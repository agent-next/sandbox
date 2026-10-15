/- Exercise 1: addition is not symmetric — get the order right. -/

/-- `1 + n` and `n + 1` agree, even though addition is recursive in the
second argument. -/
theorem exercise_one_add_self (n : Nat) : 1 + n = n + 1 := by omega
