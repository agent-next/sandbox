// P2 rle: run-length encode, count+char pairs.
'use strict';
const fs = require('fs');

const s = fs.readFileSync(0, 'utf8').replace(/\n$/, '');
if (s.length === 0) process.exit(0);
let out = '';
let prev = s[0];
let count = 1;
for (let i = 1; i < s.length; i++) {
  const ch = s[i];
  if (ch === prev) {
    count++;
  } else {
    out += count + prev;
    prev = ch;
    count = 1;
  }
}
out += count + prev;
process.stdout.write(out + '\n');
