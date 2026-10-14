# Bare-metal UART shell firmware for an emulated Cortex-M3 board

## Goal

Show an agent writing real embedded C — no OS, no libc, linker script and
startup code by hand — and having a judge it cannot fool decide whether the
result is right.

The agent produces a **C firmware artifact** for a single debug board (a
Stellaris/TI LM3S6965 evaluation board, emulated by QEMU) that is built with
`-Wall -Werror`, boots bare metal on the emulator, and answers a scripted
UART command shell over the emulated serial port.

## What the agent writes

Three units, plus the bare-metal scaffolding they need:

| unit | responsibility |
|---|---|
| `ring.c` | fixed-size byte ring buffer (`rb_init`, `rb_push`, `rb_pop`, `rb_peek`, `rb_count`) |
| `crc.c` | CRC-32 (IEEE 802.3) of a byte range, computed in place, no table |
| `uart.c` | UART driver: init, `putc`/`puts`, `getc` polling, interrupt-driven RX ring |
| `shell.c` | command shell over UART, line editing, command dispatch |

The agent may lay these out however it likes; only the file names above are
fixed, because the mutant generator in `judge/mutants.py` edits them by line
number.

## The board

QEMU's `lm3s6965evb` machine:

- ARM Cortex-M3, Cortex-M3 little-endian (v7-M), 256 KiB flash at `0x00000000`,
  64 KiB SRAM at `0x20000000`
- Stellaris UART0 at `0x4000C000`; QEMU connects UART0 to the stdio backend by
  default for this machine (`-serial stdio` is also accepted)
- The demo drives UART0 with `-serial mon:stdio` or `-serial pty`, so the judge
  can write request lines and read response lines

## Non-goals

- Not a real device and not a hardware bring-up demo. Nothing here proves
  timing, power, radio behaviour or anything about real silicon.
- No OS, no scheduler, no filesystem, no dynamic allocation.
- No `-march`-specific tuning, no assert on code size, no bootloader.
- Not a benchmark. Wall time is reported because a judge that takes an hour is
  useless, not because speed is graded.

## The artifact

`examples/good/` holds the reference firmware: `startup.c`, `link.ld`, the four
units above, a `Makefile`, and `common.h`. The judge builds whatever directory
it is given with that same `Makefile` contract:

```
make CROSS=arm-none-eabi- build/firmware.elf
```

so the judged artifact must be a drop-in replacement for
`examples/good/` — same `Makefile` target, same source file names.

## Acceptance oracle

The judge never trusts the artifact to report about itself. Four independent
oracles:

1. **The toolchain** (`arm-none-eabi-gcc -Wall -Werror`) — compile warnings are
   failures, not opinions.
2. **A blank-slab emulator** — QEMU boots the ELF on a board with nothing else
   on it. If it boots, the vector table, `Reset_Handler`, `.data` copy and
   `.bss` clear are all correct. If the shell answers, the UART really works.
3. **Python `zlib`** — the kernel-side reference CRC-32, run over the same
   bytes the firmware was fed. No shared code, no shared table.
4. **Checksums of the judge directory** — taken before and after each build, so
   no artifact can edit its own judge.

Gates are numeric, deterministic, and pass/fail. There is no partial credit and
no "the build succeeded" gate standing alone: every gate compares against
something outside the artifact.

## Gates

The judge prints exactly one verdict JSON object. All gates must pass for exit
code 0. `P` = measured value, `R` = rule.

### Gate list

| # | gate | what is measured | pass rule |
|---|---|---|---|
| 1 | `build_clean` | `arm-none-eabi-gcc -Wall -Werror` exit code and stderr | exit 0 **and** stderr empty |
| 2 | `elf_ok` | `arm-none-eabi-readelf -h` on the built ELF | e_machine is `ARM` (0x28) **and** ET_EXEC **and** entry point within `.text` |
| 3 | `maps_ok` | section sizes from `arm-none-eabi-size` | `.text + .rodata <= 8192` bytes |
| 4 | `boot` | stdout of QEMU, watched for the boot banner | banner seen within `BOOT_S` seconds |
| 5 | `shell` | scripted request/response round trips over the UART | every response matches its rule below, byte for byte, in order, within `SHELL_S` |
| 6 | `crc_oracle` | CRC-32 of 15 buffers (3 fixed + 12 seeded pseudo-random, each at most 64 bytes) vs Python `zlib.crc32` | **all** 15 match, exactly |
| 7 | `no_hardfault` | whole QEMU stdout + stderr, all rounds combined | zero occurrences of `HardFault`, `UsageFault`, `BusFault`, `MemManage` |
| 8 | `judge_intact` | sha256 of every file under `judge/`, before vs after | identical |

Numeric constants. `grade.sh` takes only `--seed` and `--json` on the
command line; the values below are environment variables:

| constant | default | meaning |
|---|---|---|
| `BOOT_S` | 10 | seconds allowed for the boot banner |
| `SHELL_S` | 30 | seconds for the whole scripted UART session |
| `MACHINE` | `lm3s6965evb` | QEMU machine, passed to `drive.py` |
| `QEMU_BIN` | `qemu-system-arm` | emulator binary, read by `grade.sh` (`drive.py` invokes `qemu-system-arm` by name) |

The CRC oracle's shape is fixed in `judge/drive.py` and cannot be
overridden: 3 fixed buffers plus 12 seeded pseudo-random buffers of at
most `MAX_ARG_BYTES` (64) bytes each — 15 buffers per grade.

Rows are filtered through a **known-answer mask**: the judge knows the exact
string the firmware should print for every input, from `judge/spec.json`.
That file is the contract, not a hint — it is written from this spec by hand
and never derived from the artifact.

### UART protocol

One command per line, terminated by `\r\n` (LF alone is also accepted), echoed
per character as it is typed. Responses end with `\r\n`. Any unknown command
must be answered `ERR unknown\r\n` and must not stop the shell.

| command | response |
|---|---|
| `HELP` | `OK commands: HELP VER ID CRC RB PING ECHO\r\n` |
| `VER` | `OK firmware-qemu 1.0 cortex-m3\r\n` |
| `ID` | `OK lm3s6965evb\r\n` |
| `PING` | `OK pong\r\n` |
| `CRC <hex>` | `OK <CRC-32 of the decoded bytes, 8 lowercase hex digits>\r\n` |
| `RB push <hex>` | `OK <count after push>\r\n` |
| `RB pop` | `OK <count after pop>\r\n` (or `ERR empty\r\n`) |
| `RB count` | `OK <count>\r\n` |
| `RB clear` | `OK 0\r\n` |
| `RB dump` | `OK <all bytes in the ring, hex>\r\n` (empty ring -> `OK \r\n`) |
| `ECHO <text>` | `OK <text>\r\n` |
| anything else | `ERR unknown\r\n` |

`CRC` and `RB push` take a hex string; an odd-length or non-hex argument
returns `ERR bad hex\r\n`.

### Ring buffer rules

The ring buffer capacity is `RB_CAP` (16 in the reference firmware). Rules the
gate checks, via `RB` commands:

- `push` of a single byte returns the new count, and the ring wraps at
  `RB_CAP` — a `push` past capacity returns `OK 16` and drops the oldest byte,
  so `RB count` never exceeds `RB_CAP`
- `pop` of a byte removes it, decrementing count
- `pop` on an empty ring answers `ERR empty`
- `dump` always returns exactly `count` bytes

## Known-bad artifact family

`examples/bad/` contains ≥ 5 single-edit mutants of the good firmware. The
script `judge/mutants.py` generates them from `examples/good/` by exact line
edit, so each mutant differs from the good artifact by one line:

| mutant | edit | gate that must fail |
|---|---|---|
| `ring-off-by-one` | ring-full test `>` instead of `>=` | `shell` (row mask) |
| `ring-drop-newest` | overflow advances `tail` instead of `head` | `shell` |
| `ring-count-drift` | `count += 2` on every push | `shell` |
| `crc-poly` | reflected polynomial `0xEDB88320` -> `0x82F63B78` | `crc_oracle` |
| `crc-no-xorout` | remove the final XOR-out | `crc_oracle` |
| `crc-init` | initial value `0xFFFFFFFF` -> `0` | `crc_oracle` |
| `crc-shift-dir` | register shifts left instead of right | `crc_oracle` |
| `uart-no-init` | `uart_init()` returns before touching hardware | `boot` |
| `uart-rx-inverted` | RX-FIFO-empty flag tested the wrong way | `shell` |
| `shell-unknown-ok` | unknown commands answer `OK` not `ERR` | `shell` |
| `shell-bad-hex-accepted` | malformed hex accepted instead of `ERR bad hex` | `shell` |
| `startup-no-reset` | reset vector points at `Default_Handler` | `boot` |
| `startup-bad-sp` | initial stack pointer is `0` | `boot` |
| `build-broken` | `#if 0` ahead of the entry function body | `build_clean` |

Every mutant must fail at least one gate. Exactly one mutant
(`build-broken`) is allowed to be caught by the build alone; every other
must be caught by a behavioural gate (`boot`, `shell`, `crc_oracle`).
`judge/selftest.sh` runs all of them, prints the kill rate split into
behavioural and build-only kills, and exits non-zero if the behavioural
kill rate is below 90%.

Three earlier mutants were removed as *equivalent under QEMU* — the judge
could never observe them, so a survival told us nothing:

- `uart-no-rx` (RXE bit cleared): QEMU's pl011 does not gate reception on
  `CTL.RXE`; bytes arrive anyway. Replaced by `uart-rx-inverted`.
- `startup-no-bss` (`.bss` clear skipped): QEMU zeroes emulated SRAM at
  reset, so `.bss` reads as `0` regardless. Replaced by `startup-no-reset`.
- `startup-no-data` (`.data` copy skipped): the reference firmware's
  `.data` section is empty, so the copy loop is a no-op. Replaced by
  `startup-bad-sp`.

## What this demo does not prove

- Nothing about real hardware: clock speed, pin drive, actual baud rates,
  silicon errata, and radio/analogue behaviour are all out of reach of an
  emulator.
- The UART is looped back by QEMU in software; there is no second device on the
  other end and no framing error, overrun or break handling is exercised.
- Timing is not measured. A firmware that answers slowly still passes, as long
  as it answers within `SHELL_S`.
- Passing gates mean the artifact behaves as specified, not that it is the
  firmware you would ship.
