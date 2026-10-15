// P1 sumsq: sum of squares, capped at 10^18.
'use strict';
const fs = require('fs');

const data = fs.readFileSync(0, 'utf8').split(/\s+/);
if (data.length < 2 || data[0] === '') process.exit(1);
const n = Number(data[0]);
let total = 0n;
const CAP = 1000000000000000000n;
for (let i = 1; i <= n; i++) {
  const x = BigInt(data[i]);
  total += x * x;
  if (total > CAP) { total = CAP; break; }
}
process.stdout.write(total.toString() + '\n');
