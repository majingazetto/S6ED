# SXED regression suite (S6ED + S2ED)

```
make check       # T0 only: static invariants, no emulator          ~0.2 s
make gate        # the S6 Gate: headless openMSX on an MSX2          ~30 s
make test-s2     # the S2 Gate: headless openMSX on an MSX1          ~14 s
make test        # static + both gates -- before calling a job done  ~45 s
make selftest    # put each historical defect back, prove it is caught
make testall     # all of it in one run, every check printed
```

All of them from `CODE/`. Or directly:
`TEST/runtests.py [--all|--static|--gate|--s2|--selftest] [-k NAME]`. Exit code
is 0 only when every check passes.

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
| `gate.py` | the S6ED runtime cases (Screen 6, MSX2) |
| `gate_s2.py` | the S2ED runtime cases (Screen 2, MSX1) |
| `pattern.py` | Screen 2 expectation computed from `S2ED.FNT` + the document |
| `cases.py` | case base class, fixture helpers |
| `harness.py` | one openMSX session: disk, generated `.tcl`, run, dumps |
| `keys.py` | MSX key matrix and the input timeline |
| `vram.py` | Screen 6 decoding, pixel diffs, glyph comparison |
| `symbols.py` | `.sym` parser and source attribution |
| `mutations.py`, `selftest.py` | the self-test |
| `data_baseline.txt` | data defined outside `VARS.Z8A`, reviewed and classified |
| `out/` | per-case disks, scripts, logs and dumps (gitignored) |

## Two targets, one harness

`CORE/` is shared between S6ED and S2ED, so a change to it has to be checked on
both. A `Context` carries the target: the file-name prefix, the `.sym`, the
assembler include path (which is also how the harness resolves a source file --
`RENDER.Z8A`, `UI.Z8A` and `SCROLL.Z8A` exist in both `S6/` and `S2/`) and the
openMSX machine. A mutation may name `'target': 'S2ED'` and is then applied,
built and measured over there.

**The S2 gate is verified differently, and it is the stronger method.** The S6
gate's general case, `G7/render-pure`, forces a full `REDRAW` and diffs the
screen against itself: that proves the differential painters agree with the
bulk painter, and nothing about whether either is right. On Screen 2 the whole
pipeline is closed-form --

    cell(c) = FONT4H[text[2c]] | FONT4L[text[2c + 1]]
    FONT4L  = FONT4H with the nibbles swapped

-- so `pattern.py` **computes** the pattern table the VDP should be holding
from `S2ED.FNT` and the document text, and the case compares byte for byte. No
golden images, so nothing can be blessed by accident.

That difference is not theoretical: `mut/s2-rendiff-hit` (the differential
painter's cache-hit path repaints nothing) **passes `render-pure`** -- the stale
row survives the forced REDRAW, so the two screens are identically wrong -- and
is caught only by `S2-8/matches-document`. Measured, 2026-09-21.

### The S2 cases

| Case | Derived from |
|---|---|
| `S2-1-render` | round 1: `RENDEROW` called `COMROW` with `B` destroyed, so every row composed on top of row 0 |
| `S2-2-attrs` | round 2: `FILELOAD` cleared the attribute half from the S6 offset, leaving 16 dirty bytes per record -- the yellow bands |
| `S2-3-cursor` | round 2: a colour-nibble swap cannot invert half a cell, so the cursor covered two characters |
| `S2-4-select` | round 2: the same cause seen through `SELDIFF`, whose one-column deltas cancelled each other out |
| `S2-5-band` | round 2: `CORE` bounded the cursor with `SCRROWS` where it meant `ROWSVIS` |
| `S2-6-deltype` | round 3: `EDDELBK` / `EDDELCHR` ran to a literal 79 and poisoned the last text column, after which typing was refused |
| `S2-7-enterbot` | round 3: `EDNWLIN` repainted the split head at a literal row 23 -- the status bar |
| `S2-8-renderpure` | the general net: edits, then a forced REDRAW, compared both ways |
| `S2-9-margin` | the right margin: a full line clamps the cursor to its last column, so an edit there is an append, not an insert one place early |
| `S2-10-theme` | the theme integration: `THEME=` rewrites `VCOLTXT..VCOLBG`, and text, chrome and border follow |
| `S2-11-about` | W1: with no command engine and no off-screen VRAM a window composes in the RAM shadows, so a save or a restore off by one cell corrupts the document under it permanently |
| `S2-12-dialog-undo` | `WSVBUF` moved into the TPA next to the undo ring; only a run can prove two allocations do not overlap |
| `S2-13-shadow` | the drop shadow was a hardcoded `#11` -- black on black, visible on one theme of four |
| `S2-14-markup` | `MARKUP=MD` shipped untested; `ATRMARK` is tested last so a delimiter on an odd column gives way to the content sharing its cell |
| `S2-15-quit` | W2: `ACTQUIT` went straight to `TERM`, so ESC threw the document away without asking |
| `S2-16-menu` | W4: `MNUENT` was the last `IFDEF S2ED` in the menu path -- SELECT and F1..F5 opened nothing, and the item indices have to match S6ED's because the dispatch below them is shared |
| `S2-17-menu-nav` | W4: switching menus is a close, a re-highlight and an open; miss the un-highlight and the inverted titles pile up along the bar, which no check that only looks at the window can see |
| `S2-18-goto` | the first window with an input field.  Its viewport maths centres on `ROWSVIS / 2`, which is 11 here and 12 on S6ED, so `mut/goto-scrrows` is a mutation only this gate can catch |
| `S2-19-select-lines` | `SELPAIN` loaded `IX` once and trusted it across `SELXOR`, whose contract is clobbers-all; `PATINV` really does use `IX`, so a selection across lines painted rows it did not cover.  S6ED's `LMMV` leaves `IX` alone, so `mut/s2-selpain-ix` is catchable only here |

Two traps this suite met while being built, both worth knowing before adding a
case:

* **The cursor blinks.** `MAINLOOP` toggles `BLNKPH` every 20 JIFFY ticks. The
  first version of `S2-3` sampled five times at an even spacing that worked out
  to exactly two toggles, so every sample landed in the same phase and the case
  failed against a cursor that was working. Samples are now unevenly spaced,
  each is checked against its own `BLNKPH`, and the last one is taken right
  after a keystroke, which ends in `.DRAWCUR` and leaves the cursor up by
  construction.
* **A snapshot stops emulated time, and a keystroke can disappear into it.**
  The Tcl breakpoint handler reads sixty variables with the machine halted, so
  no VBLANK happens while it runs -- and the keyboard ISR only samples the
  matrix on a VBLANK. A `keymatrixdown` / `keymatrixup` pair that both land
  inside that window is **never seen**: the key did not fail, it did not
  happen. Snapshots wait for a breakpoint while keys fire on absolute times, so
  the drift accumulates down a long case. Measured while building `S2-18`: the
  RETURN closing the ninth dialog vanished, deterministically, and a second
  RETURN pressed immediately after it worked. Both goto cases now open every
  step with `t.wait(1.0)` and say so in a comment, because it reads like
  padding and is not.
* **A `WINPOLL` gate samples whichever modal got there first.** The breakpoint
  is armed at a moment in the timeline and fires at the next hit, and every
  modal loop polls `WINPOLL` continuously -- so a snapshot armed between two
  keystrokes catches the window that is open *then*, not the one the case is
  about. It cost a whole suite run when W4 moved About behind the Help menu:
  `S2-11`, `S2-12` and `S2-13` pressed F5 and sampled the dropdown. Two rules
  came out of it. Arm the gate **after** every key that leads to the window you
  mean, and make the check **name that window**: `S2-16/open` asserts
  `WINR/WINC/WINNR/WINNC`, because `WINACTV == 1` is equally true of the Quit
  dialog, which is what a stubbed-out `MNUENT` leaves the timeline's ESC to
  open -- and `mut/s2-menu-stub` walked straight through the first version of
  that check.
* **An operation that ends in `REDRAW` blinds the sample.** `S2-8` originally
  ended with BACKSPACE at column 0, which in `WRAP_TXT` cascades `REFLOW` and
  finishes with a full repaint microseconds before the snapshot -- a mutation
  that dropped a scroll's VRAM push went straight through it. The timeline now
  ends with a mid-document split.

## The S6 Gate

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

## The trap that costs the most time

`make selftest` **mutates the sources in place** and restores them in
`__exit__`. Kill the run -- `pkill`, Ctrl-C, a timeout -- and the tree is left
mutated with a `.mutbak` beside it. And `--gate` **does not build**, so a gate
run afterwards reads whatever `.COM` is on disk, which after any `make testall`
is the binary of the *last mutation*. On 2026-09-21 those two together produced
three identical "reproductions" of a regression in `E4` and `E7` that did not
exist: `mut/e4-selall-del` had survived in `ACTSELAL`.

After an interrupted self-test, before believing any gate result:

```sh
git status                       # sources clean?
find . -name '*.mutbak'          # nothing left behind?
cd CODE && make build dsk s2     # rebuild; --gate will not do it for you
```

A worktree is no escape: one created outside the workspace cannot find
`msxtools/bin/dsktool`, and one that has not been built reports **PASS**, so a
bisect in it measures nothing at all.

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
