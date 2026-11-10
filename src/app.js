'use strict';

const express = require('express');
const crypto = require('crypto');
const { luhnValid, maskCard } = require('./utils');
const store = require('./store');

const SUPPORTED_CURRENCIES = ['EUR', 'USD', 'TND'];

function createApp(options = {}) {
  const latencyMs =
    options.latencyMs !== undefined
      ? options.latencyMs
      : Number(process.env.SIMULATED_LATENCY_MS || 0);

  const app = express();
  app.use(express.json());

  // Request log: method, path, status. NEVER log bodies (PII / card numbers).
  app.use((req, res, next) => {
    res.on('finish', () => {
      if (process.env.NODE_ENV !== 'test') {
        console.log(`${new Date().toISOString()} ${req.method} ${req.path} ${res.statusCode}`);
      }
    });
    next();
  });

  // Artificial latency (used to demonstrate a failing performance test).
  app.use((req, res, next) => {
    if (latencyMs > 0 && req.path !== '/health') {
      setTimeout(next, latencyMs);
    } else {
      next();
    }
  });

  app.get('/health', (req, res) => res.json({ status: 'UP' }));

  app.post('/accounts', (req, res) => {
    const { owner, currency = 'EUR', balance = 0 } = req.body || {};
    if (typeof owner !== 'string' || owner.trim() === '') {
      return res.status(400).json({ error: 'owner is required' });
    }
    if (!SUPPORTED_CURRENCIES.includes(currency)) {
      return res.status(400).json({ error: 'unsupported currency' });
    }
    if (typeof balance !== 'number' || balance < 0) {
      return res.status(400).json({ error: 'balance must be a number >= 0' });
    }
    const account = { id: crypto.randomUUID(), owner: owner.trim(), currency, balance };
    store.accounts.set(account.id, account);
    return res.status(201).json(account);
  });

  app.get('/accounts/:id', (req, res) => {
    const account = store.accounts.get(req.params.id);
    if (!account) return res.status(404).json({ error: 'account not found' });
    return res.json(account);
  });

  app.post('/payments', (req, res) => {
    const { accountId, amount, cardNumber } = req.body || {};
    if (typeof amount !== 'number' || !(amount > 0)) {
      return res.status(400).json({ error: 'amount must be a number > 0' });
    }
    if (!cardNumber || !luhnValid(cardNumber)) {
      return res.status(400).json({ error: 'invalid card number' });
    }
    const account = store.accounts.get(accountId);
    if (!account) return res.status(404).json({ error: 'account not found' });
    if (account.balance < amount) {
      return res.status(402).json({ error: 'insufficient funds' });
    }
    account.balance -= amount;
    const payment = {
      id: crypto.randomUUID(),
      accountId,
      amount,
      currency: account.currency,
      cardMasked: maskCard(cardNumber),
      status: 'COMPLETED',
    };
    store.payments.set(payment.id, payment);
    return res.status(201).json(payment);
  });

  app.get('/payments/:id', (req, res) => {
    const payment = store.payments.get(req.params.id);
    if (!payment) return res.status(404).json({ error: 'payment not found' });
    return res.json(payment);
  });

  return app;
}

module.exports = { createApp };
