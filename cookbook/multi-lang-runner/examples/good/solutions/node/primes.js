// P3 primes: count primes p with lo <= p <= hi, simple sieve.
'use strict';
const fs = require('fs');

const data = fs.readFileSync(0, 'utf8').split(/\s+/);
if (data.length < 2 || data[0] === '') process.exit(1);
const lo = Number(data[0]);
const hi = Number(data[1]);
if (hi < 2) { process.stdout.write('0\n'); process.exit(0); }
const sieve = new Uint8Array(hi + 1).fill(1);
sieve[0] = 0; sieve[1] = 0;
for (let i = 2; i * i <= hi; i++) {
  if (sieve[i]) {
    for (let j = i * i; j <= hi; j += i) sieve[j] = 0;
  }
}
let count = 0;
for (let i = lo; i <= hi; i++) count += sieve[i];
process.stdout.write(count + '\n');
