# S6ED regression suite

```
make check       # T0 only: static invariants, no emulator          ~0.2 s
make gate        # the Gate: the headless openMSX sessions           ~30 s
make test        # both -- run before calling an integration done    ~30 s
make selftest    # put each historical defect back, prove it is caught ~35 s
make testall     # all three in one run, every check printed         ~75 s
```

All of them from `CODE/`. Or directly:
`TEST/runtests.py [--all|--static|--gate|--selftest] [-k NAME]`. Exit code is 0
only when every check passes.

Nothing short-circuits: every section asked for runs to the end and every check
is printed, pass or fail, so one `make testall` shows the whole picture. The
only exception is a build that does not assemble, which leaves nothing to test.
`-k` filters cases by name and mutations by name or by the cases they hit.

## Why this exists

Every non-trivial defect in this project was found empirically, with the emulator,
*after* it shipped into `dev` -- and none of them was found by the feature that
introduced it. The line directory overwrote `DISPKEY`; the clock left pixel
residue; the free list leaked 161 bytes per keystroke pair; the painted selection
range overlapped somebody else's scratch. Each was diagnosed with a one-off `.tcl`
that was then thrown away, so the project accumulated knowledge and no detection.

The Gate is that detection. It is not coverage: it is a fixed set of invariants
that runs at the end of **every** integration, whatever was touched.

## The Four Anti-Regression Rules

Every new test or code change must satisfy the four rules documented in [`AGENTS.md`](file:///Users/armandoperezabad/Code/brew/S6ED/AGENTS.md):

1. **Mandatory Green Baseline:** A mutation test in `selftest.py` only proves a catch if all expected checks are 100% green on the clean build first. A mutation caught by a check that was already failing is reported as a self-test failure (`BASELINE NOT GREEN`).
2. **Deterministic Race & Timing Tests:** Race conditions between the keyboard matrix and BIOS ISRs must be tested deterministically. Turn off host-clock dependencies (`CLOCK=0`) and use multi-pass bursts (e.g. 4 passes across the key row) to sweep the CPU/ISR phase window. Never rely on an isolated single keypress.
3. **Dual-Path Arbitration (First-Come, First-Served):** Whenever direct hardware polling (`CHKACNT`) and BIOS buffered ISR input (`TRNGRPH`) coexist for multi-region compatibility, whichever path triggers first must claim state ownership (`LASTGRP`) and actively suppress the secondary path.
4. **Full Lifecycle Verification:** Test initialisation fallbacks (e.g. missing assets in `B3`), steady-state editing, and clean exit teardown back to MSX-DOS (`G12`, checking screen mode, palette, and colors).


## Layout

| File | What it is |
|---|---|
| `runtests.py` | driver and CLI |
| `static.py` | T0 checks: build, image end, variable placement, record layout, lints |
| `gate.py` | the eleven runtime cases |
| `cases.py` | case base class, fixture helpers |
| `harness.py` | one openMSX session: disk, generated `.tcl`, run, dumps |
| `keys.py` | MSX key matrix and the input timeline |
| `vram.py` | Screen 6 decoding, pixel diffs, glyph comparison |
| `symbols.py` | `.sym` parser and source attribution |
| `mutations.py`, `selftest.py` | the self-test |
| `data_baseline.txt` | data defined outside `VARS.Z8A`, reviewed and classified |
| `out/` | per-case disks, scripts, logs and dumps (gitignored) |

## The Gate

Every case names the defect it was derived from in its `origin` field.

| Case | Invariant | Derived from |
|---|---|---|
| G1 | no editing path writes into the program image | line directory pinned at `#4000` |
| G2 | saving twice over an existing file | `DCREATE` without `LD B, 0` |
| G3 | exhaustion truncates, stays alive, refuses losslessly | `STORLINE`/`APPSEG`, `NEWREC JP C, ERRMEM` |
| G4 | deleted records come back through the free list | `LINEDEL` abandoning the record |
| G5 | every clock cell is exactly its glyph | `HMMV` byte truncation |
| G6 | no hook of ours, stack stays put | `H.TIMI` pointing into page 1 |
| G7 | the screen is a pure function of document state | painted selection range overlap |
| G8 | every CFG key parses with spaces around `=` | `CFGVAL` bare prefix match |
| G9 | insert and join round-trip through `DIRBANK` | `DIRBANK` destroying `HL` |
| G10 | Enter under AUTOALIGN writes no trailing spaces | `.TRUNC` stretching the head |
| G11 | batch insert and per-character insert agree | `EDINSRUN` rewrite |
| G12 | screen mode, width, colors and VDP palette restored at exit | palette and text mode corruption in DOS |
| B2 | four VRAM font tables match `RES/FONTS.BIN` | font loading from `S6ED.FNT` |
| B3 | fallback to BIOS ROM charset when `S6ED.FNT` missing | missing font asset degradation |
| F1 | vertical scroll limits and render purity | `YMMM` scroll blit vs `REDRAW` |
| F2 | held cursor key collapses queued repeats | repeat coalescing via `KEYRUN` |
| D1 | insertion at start, mid-line, and col 79 boundary | `EDINSCHR` shift and boundary clamping |
| D2 | line splitting on Enter at start, middle, and EOL | `EDNWLIN` record reservation and split |
| D3 | backspace in mid-line, at col 0 join (WRAP_DEV), and doc start | `EDDELBK` deletion and `EDJNDEV` join |
| D4 | delete in mid-line, at EOL pull (WRAP_DEV), and EOF | `EDDELCHR` deletion and `EDDELDV` pull |
| D5 | word delete left (GRAPH+BS) and line delete (Ctrl+Y) | `ACTDWLFT` scanner and `ACTDLS` recycling |
| D6 | cascade paragraph reflow across lines in WRAP_TXT | `REFLOW` word pull up to 80 cols |
| D7 | soft tabs: dynamic tab stops and raw tab expansion on load | `ACTTAB` space formula and `FILEIO` tab parser |
| D8 | Spanish characters via GRAPH matrix combos and dead-key state machine, each accent delivered exactly once | `CHKACNT` matrix scanner, `TRNGRPH` claim and `TRNDEAD` |
| D9 | suppress KANA mode and force physical LED off in Boosted_MSX2+_JP | `MAINLOOP` / `KANARST` PSG R15 bit 7 control |
| D10 | markdown and lite markup: cycling, delimiters, selection wrapping | `ACTCYCMK`, `INSDELIM` and `WRAPSEL` |
| H8-H16 | corrupt `S6ED.DAT` (magic, version, NUMBLKS, truncation, LENGTH, BLKID) aborts with a message, never a hang | Fase C1: unvalidated container loader |
| H17 | padded container loads correctly via `DSEEK` to DATAOFF | Fase C1: table-driven multi-block loader |
| E1 | multi-line cut removes lines with clean screen | `ACTCUT` and `ACTDLS` multi-line deletion |
| E2 | multi-line paste with CRLF splits host line | `ACTPAST` run inserter and `PSTNL` break |
| E3 | extending selection across viewport edge scrolls cleanly | `ACTSLMD` motion and scrolling diffs |
| E4 | Ctrl+A select-all and DEL leaves single clean empty line | `ACTSELAL` full document select and delete |
| E5 | typing printable character replaces active selection | `DISP.Z8A` `ACTDLS` call before insertion |
| E6 | word selection (Shift+Graph+Right) and page selection | `ACTSLWRT` word bounds and `ACTSLPGD` page |
| E7 | clipboard limit clamps copy to CLIPMAX (2048 bytes) | `ACTCOPY` buffer bound and memory isolation |
| I1 | auto-detect UNIX LF on load and preserve pure LF on save | `FILELOAD` standalone LF and `FILESAVE` LF |
| I2 | auto-detect DOS CRLF on load and preserve CRLF on save | `FILELOAD` CRLF delimiter and `FILESAVE` CRLF |
| I3 | convert DOS document to UNIX on save via EOL=UNIX | `PARSEOL` `AUTOLOD=0` and `SAVEEOL=1` |
| I4 | convert UNIX document to DOS on save via EOL=DOS | `PARSEOL` `AUTOLOD=0` and `SAVEEOL=0` |

**G7 is the general one.** A full `REDRAW` repaints from the document alone, so
comparing the screen before and after one is a test of every differential painter
at once -- `RENDIFF`, `SELDIFF`, `SELPRE`/`SELPOST`, `KEYRUN`, `DRWSTAT` -- with no
golden images to go stale. Apply it to any new editing path.

## How the harness works

Build, write a fixture disk from a fresh `RES/DOS2.DSK`, generate the `.tcl` from
the `.sym` the build just produced, run openMSX headless, read the log and the
dumps from the shell. Three things are load-bearing:

1. **`set renderer none`.** Not an optimisation: with a window, openMSX *stops*
   when it is not the foreground app, and a frozen emulator is indistinguishable
   from a program that never booted. Measured: ~380 emulated seconds per wall-clock
   second headless, against ~2 with a window. Nothing here needs a picture.
2. **The schedule is relative to T0**, the first time the editor reaches `MAINLOOP`
   with its own opcodes still there -- never an absolute boot time. A slower fixture
   or a different machine changes nothing.
3. **Every sample is taken at a breakpoint in our own code**, gated on a code
   signature *and* `SCRRDY`. A timer sample catches the DOS 2 kernel over page 0 or
   the Disk ROM over page 1 and returns phantom values.

Verdicts come from the disk (`dsktool E` + compare), from RAM at a breakpoint, from
`Main RAM` (every mapper segment at once, so `DIRSEG` can be walked without
banking), and from VRAM.

## Adding a case

Subclass `Case` in `gate.py`: give it `name`, `desc`, `origin`, a `fixture`, a
`timeline` and a `verify`. The timeline is a small DSL -- `press('DOWN',
mods=['SHIFT'])`, `text('ABC')`, `snap('label', vram=True)`. Key holds are
0.25 s down / 0.35 s gap; shorter holds drop keystrokes silently. `press`
takes a `tail=` override for the pause after the modifier comes back up, which
is how D8 walks a keystroke into a window only a few microseconds wide.

Then **add a mutation** to `mutations.py` that breaks what the case protects, and
check `make selftest` goes red without it. A case whose failure has never been
observed is not yet a test.

The self-test establishes the **baseline** first: every check a mutation expects
to redden must be green on the clean build, otherwise the mutation is reported
as a failure rather than as a catch. `mut/d8-accents` spent a while passing
through a `D8/content` that was already red, which proves nothing. When the
Gate has just run, its verdicts are reused as that baseline, so `make testall`
does not pay for the same sessions twice.

A case whose defect is a **race** needs more care, because the emulator is
deterministic but the host clock is not: with `CLOCK=1` the colon blit moves
MAINLOOP's phase from run to run and the same timeline reproduces the defect
only sometimes. Turn the clock off in the case's `cfg` and tune the timeline
until the mutation is caught on every run -- D8 does both, and the comment on
the case records what was measured. If a later change to MAINLOOP moves the
phase, `make selftest` will say NOT CAUGHT: that is the signal to re-tune the
timeline, not to delete the case.

## Known limits

- The Gate covers core invariants, fonts, vertical scroll, core editing
  semantics (D1-D6), accents, tabs and markup (D7-D10), the full selection &
  clipboard subsystem (E1-E7), the EOL round-trips (I1-I4), the `S6ED.DAT`
  container loader (H6, H8-H17) and the window engine (H7, H18-H20). Suites B
  (themes, bad asset fallback) and F (status bar, clamping) are not yet
  implemented.
- Everything runs on the 128 kB `Philips_NMS_8250`. Cases that need the 2 MB
  machine set `machine = MACH_2MB` explicitly.
- `type` goes through the BIOS buffer, so it cannot produce modifiers or cursor
  keys. Use `press` for those.
