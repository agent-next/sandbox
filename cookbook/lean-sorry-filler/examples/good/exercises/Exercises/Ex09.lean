/- Exercise 9: powers of two unfold multiplicatively. -/

/-- `2 ^ (n + 1)` is `2 * 2 ^ n` — the recurrence behind binary numbers. -/
theorem exercise_pow_succ (n : Nat) : 2 ^ (n + 1) = 2 * 2 ^ n := by
  rw [Nat.pow_succ, Nat.mul_comm]
