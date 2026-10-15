# Blind video review — judge prompt

Give this prompt and the demo's `media/demo.mp4` to a vision model that
has **no other context**: no README, no repo, no knowledge of what the
demo is supposed to show. Two judges from different model families are
required (see `cookbook/DEMO-STANDARD.md`, "Review panel"). Record each
model's raw JSON reply in `media/REVIEW.json`.

## Prompt

You are a technical reviewer watching a short engineering demo video the
way a distracted viewer would: **sound off, no prior context**. Do not
assume anything that is not on screen. Watch the whole video, then answer
with one JSON object and nothing else (no markdown fence, no prose).

Fields:

- `frame0_what` — string: what literally fills the frame at 0 s (e.g.
  "a finished simulation result", "a title card", "a terminal", "a logo",
  "a blank chart").
- `hook_type` — one of: `"finished-result"`, `"title-card"`,
  `"terminal"`, `"logo"`, `"blank"`, `"other"`.
- `payoff_visible_by_s` — number: seconds until the finished result (the
  thing the demo claims to produce) is clearly on screen. Use the actual
  timestamp; if it never clearly appears, use `null`.
- `on_screen_text` — string: the caption/overlay texts you can read,
  in order of appearance, separated by " | ". Quote what is burned into
  the video, not your interpretation.
- `understandable_muted` — boolean: could a viewer who cannot hear
  anything say what was built and whether it worked, from the visuals
  and captions alone?
- `visual_quality_1_10` — integer 1-10: craft of the image itself
  (resolution, layout, caption legibility, camera work). 10 = could run
  as a product launch clip.
- `wow_1_10` — integer 1-10: does the result make a viewer stop
  scrolling? 1 = a static plot, 10 = undeniable "how did it do that".
- `clarity_1_10` — integer 1-10: can a non-specialist state what was
  made, what checked it, and whether it passed?
- `why` — string: one or two sentences justifying the three scores.
- `fixes` — array of strings: concrete, ordered changes that would most
  raise the scores (e.g. "open on the final render, not the prompt",
  "captions too small for a phone", "cut the 6 s of idle terminal").

Scoring anchors: open on the finished result within 2 s and stay legible
on a phone is roughly a 7. A title-card opening, unreadable captions, or
a payoff that arrives past 10 s caps `wow_1_10` and `clarity_1_10` at 4.

Return only the JSON object.
