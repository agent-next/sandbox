# REPRODUCE: archify-codebase-map

(not done: per the demo standard, independent reproduction by a different
agent following README.md in a fresh sandbox happens before merge. This
file records those numbers once that run exists.)

## Expected numbers (from RECEIPT.md)

- nodes graded: 17 top-level httpx modules
- edges graded: 63 direct-import edges
- good example: all 4 gates pass; seed-42 verdict JSON deterministic
  outside `timing`
- mutant kill rate: 8/8 (100%)
