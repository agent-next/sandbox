/- Exercise 10: conjunction distributes over disjunction. -/

/-- `∧` pushes into both sides of a `∨`. -/
theorem exercise_and_distrib (p q r : Prop) : (p ∧ (q ∨ r)) ↔ ((p ∧ q) ∨ (p ∧ r)) := by
  constructor
  · intro h
    cases h.2 with
    | inl hq => exact Or.inl ⟨h.1, hq⟩
    | inr hr => exact Or.inr ⟨h.1, hr⟩
  · intro h
    cases h with
    | inl hpq => exact ⟨hpq.1, Or.inl hpq.2⟩
    | inr hpr => exact ⟨hpr.1, Or.inr hpr.2⟩
