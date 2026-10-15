"""The synthetic date-normalization task: generator + analytic inverse.

Single source of truth shared by the training pipeline (inside the sandbox)
and the judge. The judge never trusts an artifact's own data: it regenerates
the held-out test set with its own seed and parses every input back to the
exact correct ISO answer with `iso_answer` below (no model involved).
"""

import datetime
import random

TRAIN_SIZE = 2000
TEST_SIZE = 200
TRAIN_SEED = 20240917
TEST_SEED = 909090
MIN_DATE = datetime.date(1990, 1, 1)
MAX_DATE = datetime.date(2029, 12, 31)

MONTHS_FULL = [
    "January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December",
]
MONTHS_ABBR = [m[:3] for m in MONTHS_FULL]
MONTH_TO_NUM = {name: i + 1 for i, name in enumerate(MONTHS_FULL)}
MONTH_TO_NUM.update({abbr: i + 1 for i, abbr in enumerate(MONTHS_ABBR)})

ORDINAL_SUFFIXES = {1: "st", 2: "nd", 3: "rd"}
# templates 0..5 in SPEC order
N_TEMPLATES = 6


def ordinal_suffix(day: int) -> str:
    if 10 <= day % 100 <= 20:
        return "th"
    return ORDINAL_SUFFIXES.get(day % 10, "th")


def render(date: datetime.date, template: int) -> str:
    y, m, d = date.year, date.month, date.day
    if template == 0:
        return f"{MONTHS_FULL[m - 1]} {d}, {y}"
    if template == 1:
        return f"{d} {MONTHS_FULL[m - 1]} {y}"
    if template == 2:
        return f"{m:02d}/{d:02d}/{y}"
    if template == 3:
        return f"{y:04d}-{m:02d}-{d:02d}"
    if template == 4:
        return f"{MONTHS_ABBR[m - 1]} {d}, {y}"
    if template == 5:
        return f"{d}{ordinal_suffix(d)} of {MONTHS_FULL[m - 1]}, {y}"
    raise ValueError(template)


def parse(text: str) -> datetime.date:
    """The analytic inverse of `render`: exact, total, template-driven."""
    s = text.strip()
    # template 3: ISO passthrough
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        try:
            return datetime.date(int(s[0:4]), int(s[5:7]), int(s[8:10]))
        except ValueError:
            raise ValueError(f"not a valid ISO date: {s!r}")
    # template 2: MM/DD/YYYY
    if "/" in s:
        parts = s.split("/")
        if len(parts) == 3:
            try:
                m, d, y = int(parts[0]), int(parts[1]), int(parts[2])
                return datetime.date(y, m, d)
            except ValueError:
                raise ValueError(f"not a valid date: {s!r}")
        raise ValueError(f"unparseable date: {s!r}")
    words = s.replace(",", " ").split()
    day = month = year = None
    for w in words:
        if w.lower() == "of":
            continue
        if w.isdigit():
            n = int(w)
            if len(w) == 4 and 1900 <= n <= 2100:
                year = n
            elif day is None:
                day = n
            elif year is None:
                year = n
        elif w[-2:] in ("st", "nd", "rd", "th") and w[:-2].isdigit():
            day = int(w[:-2])
        elif w in MONTHS_FULL:
            month = MONTH_TO_NUM[w]
        elif w in MONTHS_ABBR:
            month = MONTH_TO_NUM[w]
        else:
            raise ValueError(f"unparseable date word: {w!r} in {s!r}")
    if month is not None and day is not None and year is not None:
        # templates 0/4 ("<month> <day>, <year>"), 1 ("<day> <month> <year>")
        # and 5 ("<day> of <month>, <year>") share this grammar and are all
        # unambiguous once month/day/year are identified.
        try:
            return datetime.date(year, month, day)
        except ValueError:
            raise ValueError(f"not a valid date: {s!r}")
    raise ValueError(f"incomplete date: {s!r}")


def iso_answer(text: str) -> str:
    return parse(text).isoformat()


def generate_split(seed: int, n_train: int, n_test: int):
    """One seeded stream, split: first n_train rows train, last n_test test.

    Disjoint by construction — no rendered input string can appear in both
    splits — and fully deterministic, so the judge regenerates exactly the
    test set the trainer saw, from the seed alone.
    """
    rng = random.Random(seed)
    days = (MAX_DATE - MIN_DATE).days
    items = []
    for _ in range(n_train + n_test):
        date = MIN_DATE + datetime.timedelta(days=rng.randrange(days + 1))
        template = rng.randrange(N_TEMPLATES)
        items.append((render(date, template), date.isoformat()))
    return items[:n_train], items[n_train:]


def train_set():
    return generate_split(TRAIN_SEED, TRAIN_SIZE, TEST_SIZE)[0]


def test_set():
    return generate_split(TRAIN_SEED, TRAIN_SIZE, TEST_SIZE)[1]
