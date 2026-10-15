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


def key(keys, delay=0.05):
    """Send one keystroke to the focused window via XTEST.

    xdotool's --window mode synthesises XSendEvent input, which the GTK VCL
    behind LibreOffice ignores; XTEST goes through the X server itself, so
    the keystroke lands exactly as a user's would.
    """
    run(["xdotool", "key", "--clearmodifiers", keys])
    time.sleep(delay)


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


def press(*keys):
    """Send a key event to the focused window via XTEST (xdotool key)."""
    run(["xdotool", "key", *keys])


def type_text(text):
    """Type text into the focused window via XTEST (xdotool type)."""
    run(["xdotool", "type", "--delay", "12", text])


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

    # focus and raise it on the real display; XTEST input goes to the
    # focused window, so the frame must own keyboard focus first
    run(["xdotool", "windowactivate", "--sync", wid])
    run(["xdotool", "windowfocus", wid])
    run(["xdotool", "windowraise", wid])
    time.sleep(0.5)

    last = n + 1          # row of the last data row
    total_row = n + 2     # the SUM row the task contract asks for

    # --- header of the computed column ----------------------------------
    # Ctrl+Home takes the cursor to A1; Tab x3 lands on D1
    press("ctrl+Home")
    time.sleep(0.3)
    press("Tab")
    press("Tab")
    press("Tab")
    time.sleep(0.3)
    type_text("total")
    press("Return")
    time.sleep(0.4)

    # --- the computed column, one live formula per data row --------------
    # each Return commits the cell and moves down, so the cursor walks
    # D2 -> D3 -> ... -> D{total_row} on its own
    for row in range(2, 2 + n):
        type_text(f"=B{row}*C{row}")
        press("Return")
        time.sleep(0.3)

    # --- the SUM row under the table -------------------------------------
    # the cursor now sits on D{total_row}; walk to A{total_row}
    press("Left")
    press("Left")
    press("Left")
    time.sleep(0.3)
    type_text("total")
    press("Return")
    press("Up")          # back to A{total_row}
    press("Right")       # B{total_row}
    time.sleep(0.2)
    type_text(f"=SUM(B2:B{last})")
    press("Return")
    press("Up")          # back to B{total_row}
    press("Right")       # C{total_row}: stays empty by contract
    press("Right")       # D{total_row}
    time.sleep(0.2)
    type_text(f"=SUM(D2:D{last})")
    press("Return")
    time.sleep(0.6)
    print(f"actions: cursor at row {total_row}; table and SUM row entered",
          flush=True)

    # --- save as true OOXML (.xlsx) --------------------------------------
    press("ctrl+shift+s")
    time.sleep(2.5)
    type_text(XLSX)
    press("Return")
    deadline = time.time() + 20
    while time.time() < deadline:
        if os.path.exists(XLSX) and os.path.getsize(XLSX) > 0:
            break
        time.sleep(0.5)
    if not os.path.exists(XLSX):
        raise SystemExit(f"actions: save did not create {XLSX}")
    print(f"actions: wrote {XLSX}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
