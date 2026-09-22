# Go to Line — the first interactive window, on both targets

> **Status:** implemented 2026-09-22 on `feat/sxed-gotoline`. See §12 for what was built and what changed on the way. Supersedes
> `.memory/project_s6ed_gotoline_spec.md` (2026-09-21), which predates the SXED
> dual-target split and is wrong in three places — see §1.3.
>
> **Scope:** `Ctrl+G` / Edit > Go to Line on S6ED **and** S2ED, built as a
> reusable text-input widget rather than as one dialog.

---

## 1. Why this one, and why now

### 1.1 It is the first window with an input field

`DOABT` has no controls and `DOQIT` has two buttons. Neither accepts a
character. Go to Line is the smallest thing that forces the missing widget into
existence: a field, a caret, digits, Backspace, ENTER and ESC.

### 1.2 Why not start with Find or Save As

Measured against what each one drags in besides the widget:

| Candidate | Extra machinery |
|---|---|
| **Go to Line** | `ATOI16` (~25 B) and `GOTOLN` (~90 B of arithmetic). Nothing else. |
| **Find** | a search engine over the mapper — walk the directory, bank each record, compare, report line and column — plus *Find Next* state and a "not found" path |
| **Save As / Open** | FCB paths, error strings, **and a second modal on top of the first** ("file exists, overwrite?"); Open also needs "discard changes?" |
| **Keyboard Help** | nothing — it is a longer About and does not advance the widget |

The decisive one is the **nested modal**. `WSAVE` does `LD DE, WSVBUF`: there is
**one** saved background, no stack, and S6ED likewise keeps a single off-screen
region. Save As cannot ask a follow-up question without either a second buffer
or a re-entrant save. Go to Line never nests, so the widget can be designed
without solving nesting at the same time.

Two supporting reasons: the widget's contract should be fixed by its simplest
consumer, not by the filesystem; and Go to Line is the only candidate whose
**action already exists** in CORE (`SETCURY`, `TOPLINE`, `REDRAW`), so it is
verifiable headlessly with no disk fixtures and no read-back.

### 1.3 What the old spec got wrong

1. It centres the viewport with **`SCRROWS`** and a literal row **11**. On S2
   `SCRROWS` is 24 and the text band is 22. This is the exact defect class of
   round 3, and T0 `target-params` would reject the literal in `CORE/` today.
2. It puts `DOGOTOL` in `CODE/SRC/WINDOW.Z8A`, which no longer exists — there
   are two, one per target.
3. It gives geometry in pixels, which only describes S6ED.

Everything else in it survives: the modal flow, the clamp, the centring policy,
`ACGOTOL EQU 59` (**still free**: `ACMAX` is 59 today) and the `INPBUF` /
`INPLEN` work area.

---

## 2. Architecture — three pieces, two of them per target

```
        page 1 (.COM)                     page 2 (FTRSEG container)
    ┌──────────────────────┐          ┌──────────────────────────────┐
    │ ACTGOTO   (CORE)     │  FCALL   │ DOGOTO   (S6/ or S2/WINDOW)  │
    │   CHKUNSEL           │ ───────► │   WINOPEN                    │
    │   FCALL DOGOTO       │          │   WINEDIT  ◄── the widget    │
    │   CY=1 → RET         │ ◄─────── │   WINCLOS                    │
    │   GOTOLN  (CORE)     │  HL = N  │                              │
    │   REDRAW / DRWSTAT   │          └──────────────────────────────┘
    └──────────────────────┘
```

**The action must run in page 1.** `GOTOLN` writes `TOPLINE`/`DOCLINE` and calls
`REDRAW`, which needs the text segments banked at page 2 — not `FTRSEG`. This is
the same split `DOMNU` already uses, and there it is a convention; here it is a
requirement.

`DOGOTO` returns:

- `CY = 1` — cancelled (ESC, or ENTER on an empty field).
- `CY = 0`, `HL` = the **1-based line number the user typed**, unclamped.
  Clamping is `GOTOLN`'s job, in page 1, where `TOTLINES` means something.

---

## 3. `WINEDIT` — the widget

One implementation per target, **identical contract**. This is the deliverable
that outlives Go to Line: Find and Save As change only the character class.

```
; - WINEDIT ----------------------------
; - MODAL TEXT INPUT FIELD. RUNS ITS OWN KEY LOOP AND RETURNS WHEN THE
; - USER ACCEPTS OR CANCELS. THE CALLER HAS ALREADY OPENED THE WINDOW.
; - IN:  B  = FIELD ROW      (SCREEN ROW ON S2 / RELATIVE Y IN PIXELS ON S6)
; -      C  = FIELD COLUMN   (CHAR COLUMN ON S2 / RELATIVE X IN PIXELS ON S6)
; -      D  = FIELD WIDTH IN CHARACTERS (1..INPMAX)
; -      E  = CHARACTER CLASS (ED_DIGIT = 0, ED_FILE = 1, ED_TEXT = 2)
; - OUT: CY = 1: CANCELLED.  CY = 0: ACCEPTED, (INPBUF) HOLDS ASCIIZ,
; -      (INPLEN) ITS LENGTH
; - CLOBBERS: ALL
; -
```

### 3.1 Focus has three positions, not two

`WINSEL` = `ED_FFLD` (0, the field — the default), `ED_FOK` (1) or `ED_FCAN`
(2). `TAB` / `CLEFT` / `CRIGHT` cycle them.

This is what SPACE forces. SPACE cannot mean "accept" while the field has the
focus, because the day `ED_TEXT` exists a space is a character someone is
typing into a search box — so **SPACE activates the focused control, and the
field is a control**. In the field it does nothing; on a button it presses it.
A two-position focus would have had to special-case the character class, which
is how a widget stops being reusable.

The field's focus indicator is the caret; when a button has the focus, that
button wears the selected style and the other does not.

Behaviour, the same on both:

| Key | Focus = field | Focus = OK / CANCEL |
|---|---|---|
| a character of the class | appended if `INPLEN < width`, else ignored | ignored |
| `BS` (`#08`) | removes the last character if any | ignored |
| `CR` | accept | accept on OK, cancel on CANCEL |
| `' '` | **ignored** | same as `CR` |
| `ESC` | cancel | cancel |
| `TAB` / `CLEFT` / `CRIGHT` | move the focus, repaint | move the focus, repaint |
| anything else | ignored | ignored |

An **empty field cancels** on accept, whatever the focus: "go to no line" has no
other reading.

`ED_DIGIT` accepts `'0'..'9'`. `ED_FILE` and `ED_TEXT` are **declared now and
not implemented** — the class byte exists so the callers that need them do not
change the signature later. The widget rejects an unknown class with `CY = 1`.

**No cursor keys inside the text.** Editing is append and Backspace only. A
caret that moves inside the field means insert, delete and a scroll offset, and
none of the three consumers needs it. If Find later wants it, it is an addition
to the widget, not a change to its contract.

**The caret** is drawn at the insertion point and is part of the field repaint:

- **S6ED:** a `COL_HI` block, `LMMV`, at `field_x + INPLEN * 6`.
- **S2ED:** the `'_'` glyph written through `WINPUTC` at the insertion column.
  It is a character, not an inversion, so it costs nothing extra and survives
  the ordinary cell repaint.

**Repaint granularity.** A keystroke repaints the field only:

- **S6ED** already has `WINUPD` (sub-rectangle blit) — one `WINVSY` then one
  `WINUPD` over the field box.
- **S2ED** needs a new one-row primitive, **`WDUMPR`** (~40 B): dump exactly one
  window row, pattern slice through `VDPDUMP` and colour slice through
  `COLDMPC`, which is `WDUMP`'s inner body with the loop removed. Measured
  cost for a 15-cell window: 16 cells × 8 = 128 pattern bytes plus 128 colour
  bytes at 29 T/byte ≈ **7.4 ms**, against ≈ 60 ms for a whole-window `WDUMP`.
  `WDUMPR` is a widget primitive, not a Go to Line one, and `DOQIT`'s button
  navigation can move onto it afterwards.

---

## 4. Geometry

### 4.1 S6ED (pixels, 512 × 212)

Unchanged from the old spec — it is still correct for this target.

| Element | Position |
|---|---|
| Window | `WINX = 156`, `WINY = 70`, `WINW = 200`, `WINH = 72` |
| Title | `"Go to Line"`, bold, `COL_HI` |
| Prompt | rel `Y = 20`, rel `X = 6`, normal, `COL_FG` |
| Field box | rel `X = 56..143`, rel `Y = 32..43` — 1-px `COL_UI` border, `CLR_BG` interior |
| Field text | rel `X = 60`, 5 characters at 6 px |
| `[  OK  ]` | rel `X = 36`, rel `Y = 50`, `WINBTS` style from `WINSEL` |
| `[CANCEL]` | rel `X = 108`, rel `Y = 50` |

### 4.2 S2ED (cells, 32 × 24)

| | Value |
|---|---|
| `WINR, WINC` | `8, 8` |
| `WINNR, WINNC` | `7, 15` |
| Save buffer | `(7+1) × (15+1) = 128` of the 170 cell-slots `WSVMAX / 9` allows ✓ |
| Content span | cells 9..21 → char columns 18..43, **26 characters** |
| Title row | `WINR` = 8, `"Go to Line"` in `VCOLHI` (the bar `WBOX` paints anyway) |
| Prompt | row 10, char column 18 — `"Line number (1-3232):"` is 21 ✓ |
| Field | row 11, char columns 20..25 (5 digits + caret), `VCOLTXT` so it reads as an inset against the `VCOLWIN` body |
| Buttons | row 13, `[  OK  ]` at char column 20, `[CANCEL]` at column 32 |

**The buttons are cell-aligned**, as `DOQIT`'s are: eight characters starting on
an even column own exactly four cells and the focus bar has no half cell hanging
off. The field starts on an even column for the same reason.

---

## 5. `DOGOTO` — the dialog

Identical on both targets but for the drawing calls.

1. `INPLEN = 0`, `INPBUF[0] = 0`, `WINSEL = 0` (OK focused).
2. Build the prompt: `"Line number (1-"`, then `TOTLINES` through **`B2D16`**
   (which returns `HL` at the first digit and `C` as the count — **no buffer
   needed**, so the old spec's 32-byte `GOTOPRM` is dropped), then `"):"`.
   Three writes, not one string.
3. `WINOPEN` with the title.
4. Paint prompt, empty field, both buttons; push the window.
5. `WINEDIT` with `D = 5`, `E = ED_DIGIT`.
6. `CY = 1` → `WINCLOS`, return `CY = 1`.
7. `CY = 0` and `WINSEL == 1` (CANCEL focused) → same as cancel.
8. Otherwise `ATOI16 (INPBUF)` → `HL`; `WINCLOS`; return `CY = 0`.

**`ATOI16` is new and goes in `CORE/GENERIC.Z8A`** (~25 B): ASCIIZ decimal →
`HL`, saturating at 65535. It cannot reuse `CFG.Z8A`'s `GETNUM`, which is
`IFNDEF S2ED` and lives in the container.

---

## 6. `GOTOLN` — the action, in `CORE/ACTION.Z8A`

```
; - GOTOLN -----------------------------
; - PLACE THE DOCUMENT AND THE VIEWPORT ON A LINE
; - IN:  HL = TARGET LINE, 1-BASED, UNCLAMPED
; - OUT: NONE
; - CLOBBERS: ALL
; -
```

1. Clamp `HL` into `[1, TOTLINES]`, then `DOCLINE = HL - 1`, `CURX = 0`.
2. **Already on screen** — `TOPLINE <= DOCLINE < TOPLINE + ROWSVIS` — leave
   `TOPLINE` alone and fall through to `SETCURY`. No jarring scroll for a jump
   of two lines.
3. **Otherwise centre:** `TOPLINE = DOCLINE - ROWSVIS / 2`, clamped into
   `[0, max(0, TOTLINES - ROWSVIS)]`, then `SETCURY`.

**`ROWSVIS`, never `SCRROWS`, and `ROWSVIS / 2`, never 11.** The two targets do
not agree: S6 centres on row 12, S2 on row 11, and S2's `SCRROWS` is 24 while its
band is 22 — so a literal is wrong on one target and a `SCRROWS` is wrong on the
other. `SETCURY` owns the `CURY = DOCLINE - TOPLINE` invariant; nothing here
touches `CURY` by hand.

`ACTGOTO` is then:

```
ACTGOTO   CHKUNSEL                  ; closes the undo burst, drops the selection
          FCALL DOGOTO              ; FTR-BUDGET comment required by T0
          RET C                     ; cancelled
          GOTOLN
          REDRAW
          JP DRWSTAT
```

---

## 7. Wiring

| Where | Change |
|---|---|
| `CORE/CONST_CORE.Z8A` | `ACGOTOL EQU 59`, `ACMAX EQU 60`; `INPMAX EQU 5`; `ED_DIGIT/ED_FILE/ED_TEXT EQU 0/1/2` |
| `CORE/ACTION.Z8A` | `ACTTBL` slot 59; `ACTGOTO`; `GOTOLN`; `.EDIMNU` gains `CP 8 → ACTGOTO` |
| `CORE/GENERIC.Z8A` | `ATOI16` |
| `CORE/KEYMAP.Z8A` | `CTRL_G, MODCTRL, ACGOTOL` in `KMAPSTD`, `KMAPEMAC`, `KMAPVIN` |
| `VARS.Z8A` | `INPBUF DEFS 6`, `INPLEN DEFB 0` — **7 bytes**, shared, not `IFDEF` |
| `S6/WINDOW.Z8A` | `WINEDIT`, `DOGOTO` |
| `S2/WINDOW.Z8A` | `WINEDIT`, `WDUMPR`, `DOGOTO` |

**Nothing changes in the menus.** Edit item 8 already exists on both targets with
accelerator `G`; the dispatch simply stops returning.

### 7.1 The WordStar problem — a decision, not an oversight

`CTRL_G` is **taken in `KMAPWS`** by `ACDELFW`, which is authentic WordStar
(`^G` deletes forward). It is free in STD, Emacs and Vi.

The old spec proposed `CTRL_J` for WordStar. **That is not viable:** `CTRL_J` is
not defined in `HARD.Z8A` and `#0A` is LF, deliberately absent from the table.
Of the codes that are defined and unused in `KMAPWS` — `CTRL_N`, `CTRL_O`,
`CTRL_P`, `CTRL_U`, `CTRL_V` — every one means something else in real WordStar,
and `CTRL_L` collides with `CLSKEY` (`#0C`).

**Decided: WordStar gets no Ctrl binding.** It reaches Go to Line through the
Edit menu (`F2`, then `G`), which works in every profile. Inventing a WordStar
key that WordStar does not have is worse than one profile reaching a feature
through the menu — and the profile may not survive anyway: removing WordStar
altogether is on the table, which is a second reason not to spend a keycode on
it.

Note the menu string says `^G` in all profiles. That is a pre-existing property
of a static menu table — several other accelerators already do the same — and
this spec does not change it.

---

## 8. Budget

Calibrated against the dialogs already in each container:

| | S6ED | S2ED |
|---|---:|---:|
| `DOQIT` (measured) | 293 B | 260 B |
| `WINEDIT` + `WDUMPR` (est.) | ~180 B | ~220 B |
| `DOGOTO` (est.) | ~320 B | ~260 B |
| **Container total (est.)** | **~500 B** | **~480 B** |
| Free now | 11.501 B | **1.688 B** |
| Free after | ~11.000 B | **~1.200 B** |

Page 1, both targets: `GOTOLN` ~90 B, `ATOI16` ~25 B, `ACTGOTO` ~25 B, keymap
and dispatch ~20 B → **~160 B** of image, against 4.240 / 3.167 B of free TPA.
`VARS` grows by 7 bytes.

`S6ED.COM` **will** change this time — `ACTGOTO`, `GOTOLN` and `ATOI16` are real
code in the shared image. That is expected and is not the byte-identity proof the
last three phases used.

---

## 9. Verification

### 9.1 Cases

**`H24-goto` (S6ED)** and **`S2-18-goto` (S2ED)**, same shape, geometry per
target. Fixture: 100 numbered lines.

| Step | Assertion |
|---|---|
| `Ctrl+G` | dialog open at `WINPOLL`, and the **geometry names this window** (`WINX/WINY/WINW/WINH`, `WINR/WINC/WINNR/WINNC`) — the W4 lesson |
| type `4`, `2` | the field shows `42` — compared against the computed font, not an image |
| `CR` | `DOCLINE == 41`; `TOPLINE` centred per `ROWSVIS`; `CURY == ROWSVIS/2`; `CURX == 0` |
| `Ctrl+G`, `8`, `8`, `ESC` | nothing moved: `DOCLINE` still 41, screen byte-identical to before |
| `Ctrl+G`, `9`,`9`,`9`, `CR` | clamped to the last line, `TOPLINE` clamped to `TOTLINES - ROWSVIS` |
| `Ctrl+G`, `0`, `CR` | clamped to line 1, `TOPLINE == 0`, `CURY == 0` |
| `Ctrl+G`, `1`,`2`,`BS`,`CR` | Backspace really removes: lands on line 1, not 12 |
| `Ctrl+G`, `CR` on an empty field | cancels; nothing moved |
| jump two lines down | `TOPLINE` **unchanged** — the "already visible" branch |
| `F2`, `G` | the menu route reaches the same dialog |

Every "nothing moved" compares the screen byte for byte against the snapshot
before, cursor blink forgiven — the `restored()` helper the S2 suite already has.

### 9.2 Mutations

| Name | Injected defect | Caught by |
|---|---|---|
| `goto-nodispatch` | `.EDIMNU` / `ACTTBL` never reaches `ACTGOTO` | `*/open` |
| `goto-noclamp` | `GOTOLN` skips the clamp | `*/clamp-high`, `*/clamp-low` |
| `goto-scrrows` | centring uses `SCRROWS` instead of `ROWSVIS` | `*/centred` on **S2 only** — which is the point |
| `goto-visible` | the "already visible" branch always centres | `*/no-scroll` |
| `goto-bs` | `WINEDIT` ignores Backspace | `*/backspace` |
| `goto-esc` | ESC accepts instead of cancelling | `*/cancel` |
| `goto-empty` | ENTER on an empty field jumps to line 0 | `*/empty` |

`goto-scrrows` is deliberately a mutation that **can only be caught on S2**. It
is the round-3 defect class, and having it in the suite is the point of running
two gates.

---

## 10. Explicitly out of scope

Find, Save As and Open. They inherit `WINEDIT` unchanged; what they still need
is theirs:

- **Find:** `ED_TEXT`, a search engine over the mapper, *Find Next* state.
- **Save As / Open:** `ED_FILE`, and **nested modals** — `WSVBUF` holds one
  background, so a confirmation on top of a dialog needs a second buffer or a
  re-entrant save. That is a separate piece of work and this spec does not
  prejudge it.

---

## 11. Decisions taken (2026-09-22)

1. **WordStar binding: none.** Menu only, `F2` then `G`. See §7.1.
2. **Field width: 5**, clamped in `GOTOLN`. `TOTLINES` tops out at 3.232 on the
   2 MB machine and 202 on a stock 128 kB one, so the fifth digit exists only to
   swallow a typo gracefully instead of dropping it.
3. **Buttons: yes**, `[  OK  ]` and `[CANCEL]`, with focus. ENTER and ESC do the
   whole job on their own, so the buttons are discoverability — but a window
   engine exists in order to have them, and `WINSEL` focus is already proven by
   `DOQIT` on both targets. The cost is ~60 B per target and it buys the
   convention every later dialog will follow.

The consequence of (3), settled while writing §3.1: focus has **three**
positions, because SPACE may only activate a control and the field is one. ENTER
on CANCEL cancels; an empty field cancels whatever the focus.


---

## 12. As built (2026-09-22)

### 12.1 Cost, measured

| | S6ED | S2ED |
|---|---:|---:|
| Container | 4,883 -> **5,538** B (+655) | 3,432 -> **3,904** B (+472) |
| `FTRFREE` | 11,501 -> 10,846 B | 1,688 -> **1,216** B |
| Image | 16,414 -> 16,609 B (+195) | 16,030 -> 16,225 B (+195) |
| `TPAFREE` | 4,240 -> 4,035 B | 3,167 -> 2,962 B |

The image grows by **exactly the same 195 bytes on both targets**, which is
what shared CORE code is supposed to look like. `VARS` grows by 10 bytes
(`INPBUF` 6, `INPLEN` 1, `EDROW`/`EDCOL`/`EDWID` 3). The S6 dialog came out
~155 B over the estimate and the S2 one ~10 B under.

### 12.2 Three things the spec did not foresee

1. **`WDUMPR` was not new code, it was `WDUMP`'s body.** `WDUMP` now loops over
   it, so the one-row and the whole-window paths cannot drift apart. Cheaper
   than writing a second dumper and strictly safer.
2. **The field geometry is derived, not given.** `EDGEOM` computes the box from
   `EDROW`/`EDCOL`/`EDWID` on S6 — four pixels left, two above,
   `(EDWID + 1) * 6 + 8` wide — so the widget owns its own frame and the dialog
   only says where the text goes. The spec's 88-px box became 44, which is what
   five digits and a caret actually need.
3. **The buttons stayed with the caller, by name.** `WINEDIT` calls `EDBTNS`,
   defined next to `DOGOTO`. There is one dialog with a field per target today;
   the day there are two, that becomes a pointer parameter. It is a seam, and
   it is documented as one in both files.

### 12.3 A defect found on the way, and fixed

`.EDIMNU` in `CORE/ACTION.Z8A` dispatched **five of its six items to the action
ID instead of the routine**: `CALL ACCUT` where `ACCUT EQU 46`, i.e.
`CALL #002E`, into the DOS zero page. Cut, Copy, Delete Line, Select All and
Deselect were all broken from the Edit menu on **both** targets; only Paste
(`ACTPAST`) named a routine. It assembles cleanly — the names differ by three
letters — and **no gate case had ever pressed an Edit menu item**, so nothing
saw it. `H23/edit-action` and `S2-17/edit-action` now press Select All and
assert `SELACT`, and `mut/menu-edit-id` puts the defect back.

### 12.4 A harness trap worth more than the feature

The first long version of both cases died mid-way with the editor stuck inside
the dialog, deterministically, at a different step in each run. The cause is
not in the editor: **a snapshot stops emulated time while Tcl reads its sixty
variables, and a keystroke whose down *and* up both land inside that window is
never sampled by the keyboard ISR.** It simply does not happen. Measured: the
RETURN that should have closed the ninth dialog was swallowed, and a second
RETURN pressed straight after it worked perfectly.

The drift accumulates because snapshots wait for a breakpoint while keys fire
on absolute times. Every step of both cases now opens with `t.wait(1.0)`, and
the comment in the timeline says why so nobody deletes it as padding.

### 12.5 Verification

`H24-goto-line` (12 checks) and `S2-18-goto` (13), nine mutations —
`goto-nodispatch`, `goto-scrrows`, `goto-visible`, `goto-bs`, `goto-esc`,
`goto-empty`, `goto-space`, plus `menu-edit-id` — all caught. **`goto-scrrows`
can only be caught on S2ED**: it centres on `SCRROWS / 2` instead of
`ROWSVIS / 2`, which is the same number on S6ED and two rows wrong on S2ED.
That is the round-3 defect class, and having it in the suite is the argument
for running two gates.

`make testall`: **587 checks, 0 failed.**
