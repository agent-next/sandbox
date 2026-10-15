/- Exercise 4: appending the empty list changes nothing. -/

/-- `l ++ []` is `l` — the base case of every append-induction. -/
theorem exercise_append_nil (l : List Nat) : l ++ [] = l := by simp
