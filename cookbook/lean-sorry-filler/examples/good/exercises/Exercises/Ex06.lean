/- Exercise 6: length counts concatenation additively. -/

/-- The length of a concatenation is the sum of the lengths. -/
theorem exercise_length_append (l m : List Nat) : (l ++ m).length = l.length + m.length := by simp
