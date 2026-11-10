'use strict';

const accounts = new Map();
const payments = new Map();

function reset() {
  accounts.clear();
  payments.clear();
}

module.exports = { accounts, payments, reset };
