#!/usr/bin/env python3
"""Generates postman/payflex.postman_collection.json (run once; the JSON is committed)."""
import json

def req(name, method, path, body=None, tests=None, prerequest=None):
    item = {
        "name": name,
        "request": {
            "method": method,
            "header": [{"key": "Content-Type", "value": "application/json"}],
            "url": {"raw": "{{baseUrl}}" + path, "host": ["{{baseUrl}}"], "path": [p for p in path.split("/") if p]},
        },
        "event": [],
    }
    if body is not None:
        item["request"]["body"] = {"mode": "raw", "raw": json.dumps(body, indent=2)}
    if prerequest:
        item["event"].append({"listen": "prerequest", "script": {"type": "text/javascript", "exec": prerequest}})
    if tests:
        item["event"].append({"listen": "test", "script": {"type": "text/javascript", "exec": tests}})
    return item

# Card number built at runtime: the repository never contains a literal PAN.
CARD_PRE = [
    "pm.collectionVariables.set('card', ['4111','1111','1111','1111'].join(''));",
    "pm.collectionVariables.set('badCard', ['4111','1111','1111','1112'].join(''));",
]

items = [
    req("01 - Health check", "GET", "/health", tests=[
        "pm.test('status 200', () => pm.response.to.have.status(200));",
        "pm.test('status is UP', () => pm.expect(pm.response.json().status).to.eql('UP'));",
    ]),
    req("02 - Create account", "POST", "/accounts", body={"owner": "Alice", "currency": "EUR", "balance": 500}, tests=[
        "pm.test('status 201', () => pm.response.to.have.status(201));",
        "const a = pm.response.json();",
        "pm.test('contract: id/owner/balance/currency', () => {",
        "  pm.expect(a).to.have.all.keys('id','owner','currency','balance');",
        "  pm.expect(a.balance).to.eql(500);",
        "});",
        "pm.collectionVariables.set('accountId', a.id);",
    ]),
    req("03 - Create account without owner (400)", "POST", "/accounts", body={"currency": "EUR"}, tests=[
        "pm.test('status 400', () => pm.response.to.have.status(400));",
    ]),
    req("04 - Get account", "GET", "/accounts/{{accountId}}", tests=[
        "pm.test('status 200', () => pm.response.to.have.status(200));",
        "pm.test('same id', () => pm.expect(pm.response.json().id).to.eql(pm.collectionVariables.get('accountId')));",
    ]),
    req("05 - Payment OK", "POST", "/payments",
        body={"accountId": "{{accountId}}", "amount": 100, "cardNumber": "{{card}}"},
        prerequest=CARD_PRE, tests=[
        "pm.test('status 201', () => pm.response.to.have.status(201));",
        "const p = pm.response.json();",
        "pm.test('payment completed', () => pm.expect(p.status).to.eql('COMPLETED'));",
        "pm.test('card is masked (no PAN leak in response)', () => {",
        "  pm.expect(p.cardMasked).to.eql('**** **** **** 1111');",
        "  pm.expect(pm.response.text()).to.not.include(pm.collectionVariables.get('card'));",
        "});",
        "pm.collectionVariables.set('paymentId', p.id);",
    ]),
    req("06 - Account debited", "GET", "/accounts/{{accountId}}", tests=[
        "pm.test('balance is 400', () => pm.expect(pm.response.json().balance).to.eql(400));",
    ]),
    req("07 - Payment with invalid card (400)", "POST", "/payments",
        body={"accountId": "{{accountId}}", "amount": 10, "cardNumber": "{{badCard}}"},
        prerequest=CARD_PRE, tests=[
        "pm.test('status 400', () => pm.response.to.have.status(400));",
    ]),
    req("08 - Payment with insufficient funds (402)", "POST", "/payments",
        body={"accountId": "{{accountId}}", "amount": 99999, "cardNumber": "{{card}}"},
        prerequest=CARD_PRE, tests=[
        "pm.test('status 402', () => pm.response.to.have.status(402));",
    ]),
    req("09 - Get payment", "GET", "/payments/{{paymentId}}", tests=[
        "pm.test('status 200', () => pm.response.to.have.status(200));",
        "pm.test('same payment', () => pm.expect(pm.response.json().id).to.eql(pm.collectionVariables.get('paymentId')));",
    ]),
    req("10 - Unknown account (404)", "GET", "/accounts/does-not-exist", tests=[
        "pm.test('status 404', () => pm.response.to.have.status(404));",
    ]),
]

collection = {
    "info": {
        "name": "PayFlex API - Integration scenario",
        "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
    },
    "variable": [
        {"key": "baseUrl", "value": "http://localhost:3000"},
        {"key": "accountId", "value": ""},
        {"key": "paymentId", "value": ""},
    ],
    "item": items,
}

with open("postman/payflex.postman_collection.json", "w", encoding="utf-8") as f:
    json.dump(collection, f, indent=2)
print("collection written")
