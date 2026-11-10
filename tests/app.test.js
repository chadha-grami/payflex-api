const request = require('supertest');
const { createApp } = require('../src/app');
const store = require('../src/store');

const VALID_CARD = ['4111', '1111', '1111', '1111'].join('');
const INVALID_CARD = ['4111', '1111', '1111', '1112'].join('');

let app;
beforeEach(() => {
  store.reset();
  app = createApp({ latencyMs: 0 });
});

async function newAccount(balance = 100) {
  const res = await request(app).post('/accounts').send({ owner: 'Alice', balance });
  return res.body;
}

describe('health', () => {
  test('GET /health', async () => {
    const res = await request(app).get('/health');
    expect(res.status).toBe(200);
    expect(res.body.status).toBe('UP');
  });
});

describe('accounts', () => {
  test('creates an account', async () => {
    const res = await request(app).post('/accounts').send({ owner: 'Alice', balance: 50 });
    expect(res.status).toBe(201);
    expect(res.body).toMatchObject({ owner: 'Alice', balance: 50, currency: 'EUR' });
    expect(res.body.id).toBeDefined();
  });
  test('rejects missing owner', async () => {
    const res = await request(app).post('/accounts').send({});
    expect(res.status).toBe(400);
  });
  test('rejects unsupported currency', async () => {
    const res = await request(app).post('/accounts').send({ owner: 'Bob', currency: 'XXX' });
    expect(res.status).toBe(400);
  });
  test('rejects negative balance', async () => {
    const res = await request(app).post('/accounts').send({ owner: 'Bob', balance: -5 });
    expect(res.status).toBe(400);
  });
  test('gets an account', async () => {
    const acc = await newAccount();
    const res = await request(app).get(`/accounts/${acc.id}`);
    expect(res.status).toBe(200);
    expect(res.body.id).toBe(acc.id);
  });
  test('404 on unknown account', async () => {
    const res = await request(app).get('/accounts/unknown');
    expect(res.status).toBe(404);
  });
});

describe('payments', () => {
  test('creates a payment, masks the card and debits the account', async () => {
    const acc = await newAccount(100);
    const res = await request(app)
      .post('/payments')
      .send({ accountId: acc.id, amount: 30, cardNumber: VALID_CARD });
    expect(res.status).toBe(201);
    expect(res.body.status).toBe('COMPLETED');
    expect(res.body.cardMasked).toBe('**** **** **** 1111');
    expect(JSON.stringify(res.body)).not.toContain(VALID_CARD);
    const after = await request(app).get(`/accounts/${acc.id}`);
    expect(after.body.balance).toBe(70);
  });
  test('rejects invalid amount', async () => {
    const acc = await newAccount();
    const res = await request(app)
      .post('/payments')
      .send({ accountId: acc.id, amount: -1, cardNumber: VALID_CARD });
    expect(res.status).toBe(400);
  });
  test('rejects invalid card', async () => {
    const acc = await newAccount();
    const res = await request(app)
      .post('/payments')
      .send({ accountId: acc.id, amount: 5, cardNumber: INVALID_CARD });
    expect(res.status).toBe(400);
  });
  test('404 when account does not exist', async () => {
    const res = await request(app)
      .post('/payments')
      .send({ accountId: 'nope', amount: 5, cardNumber: VALID_CARD });
    expect(res.status).toBe(404);
  });
  test('402 on insufficient funds', async () => {
    const acc = await newAccount(10);
    const res = await request(app)
      .post('/payments')
      .send({ accountId: acc.id, amount: 50, cardNumber: VALID_CARD });
    expect(res.status).toBe(402);
  });
  test('gets a payment and 404 on unknown payment', async () => {
    const acc = await newAccount(100);
    const pay = await request(app)
      .post('/payments')
      .send({ accountId: acc.id, amount: 1, cardNumber: VALID_CARD });
    const ok = await request(app).get(`/payments/${pay.body.id}`);
    expect(ok.status).toBe(200);
    const ko = await request(app).get('/payments/unknown');
    expect(ko.status).toBe(404);
  });
});

describe('simulated latency', () => {
  test('delays non-health endpoints', async () => {
    const slow = createApp({ latencyMs: 60 });
    const t0 = Date.now();
    await request(slow).get('/accounts/unknown');
    expect(Date.now() - t0).toBeGreaterThanOrEqual(50);
  });
  test('does not delay /health', async () => {
    const slow = createApp({ latencyMs: 300 });
    const t0 = Date.now();
    await request(slow).get('/health');
    expect(Date.now() - t0).toBeLessThan(250);
  });
});
