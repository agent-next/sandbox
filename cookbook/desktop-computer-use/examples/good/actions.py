#!/usr/bin/env python3
"""Desktop computer-use agent action script (the known-good artifact).

Opens the judge's CSV on the $DISPLAY X display with LibreOffice Calc, adds a
computed `total` column (qty * price), adds a `SUM` total row, and saves the
workbook as /tmp/desktop-cu/report.xlsx in true OOXML format -- all by
driving the real GUI with xdotool, exactly as a computer-use agent would.

Run with:  python3 actions.py        (DISPLAY must point at the real display)
Exit 0 on success, non-zero on failure.
"""

import csv
import os
import subprocess
import sys
import time

CU_DIR = "/tmp/desktop-cu"
CSV = f"{CU_DIR}/input.csv"
XLSX = f"{CU_DIR}/report.xlsx"


def run(cmd, timeout=30, check=True):
    """Run one GUI command; print it so the log shows the real keystrokes."""
    print(f"actions: $ {' '.join(cmd)}", flush=True)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if check and r.returncode != 0:
        sys.stderr.write(r.stderr)
        raise SystemExit(f"actions: command failed: {' '.join(cmd)}")
    return r


def search_window(pattern, timeout=45):
    """Return the X window id matching pattern, waiting for it to appear."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = run(["xdotool", "search", "--class", pattern], timeout=15)
        ids = [line for line in r.stdout.splitlines() if line.strip()]
        if ids:
            return ids[0]
        time.sleep(1.0)
    raise SystemExit(f"actions: no window matching {pattern!r} after {timeout}s")


def clipboard():
    """Read the X clipboard via xclip (returns "")."""
    r = run(["xclip", "-o", "-selection", "clipboard"], timeout=10)
    return r.stdout


def set_clipboard(text):
    """Put text on the X clipboard."""
    subprocess.run(["xclip", "-selection", "clipboard"],
                   input=text, text=True, timeout=10, check=True)


def n_data_rows():
    """Read the fixture CSV to know how many data rows the sheet has."""
    with open(CSV, newline="") as fh:
        rows = list(csv.DictReader(fh))
    return len(rows)


def main():
    display = os.environ.get("DISPLAY", "")
    if not display:
        raise SystemExit("actions: DISPLAY is not set; run me on a real X display")

    n = n_data_rows()
    print(f"actions: fixture has {n} data rows", flush=True)

    wid = search_window("soffice")
    print(f"actions: Calc window id {wid}", flush=True)

    # focus and raise it on the real display
    run(["xdotool", "windowactivate", "--sync", wid])
    run(["xdotool", "windowfocus", wid])
    run(["xdotool", "windowraise", wid])
    time.sleep(0.5)

    # --- header of the computed column ----------------------------------
    # Ctrl+Home takes the cursor to A1; Tab x3 lands on D1
    run(["xdotool", "key", "--window", wid, "ctrl+Home"])
    time.sleep(0.3)
    run(["xdotool", "key", "--window", wid, "Tab"])
    run(["xdotool", "key", "--window", wid, "Tab"])
    run(["xdotool", "key", "--window", wid, "Tab"])
    time.sleep(0.3)
    run(["xdotool", "type", "--window", wid, "--delay", "12", "total"])
    run(["xdotool", "key", "--window", wid, "Return"])
    time.sleep(0.4)

    # --- the computed column, one live formula per data row --------------
    for row in range(2, 2 + n):
        run(["xdotool", "type", "--window", wid, "--delay", "12",
             f"=B{row}*C{row}"])
        run(["xdotool", "key", "--window", wid, "Return"])
        time.sleep(0.3)

    # --- the SUM row under the table -------------------------------------
    last = n + 1          # row of the last data row
    # the cursor is at D{last}; go one row below the table and one column
    # left: Down, then Left x3 puts us on column A of row last+1
    run(["xdotool", "key", "--window", wid, "Down"])
    run(["xdotool", "key", "--window", wid, "Left"])
    run(["xdotool", "key", "--window", wid, "Left"])
    run(["xdotool", "key", "--window", wid, "Left"])
    time.sleep(0.3)
    run(["xdotool", "type", "--window", wid, "--delay", "12", "total"])
    run(["xdotool", "key", "--window", wid, "Right"])
    time.sleep(0.2)
    run(["xdotool", "type", "--window", wid, "--delay", "12",
         f"=SUM(B2:B{last})"])
    run(["xdotool", "key", "--window", wid, "Left"])
    time.sleep(0.2)
    run(["xdotool", "type", "--window", wid, "--delay", "12",
         f"=SUM(D2:D{last})"])
    run(["xdotool", "key", "--window", wid, "Return"])
    time.sleep(0.6)

    # --- save as true OOXML (.xlsx) --------------------------------------
    run(["xdotool", "key", "--window", wid, "shift+ctrl+s"])
    time.sleep(2.5)
    run(["xdotool", "type", "--window", wid, "--delay", "12", XLSX])
    run(["xdotool", "key", "--window", wid, "Return"])
    time.sleep(4.0)

    if not os.path.exists(XLSX):
        raise SystemExit(f"actions: save did not create {XLSX}")
    print(f"actions: wrote {XLSX}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
