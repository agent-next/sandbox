#!/usr/bin/env python3
"""Real terminal motion for demo.mp4.

Two halves, one file:

* the **recorded program** (`term.py session|mutant|build|grade|selftest`)
  runs the demo's real work under `asciinema rec` and writes its output to
  the recording pty.  What it prints is what the terminal shows: the
  firmware's own UART0 bytes, the compiler's own output, the judge's own
  table.  Command *echo* is the wrapper's local echo, the way a serial
  console prints what you type -- the firmware does not echo its input
  (drive.py silences the pty for exactly that reason).
* the **player** (`term.py play`) replays an asciicast v2 file through a
  terminal emulator (pyte) and rasterises every frame with Pillow at the
  clip's frame rate.  ffmpeg encodes the frames; it never composes them.

Nothing in the terminal is typed by hand: every line on screen comes from
the recorded byte stream.
"""

import argparse
import json
import os
import random
import select
import shlex
import subprocess
import sys
import time

import pty

HERE = os.path.dirname(os.path.abspath(__file__))
DEMO = os.path.dirname(HERE)
SEED = 20260814
COLS, ROWS = 80, 30

# ---------------------------------------------------------------- palette --
# Okabe-Ito, the demo figure palette (media/common.py), on a terminal dark.
BG = "#0d1117"
FG = "#e6edf3"
DIM = "#8b949e"
C_TX = "#56b4e9"   # local echo of a command the wrapper sends
C_RX = "#7fdb8a"   # the firmware's own bytes
C_ERR = "#ff7b72"
PALETTE = {
    "default": FG,
    "green": "#009e73", "yellow": "#e69f00", "blue": "#56b4e9",
    "orange": "#d55e00", "lightgreen": "#7fdb8a", "white": "#ffffff",
    "brightblack": DIM, "dim": DIM,
}
# Foreground SGR codes only.  A background code here would be a trap: bare
# "\x1b[48m" makes a real terminal (and pyte) wait for the 256-colour form
# and eat the text that follows it.
SGR = {"dim": 90, "red": 31, "green": 32, "yellow": 33, "blue": 34,
       "orange": 35, "lightgreen": 36, "white": 97}


def out(line="", color=None, end="\r\n", dim=False):
    """Print to the recording pty (what the terminal shows).

    `color` is a pyte attribute name (fg or bg); the player maps it through
    the palette below, so what is recorded and what is drawn cannot drift.
    """
    if color is None:
        s = "\x1b[90m%s\x1b[0m" % line if dim else line
    else:
        s = "\x1b[%sm%s\x1b[0m" % (SGR.get(color, 0), line)
    sys.stdout.write(s + end)
    sys.stdout.flush()


def qemu_session(elf, boot_wait=5.0, type_cps=34, gap=0.30):
    """Run one real UART session and write it to the recording.

    Spawns QEMU on its own pty (the judge's argv), prints the launch line,
    then drives judge/spec.json's command script plus the judge's seeded
    CRC buffer set.  Every response byte is the firmware's actual output,
    read off the pty as it arrives; the command text is the wrapper's local
    echo, printed at the pace it is sent.
    """
    sys.path.insert(0, os.path.join(DEMO, "judge"))
    import drive  # the judge's own pty machinery

    with open(os.path.join(DEMO, "judge", "spec.json")) as fh:
        spec = json.load(fh)

    rng = random.Random(SEED)
    max_arg = drive.MAX_ARG_BYTES
    crc_cases = [b"123456789", b"\x00" * max_arg, b"\xff" * max_arg]
    crc_cases += [bytes(rng.randrange(256) for _ in range(rng.randint(1, max_arg)))
                  for _ in range(12)]

    argv = ["qemu-system-arm", "-M", "lm3s6965evb", "-cpu", "cortex-m3",
            "-nographic", "-monitor", "none", "-serial", "stdio",
            "-kernel", os.path.basename(elf)]
    out("$ " + " ".join(shlex.quote(a) for a in argv), color="gray")
    sys.stdout.flush()
    time.sleep(0.15)          # terminal pacing only; the boot is real

    mfd, sfd = pty_open()
    proc = subprocess.Popen(argv, stdin=sfd, stdout=sfd,
                            stderr=subprocess.DEVNULL, close_fds=True,
                            cwd=os.path.dirname(elf))
    os.close(sfd)
    drive.quiet(mfd)

    buf = bytearray()

    def pump(seconds):
        deadline = time.monotonic() + seconds
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                return
            r, _, _ = select.select([mfd], [], [], min(0.04, left))
            if not r:
                continue
            try:
                chunk = os.read(mfd, 65536)
            except OSError:
                return
            if not chunk:
                return
            buf.extend(chunk)
            sys.stdout.write(chunk.decode("utf-8", "replace"))
            sys.stdout.flush()

    # Real firmware boots in ~0.1 s (media/RECEIPT.md); the window only has
    # to cover it.  It can legitimately land before the QEMU argv line stops
    # being echoed, so the gate is "arrived at all" by the time the command
    # script starts, not "arrived after it".
    pump(boot_wait)
    banner = False
    if bytes(spec["banner"], "utf-8") in bytes(buf):
        banner = True

    def send(line):
        """Local echo + write one command, one byte at a time."""
        for ch in line:
            os.write(mfd, ch.encode())
            out(ch, color="lightgreen", end="")
            sys.stdout.flush()
            time.sleep(1.0 / type_cps)
        os.write(mfd, b"\r\n")
        out("", color="lightgreen")          # newline after the echoed command
        sys.stdout.flush()
        pump(gap)

    out("", end="")
    for entry in spec["commands"]:
        send(entry["line"])
    for data in crc_cases:
        send("CRC " + data.hex())

    pump(0.5)
    proc.kill()
    try:
        proc.wait(timeout=5)
    except Exception:
        pass
    os.close(mfd)
    return 0 if banner else 1


def pty_open():
    return pty.openpty()


def mode_session(elf):
    return qemu_session(elf)


def mode_build():
    """Real build: the toolchain's own diagnostics, untouched."""
    good = os.path.join(DEMO, "examples", "good")
    tc = os.path.join(os.path.expanduser("~"),
                      ".firmware-qemu-tools",
                      "arm-gnu-toolchain-13.3.rel1-x86_64-arm-none-eabi/bin")
    cross = os.path.join(tc, "arm-none-eabi-") if os.path.isdir(tc) else ""
    out("$ make -C examples/good clean build/firmware.elf", color="gray")
    time.sleep(0.35)
    rc = subprocess.call(["make", "-C", good, "CROSS=%s" % cross,
                          "clean", "build/firmware.elf"])
    time.sleep(0.4)
    return rc


def mode_grade():
    out("$ bash judge/grade.sh examples/good --seed %d" % SEED, color="gray")
    time.sleep(0.35)
    rc = subprocess.call(["bash", os.path.join(DEMO, "judge", "grade.sh"),
                          os.path.join(DEMO, "examples", "good"),
                          "--seed", str(SEED)])
    time.sleep(0.4)
    return rc


def mode_selftest():
    out("$ bash judge/selftest.sh", color="gray")
    time.sleep(0.35)
    rc = subprocess.call(["bash", os.path.join(DEMO, "judge", "selftest.sh")])
    return rc


# ------------------------------------------------------------------ play ----

def play(cast_path, out_path, fps=30, speed=1.0, width=2560, height=1440,
         start=0.0, stop=None, crop=None):
    """Replay one asciicast through pyte and pipe frames to ffmpeg."""
    import pyte
    from PIL import Image, ImageDraw, ImageFont

    events = []
    with open(cast_path) as fh:
        header = json.loads(fh.readline())
        for line in fh:
            line = line.strip()
            if not line:
                continue
            t, kind, data = json.loads(line)
            if kind == "o":
                events.append((t, data))
    cols, rows = header["width"], header["height"]

    if crop:
        cx, cy, cw, ch = crop          # grid cells
    else:
        cx, cy, cw, ch = 0, 0, cols, rows
    cell_w = width / float(cw)
    cell_h = height / float(ch)
    font = ImageFont.truetype(
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        int(cell_h * 0.78))
    font_b = ImageFont.truetype(
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
        int(cell_h * 0.78))

    screen = pyte.Screen(cols, rows)
    stream = pyte.ByteStream(screen)

    last = events[-1][0] if events else 0.0
    duration = (stop if stop is not None else last) - start
    if duration <= 0:
        raise SystemExit("term.py play: empty window in %s" % cast_path)
    nframes = int(duration * fps)

    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", "%dx%d" % (width, height), "-r", str(fps), "-i", "-",
           "-c:v", "libx264", "-preset", "medium", "-crf", "12",
           "-pix_fmt", "yuv420p", out_path]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    ei = 0
    for f in range(nframes):
        t_real = start + f / float(fps)
        t_cast = t_real * speed
        while ei < len(events) and events[ei][0] <= t_cast:
            stream.feed(events[ei][1].encode("utf-8", "replace"))
            ei += 1

        img = Image.new("RGB", (width, height), BG)
        draw = ImageDraw.Draw(img)
        display = screen.display          # rows of text
        buf = screen.buffer
        for gy in range(ch):
            row = buf[cy + gy]
            y0 = int(gy * cell_h)
            for gx in range(cw):
                cell = row[cx + gx]
                ch_txt = cell.data
                fg = cell.fg or "default"
                bg = cell.bg or "default"
                fg_c = _colour(fg, cell.bold)
                x0 = int(gx * cell_w)
                x1 = int((gx + 1) * cell_w)
                y1 = int((gy + 1) * cell_h)
                # "default" background = no fill at all; anything else is a
                # real SGR background from the recording.
                bg_c = None if bg == "default" else _colour(bg)
                if bg_c is not None and bg_c != BG:
                    draw.rectangle([x0, y0, x1, y1], fill=bg_c)
                if ch_txt.strip():
                    fnt = font_b if cell.bold else font
                    draw.text((x0 + cell_w * 0.06, y0 + cell_h * 0.09),
                              ch_txt, font=fnt, fill=fg_c)
        # block cursor at the replayed cursor position (terminal behaviour)
        if int(t_real * 2.6) % 2 == 0:
            cxx, cyy = screen.cursor.x, screen.cursor.y
            if cx <= cxx < cx + cw and cy <= cyy < cy + ch:
                draw.rectangle([int((cxx - cx) * cell_w), int((cyy - cy) * cell_h),
                                int((cxx - cx + 1) * cell_w),
                                int((cyy - cy + 1) * cell_h)], fill=FG)
        proc.stdin.write(img.tobytes())
    proc.stdin.close()
    rc = proc.wait()
    if rc != 0:
        raise SystemExit("term.py play: ffmpeg failed (%d) for %s"
                         % (rc, out_path))
    print("term.py: %s  %d frames  %.1fs  %dx%d"
          % (out_path, nframes, duration, width, height))


def _colour(name, bold=False):
    """Resolve a pyte colour attribute to its palette hex.

    "default" is the foreground (`fg == pixel text`); a caller that means the
    background must pass `BG` in explicitly -- a bare "default" background
    resolves to FG here and painting every cell with it turns the frame
    uniformly bright.
    """
    if not name or name == "default":
        return DIM if bold else FG
    key = str(name)
    if key in PALETTE:
        return PALETTE[key]
    # pyte hands back 256-colour / RGB escapes as bare hex ("009e73").
    if len(key) == 6 and all(c in "0123456789abcdefABCDEF" for c in key):
        return "#" + key.lower()
    return FG


# ------------------------------------------------------------------ main ----

def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("session")
    s.add_argument("elf")
    s = sub.add_parser("build")
    s = sub.add_parser("grade")
    s = sub.add_parser("selftest")

    p = sub.add_parser("play")
    p.add_argument("cast")
    p.add_argument("out")
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--speed", type=float, default=1.0,
                   help="playback factor: 4.0 replays the cast 4x faster")
    p.add_argument("--width", type=int, default=2560)
    p.add_argument("--height", type=int, default=1440)
    p.add_argument("--start", type=float, default=0.0)
    p.add_argument("--stop", type=float, default=None)
    p.add_argument("--crop", default=None,
                   help="grid cells: X,Y,W,H of the active region")
    args = ap.parse_args()

    if args.cmd in ("session", "build", "grade", "selftest"):
        # stdout is the recording pty; nothing here goes anywhere else
        if args.cmd == "session":
            sys.exit(mode_session(args.elf))
        if args.cmd == "build":
            sys.exit(mode_build())
        if args.cmd == "grade":
            sys.exit(mode_grade())
        sys.exit(mode_selftest())

    crop = None
    if args.crop:
        crop = tuple(int(v) for v in args.crop.split(","))
    play(args.cast, args.out, fps=args.fps, speed=args.speed,
         width=args.width, height=args.height, start=args.start,
         stop=args.stop, crop=crop)


if __name__ == "__main__":
    main()
