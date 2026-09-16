# S6ED regression suite

```
make check       # T0 only: static invariants, no emulator          ~0.2 s
make gate        # the Gate: 11 headless openMSX sessions            ~10 s
make test        # both -- run before calling an integration done    ~10 s
make selftest    # put each historical defect back, prove it is caught ~5 s
```

All of them from `CODE/`. Or directly: `TEST/runtests.py [--static|--gate|--selftest] [-k NAME]`. Exit code is 0 only when every check passes.

## Why this exists

Every non-trivial defect in this project was found empirically, with the emulator,
*after* it shipped into `dev` -- and none of them was found by the feature that
introduced it. The line directory overwrote `DISPKEY`; the clock left pixel
residue; the free list leaked 161 bytes per keystroke pair; the painted selection
range overlapped somebody else's scratch. Each was diagnosed with a one-off `.tcl`
that was then thrown away, so the project accumulated knowledge and no detection.

The Gate is that detection. It is not coverage: it is a fixed set of invariants
that runs at the end of **every** integration, whatever was touched.

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
0.25 s down / 0.35 s gap; shorter holds drop keystrokes silently.

Then **add a mutation** to `mutations.py` that breaks what the case protects, and
check `make selftest` goes red without it. A case whose failure has never been
observed is not yet a test.

## Known limits

- The Gate covers core invariants, fonts, vertical scroll and core editing
  semantics (D1-D6). Suites B (themes, bad asset fallback), D (accents, tabs,
  markup), E (the rest of clipboard), F (status bar, clamping), G (EOL
  round-trips, exit to DOS) and H (keymap profiles) are specified in
  `informe_test_plan_s6ed.md`.
- Everything runs on the 128 kB `Philips_NMS_8250`. Cases that need the 2 MB
  machine set `machine = MACH_2MB` explicitly.
- `type` goes through the BIOS buffer, so it cannot produce modifiers or cursor
  keys. Use `press` for those.
