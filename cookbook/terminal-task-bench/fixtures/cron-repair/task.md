# Task: repair the crontab

`work/crontab` has one line per scheduled job, but six of them would be
rejected by any scheduler: a step of zero, a missing field, an
out-of-range hour, one line with six time fields, and one that uses a
day-of-week name instead of a number.

Repair `work/crontab` in place so that it schedules **exactly** the six
jobs it was meant to, in this order:

| # | schedule | command |
|---|---|---|
| 1 | keep its existing minute, `* * * *` | `/opt/bench/bin/tick.sh` |
| 2 | every 15 minutes | `/opt/bench/bin/poll.sh` |
| 3 | 02:00 daily | `/opt/bench/bin/backup.sh` |
| 4 | 04:30, Monday to Friday | `/opt/bench/bin/report.sh` |
| 5 | 00:00 on the 1st of the month | `/opt/bench/bin/monthly.sh` |
| 6 | 06:00 on Sunday | `/opt/bench/bin/weekly.sh` |

Rules the file must satisfy:

- five numeric time fields then the command, separated by single spaces;
- `*`, single numbers, `a-b` ranges and `*/n` steps are the only forms;
- `minute` 0–59, `hour` 0–23, `day-of-month` 1–31, `month` 1–12,
  `day-of-week` 0–6 with **0 = Sunday**; no names, no six-field lines;
- comment lines start with `#`; the header comment may stay.

The judge expands every field and compares the *sets* of minutes, hours,
days, months and weekdays each line actually matches — a line that looks
plausible but fires at the wrong times fails.

Verify with `bash verify.sh "$PWD/work"` (from this directory).
