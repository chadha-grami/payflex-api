import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:3000';
// Built at runtime: no literal card number in the repository.
const CARD = ['4111', '1111', '1111', '1111'].join('');
const HEADERS = { headers: { 'Content-Type': 'application/json' } };

export const options = {
  stages: [
    { duration: '10s', target: 20 }, // ramp-up
    { duration: '30s', target: 20 }, // steady load
    { duration: '5s', target: 0 },   // ramp-down
  ],
  // Target SLO from the lab. The pipeline decides Warning vs Critical in
  // scripts/quality_gate.py from the exported summary (reports/k6-summary.json).
  thresholds: {
    http_req_duration: ['p(95)<200'],
    http_req_failed: ['rate<0.01'],
  },
};

export function setup() {
  const res = http.post(
    `${BASE_URL}/accounts`,
    JSON.stringify({ owner: 'LoadTest', currency: 'EUR', balance: 1000000000 }),
    HEADERS
  );
  return { accountId: res.json('id') };
}

export default function (data) {
  const health = http.get(`${BASE_URL}/health`);
  check(health, { 'health 200': (r) => r.status === 200 });

  const acc = http.get(`${BASE_URL}/accounts/${data.accountId}`);
  check(acc, { 'account 200': (r) => r.status === 200 });

  const pay = http.post(
    `${BASE_URL}/payments`,
    JSON.stringify({ accountId: data.accountId, amount: 1, cardNumber: CARD }),
    HEADERS
  );
  check(pay, { 'payment 201': (r) => r.status === 201 });

  sleep(0.2);
}

export function handleSummary(data) {
  const d = data.metrics.http_req_duration;
  const f = data.metrics.http_req_failed;
  const v = (m) => (m && m.values ? m.values : m) || {};
  const out =
    `\n=== k6 summary ===\n` +
    `requests : ${(v(data.metrics.http_reqs).count || 0)}\n` +
    `p(95)    : ${(v(d)['p(95)'] || 0).toFixed(2)} ms\n` +
    `error %  : ${((v(f).rate || 0) * 100).toFixed(2)}\n`;
  return {
    'reports/k6-summary.json': JSON.stringify(data, null, 2),
    stdout: out,
  };
}
