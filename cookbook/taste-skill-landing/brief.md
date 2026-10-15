# Brief: Kestrel — the wind-aware route planner for cyclists

Kestrel is a fictional product: a route planner that reads the wind forecast,
not just the map, and plans the loop that rides with the wind at your back on
the way home. One page, one product, one action: start a free route.

Sections (each must exist, in this order, with its heading):

1. **hero** — "Kestrel" + what it is in one line + one primary action
   ("Plan a wind-aware route") + the live thing: set wind speed and direction,
   see the honest time saved on a 40 km loop.
2. **how** — how it works: forecast, compass split, route search (three steps
   as prose, not cards).
3. **routes** — showcase: three named sample routes with distance, climbing
   and wind quality.
4. **pricing** — one price, what it includes, free tier limits.
5. **faq** — five real questions with answers.
6. **download** — closing call to action.
7. **footer** — wordmark at full width, credit line.

Brand colours (fixed): warm paper ground `#F4F1EA`, deep pine ink `#1A241F`,
viridian accent `#0E6E54` (accent on the action and one other thing only).
Photography does not exist for this product: imagery is drawn in code from
the subject (compass rose, wind arrows, route ribbons) as flat colour in the
brand colours, exported to raster so it counts as real pictures.

```json
{
  "product": "Kestrel",
  "sections": [
    { "id": "hero",     "heading": "Kestrel" },
    { "id": "how",      "heading": "How Kestrel plans" },
    { "id": "routes",   "heading": "Three loops" },
    { "id": "pricing",  "heading": "One price" },
    { "id": "faq",      "heading": "Questions" },
    { "id": "download", "heading": "Ride with the wind" },
    { "id": "footer",   "heading": "Kestrel" }
  ],
  "colors": { "ground": "#F4F1EA", "ink": "#1A241F", "accent": "#0E6E54" }
}
```
