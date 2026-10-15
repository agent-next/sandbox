---
name: regex-cookbook
description: Read values out of config snippets and match text with regular
  expressions without the four mistakes that make a first attempt look right
  and be wrong: greedy swallows, unescaped quotes, unanchored word counts and
  case-folded key lookups.
---

# regex-cookbook

Config snippets and log lines are written for humans, not for parsers: a key
appears twice, a value carries a trailing comment, a "port" line lists two
ports, a quote is escaped, a sentence ends with a period right after a
version number. A first attempt that "works on the example" usually fails on
exactly those cases. This skill is the set of habits that survive them.

## 1. Scope before you look up

A key is not unique in a file. Before reading `key = value`:

- **Sections win over the whole file.** If the file has `[section]` headers,
  collect the lines of the *named* block first, then look the key up inside
  it. A flat `dict` over the whole file silently returns the value from the
  first block that happens to define the key.
- **First vs last occurrence is a decision, not an accident.** Both `setdefault`
  and plain assignment "work" — one keeps the first hit, the other the last —
  and which one you get is invisible in the result. Decide, and say which in
  the answer.
- **A commented-out line is not an assignment.** `# feature_flag = off`
  followed by `feature_flag = on` has one active value. Strip comment markers
  *after* deciding whether a line is active, not before: `line.lstrip("#")`
  turns a comment into a value.

## 2. Compare keys the way the task asks

`TLS_MIN_VERSION` and `tls_min_version` are two different keys in a
case-sensitive file and the same key in a case-insensitive one. Lower-casing
the key *and* the file is a decision that must be made once, deliberately —
a case-insensitive lookup that happens to see the decoy first returns the
wrong version and looks entirely reasonable doing it.

## 3. Greedy is not "more correct"

`.*` is the most common source of a confidently wrong answer.

| you want | do not write | write |
|---|---|---|
| the first port in `port=8000,8001;` | `port=(.*)` | `\bport=(\d+)` |
| a quoted string that contains `\"` | `"[^"]*"` | `"(?:[^"\\]|\\.)*"` |
| a version, not a sentence end | `[0-9.]+` | `\d+(?:\.\d+)+` |
| a whole word | `text.count(word)` | `\b{word}\b` |
| an address, not an IPv6 one | `\d+\.\d+\.\d+\.\d+` | `\b(?:\d{1,3}\.){3}\d{1,3}\b` |

- **Lazy is not the fix for greedy either.** `port=(.*?)` still needs the
  right stopping character; `(\d+)` says what a port *is*.
- **Escape-aware quotes.** `"(?:[^"\\]|\\.)*"` reads a quote, then either a
  non-quote/non-backslash character or a backslash and whatever follows it,
  until the closing quote. It is the standard spelling of "a quoted string
  with escapes in it".
- **Anchor on what you are counting.** `\b` before a digit run keeps `::1`
  out of an IPv4 match; `$` pins the last integer; `+` belongs in a
  local-part character class (`[\w.+-]+@`), not outside it.

## 4. Count words, not substrings

`"red redder red".count("red")` is 3; there are 2 whole words. When the
question says *word*, a substring count is a different question with a
plausible-looking answer. Use `re.findall(rf"(?i)\b{re.escape(word)}\b", text)`
and take its length.

## 5. Trim values in the right order

A config value can carry a trailing comment (`"release/2.0"   # keep`) and
padding around it. Trim the comment first, then whitespace — the reverse
order leaves the comment in the answer. And keep quotes if they are part of
the value; only the task's contract decides whether they are.

## Snippets

`reference.py` in this package is the technique table these habits turn into:
a section-scoped `ini_lookup`, a `csv_lookup`, and one anchored function per
text family (`first_port`, `quoted`, `version`, `word_count`, `email_local`,
`dotted_quad`, `trailing_int`, `digits_join`). Read it before writing your
own; it is short and every function carries the one line that says why its
pattern is shaped the way it is.
