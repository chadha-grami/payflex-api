'use strict';

/** Luhn checksum validation for card numbers. */
function luhnValid(number) {
  const digits = String(number).replace(/[\s-]/g, '');
  if (!/^\d{13,19}$/.test(digits)) return false;
  let sum = 0;
  let double = false;
  for (let i = digits.length - 1; i >= 0; i--) {
    let d = Number(digits[i]);
    if (double) {
      d *= 2;
      if (d > 9) d -= 9;
    }
    sum += d;
    double = !double;
  }
  return sum % 10 === 0;
}

/** Mask a card number: only the last 4 digits are kept. */
function maskCard(number) {
  const digits = String(number).replace(/\D/g, '');
  return `**** **** **** ${digits.slice(-4)}`;
}

module.exports = { luhnValid, maskCard };
