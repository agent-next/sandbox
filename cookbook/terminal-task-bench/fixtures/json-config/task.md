# Task: repair the JSON config

`work/config.json` is not valid JSON (a trailing comma and a duplicated
key) and, even where it parses, its types are wrong. Repair it in place so
that the file satisfies this schema exactly:

- `name` — string, unchanged from the file;
- `version` — string matching `^\d+\.\d+\.\d+$`;
- `retries` — integer;
- `enabled` — boolean (`true`/`false`, not a string);
- `tags` — array of **unique** strings, sorted;
- `weights` — array of objects, each with an integer `weight` and a string
  `id`; the `id`s are unique, and the weights sum to exactly 100;
- no duplicate keys anywhere, no trailing commas, valid JSON, 2-space
  indent, one trailing newline.

Keep the values the file already carries (including `name`, `version` and
`retries`); convert the types and remove the duplicates.

Verify with `bash verify.sh "$PWD/work"` (from this directory).
