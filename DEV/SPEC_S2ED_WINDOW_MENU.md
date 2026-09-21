# S2ED Window & Menu System — Design Specification

> **Status:** Approved 2026-09-21. W1 done (branch `feat/s2ed-window-engine`): window engine + `DOABT` + guards, gate case S2-11. W2/W4/W5 pending.

## 1. Objective

Port S6ED's complete window engine (`WINDOW.Z8A`), menu subsystem (`MENU.Z8A`), and modal dialogs (`DOABT`, `DOQIT`) to S2ED's TMS9918 / SCREEN 2 environment, so both targets reach feature parity on windows and menus.

---

## 2. What S6ED Has (V9938 / Screen 6)

| Component | File | Key Mechanism |
|---|---|---|
| Window engine | `S6/WINDOW.Z8A` (~1,127 lines) | Off-screen VRAM composition buffer at Y=768, background save buffer at Y=512, `HMMM` blits for show/restore, `LMMM` glyph blitting, `HMMV`/`LMMV` fills |
| Menu subsystem | `S6/MENU.Z8A` (~814 lines) | `DOMNU` modal loop, 5 dropdown menus with data tables, title XOR highlight, item painting, accelerators, `WINOPEN`/`WINCLOS` |
| Dialogs | Inside `WINDOW.Z8A` | `DOABT` (About), `DOQIT` (Quit confirmation), `WINBTN`/`WINBTS` buttons, `WINPRN`/`WINSTR`/`WINSTR3` text rendering |
| Dispatch | `CORE/ACTION.Z8A` | `ACTMENU`→`MNUENT` entry, runs `DOMNU` via `FCALL` into `FTRSEG` (page 2), returns menu/item indices for dispatch in page 1 |

### V9938 Features Used (NOT available on TMS9918)

| V9938 Feature | Usage | Count |
|---|---|---|
| `HMMM` (high-speed move) | `WINSAV`, `WINSHOW`, `WINRST`, `WINUPD`, shadow corners | ~8 calls |
| `HMMV` (high-speed fill) | `WINBAND`, `WINBOX` shadow bars, `WINBTN` body | ~6 calls |
| `LMMV` (logical fill) | Side borders (1px), button outer border | ~4 calls |
| `LMMM` (logical move) | `WINCHTR` glyph blit from VRAM font | ~1/glyph |
| `VDP_TXOR` logop | Menu title highlight toggle (row 0) | per-open |
| Off-screen VRAM (Y>212) | Composition buffer (Y=768), save buffer (Y=512) | permanent |
| 512 px width | All pixel coordinates; 4-px alignment for byte fills | everywhere |

**None of these exist on TMS9918.** The TMS has no command engine, no off-screen VRAM beyond the 16 KB address space, and no logical operations.

---

## 3. S2ED Current State (TMS9918 / Screen 2)

### Available Primitives

| Primitive | Location | Description |
|---|---|---|
| `VDPDUMP` | `S2/VDP.Z8A` | `OUTI; JP NZ` block write from RAM to VRAM |
| `COLDUMP` | `S2/RENDER.Z8A` | Expand COLMAP row ×8 into COLEXP, dump to CTBASE |
| `COMROW` / `COMCELL` | `S2/RENDER.Z8A` | Compose 32 cells from WORKBUF into PATSHAD + COLMAP |
| `PATINV` | `S2/RENDER.Z8A` | XOR 4-px column range in pattern shadow, dump to VRAM |
| `DRWMENU` | `S2/UI.Z8A` | Compose & dump menu bar (row 0, 32 cells, `VCOLUI` color) |
| `DRWSTAT` | `S2/UI.Z8A` | Build status bar text, compose row 23, dump |
| `WINPOLL` | `S2/UI.Z8A` | `CHSNS`/`CHGET` keyboard poll for modal loops |
| `WINKIL` | `S2/UI.Z8A` | Keyboard buffer flush via BIOS `KILBUF` |
| `VIDBANK` / `TXTBANK` | `S2/VDP.Z8A` | Bank `VIDSEG`/`FTRSEG` ↔ text segments at page 2 |

### Memory Map (VIDSEG = FTRSEG, 16 KB at page 2)

```
#8000  PATSHAD   6,144 B  Pattern shadow (24 rows × 256 B)
#9800  COLMAP      768 B  Color map (1 byte per cell)
#9B00  COLEXP      256 B  Staging for COLDUMP
#9C00  FTRBASE   5,120 B  Feature passenger container
#B000  FONT4H    2,048 B  High-nibble font
#B800  FONT4L    2,048 B  Low-nibble font
                -------
                16,384 B  exactly
```

**Free in FTRBASE:** ~4,038 B (5,120 − 1,082 CFG). This is where the window/menu code must live.

### Current S2ED Stub

```asm
MNUENT  IFDEF  S2ED
        RET                 ; ← MENUS DISABLED
        ELSE
        LD   A, (FTRSEG)
        LD   HL, DOMNU
        CALL FCALL
        ...
        ENDIF
```

`ACTHELP` → `RET`, `ACTQUIT` → straight to `TERM`.

### VRAM Map (TMS9918, 16 KB)

```
#0000  Pattern Generator  6,144 B (3 × 2,048)
#1800  Name Table            768 B (filled 0..255 ×3)
#1B00  Sprite Attr Table     128 B
#2000  Color Table          6,144 B (3 × 2,048)
#3800  Sprite Generator    2,048 B
```

**No off-screen VRAM.** Everything is visible or table space.

---

## 4. Architecture Decision: RAM Shadow Windows

> **The V9938 approach (off-screen VRAM composition + HMMM blit) is impossible on TMS9918. The replacement: compose windows entirely in the RAM pattern/color shadows (`PATSHAD` + `COLMAP`) and dump to VRAM the normal way.**

### 4.1 Background Save & Restore

S6ED saves the screen area behind a window to off-screen VRAM (Y=512) with one `HMMM`. On S2ED there is no off-screen VRAM. Instead:

- **Save:** Copy the rectangular region of `PATSHAD` + `COLMAP` that the window covers into a **temporary RAM buffer** (`WINSAV_P` + `WINSAV_C`) inside `FTRBASE`.
- **Restore:** Copy the saved buffer back to `PATSHAD` + `COLMAP`, then dump the affected rows to VRAM.

**Size budget:** A window covering R rows × C cells requires `R × C × 8` pattern bytes + `R × C` color bytes = `R × C × 9`. The largest S6ED dropdown is 10 items ≈ 11 rows × ~12 cells = 1,188 bytes. The About dialog ≈ 13 rows × 24 cells = 2,808 bytes. Both fit in FTRBASE.

### 4.2 Window Composition

Instead of painting to an off-screen VRAM buffer and blitting, windows are composed **directly into PATSHAD + COLMAP** at their screen position:

1. Save the background region.
2. Draw the window frame, body, text, buttons directly into the shadow.
3. Dump the affected rows to VRAM (`VDPDUMP` + `COLDUMP`).
4. On close: restore the saved background, dump again.

### 4.3 Text Rendering Inside Windows

S6ED's `WINCHTR` / `WINSTR` use `LMMM` to blit from VRAM font tables. On S2ED, the fonts are already in the RAM shadow (`FONT4H` / `FONT4L`), so text inside windows uses the same `COMCELL` mechanism the normal renderer uses, writing directly into the PATSHAD cells the window covers.

A thin wrapper `WINPUTC(row, col, char)` composes a cell pair at the window position, and `WINPUTS(row, col, string)` walks a string through it.

### 4.4 Drop Shadow

S6ED paints a 4-px drop shadow using `HMMV`. On S2ED, the color table offers a cheaper equivalent: **the cells at the window's right and bottom edges get a "shadow" color byte** (e.g., `#11` = black on black). This is 0 CPU cost and visually effective, since the shadow only needs to darken the background.

### 4.5 Menu Title Highlight

S6ED XORs the title cell in row 0 with `LMMV | VDP_XOR`. On S2ED, `PATINV` already does per-column XOR in the pattern shadow. Alternatively: swap the FG/BG nibbles of the title's cells in `COLMAP` and redump the row — color-level inversion is **per whole cell** here, which is fine for menu titles (they span complete cells).

---

## 5. Window Engine API (S2ED)

All routines live in `S2/WINDOW.Z8A`, phased into FTRBASE via `FCALL`.

| Routine | Parameters | Description |
|---|---|---|
| `WINOPEN` | `WINR`, `WINC`, `WINNR`, `WINNC`, HL=title | Save background, draw frame/title into shadow, dump |
| `WINCLOS` | (uses saved WIN vars) | Restore background, dump, clear WINACTV |
| `WINSHOW` | — | Dump the window's rows to VRAM |
| `WINPUTC` | B=row, C=col, A=char, D=attr | Compose single cell at window-relative (row,col) |
| `WINPUTS` | B=row, C=col, HL=ASCIIZ, A=color | Write string into window at (row,col) |
| `WINCLR` | B=row, C=col, D=count, A=color | Clear cells to spaces with given color |
| `WINHLIT` | B=row, C=col, D=count, A=color | Change color of cells without recomposing patterns |
| `WINPOLL` | — | Already exists in `S2/UI.Z8A` |
| `WINKIL` | — | Already exists in `S2/UI.Z8A` |

### Window Coordinates: Cell Units, Not Pixels

S6ED uses pixel coordinates (512-px wide screen). S2ED uses **cell coordinates** (32 cells wide × 24 rows):

```
WINR  = Window top row     (0..23)
WINC  = Window left cell   (0..31)
WINNR = Window height in rows
WINNC = Window width in cells
```

This simplifies everything: no pixel alignment, no sub-cell addressing.

### Window Variables

```asm
; WINDOW STATE (1-BYTE EACH, IN VARS.Z8A, IFDEF S2ED)
WINR    DEFB  0    ; WINDOW TOP ROW
WINC    DEFB  0    ; WINDOW LEFT CELL
WINNR   DEFB  0    ; WINDOW HEIGHT IN ROWS
WINNC   DEFB  0    ; WINDOW WIDTH IN CELLS
```

The existing shared variables (`WINACTV`, `WINSEL`, `WINRES`, `MNUID`, `MNUSEL`, `MNUITMC`) stay as they are — they are already in `VARS.Z8A`.

---

## 6. Menu Subsystem (S2ED)

### 6.1 Layout

```
Row 0:   S2ED | File  Edit  View  Options  Help
                ^^^^  ^^^^  ^^^^  ^^^^^^^  ^^^^
                F1    F2    F3    F4       F5

           ┌──────────────┐
Row 1:     │ New     ^N   │ ← Dropdown window (cells)
Row 2:     │ Open    ^O   │
Row 3:     │ Save    ^S   │
Row 4:     │ Save As      │
Row 5:     │──────────────│ ← Separator
Row 6:     │ Quit    ^Q   │
           └──────────────┘ (+ shadow on right/bottom)
```

### 6.2 Menu Tables

Same structure as S6ED but in cell coordinates:

```asm
; PER MENU: [WINC(1B), WINNC(1B), WINNR(1B), ITEMCNT(1B),
;            STBL_PTR(2B), ACCL_PTR(2B)]  = 8 BYTES PER MENU
```

Title positions (in column units within the 64-character menu bar):

```
File:     col 7,  width 4
Edit:     col 13, width 4
View:     col 19, width 4
Options:  col 25, width 7
Help:     col 34, width 4
```

### 6.3 Menu Flow (DOMNU for S2ED)

1. Highlight active menu title (nibble swap in COLMAP row 0).
2. `WINOPEN` at (row=1, col=title_col, width, height).
3. Draw all items into shadow via `WINPUTS`.
4. Dump to VRAM.
5. Modal key loop (`WINPOLL`):
   - UP/DOWN: move highlight (recolor one row, dump).
   - LEFT/RIGHT: close window, switch menu.
   - ENTER/SPACE: accept.
   - ESC: cancel.
   - Accelerator keys.
6. `WINCLOS` → restore background.
7. Return `D=MNUID, E=MNUSEL` to `MNUENT` dispatch (same as S6ED).

### 6.4 Item Highlighting

The selected item row changes its COLMAP cells to `VCOLUI` (inverse: foreground ↔ background). Unselected items use `VCOLTXT`. Only the two changed rows are re-dumped. No pattern recomposition needed — only color table updates.

---

## 7. Dialogs

### 7.1 DOQIT (Quit Confirmation)

```
        ┌──── Quit S2ED ────┐
        │                    │
        │ Exit to MSX-DOS?   │
        │ Unsaved changes!   │
        │                    │
        │ [ YES ]   [ NO ]   │
        └────────────────────┘
```

- Window: ~5 rows × 12 cells, centered.
- Two "buttons" drawn as text with inverse color.
- LEFT/RIGHT switches selection, Y/N accelerators, ESC cancels.
- Button highlight: swap COLMAP bytes for the button cells only, dump 1 row.

### 7.2 DOABT (About)

```
        ┌──── About S2ED ────┐
        │                     │
        │ S2ED - MSX1 64-Col  │
        │ Text Editor         │
        │                     │
        │ Display: 64x24      │
        │ Font: 4x8 custom    │
        │ Memory: Nextor      │
        │                     │
        │     [  OK  ]        │
        └─────────────────────┘
```

- Window: ~11 rows × 13 cells, centered.
- Single OK button.
- Any key closes.

---

## 8. Memory Budget

| Item | Bytes |
|---|---|
| Window engine (`WINOPEN`, `WINCLOS`, `WINSHOW`, `WINPUTC`, `WINPUTS`, `WINCLR`, `WINHLIT`, frame draw) | ~600 |
| Menu subsystem (`DOMNU`, `MNULOAD`, `MNUTITL`, `MNUDRAW`, `MNUSWCH`, key loop, tables, strings) | ~1,200 |
| Dialogs (`DOABT`, `DOQIT`, strings, button logic) | ~500 |
| Background save buffer (largest window: ~13 rows × 13 cells × 9 = 1,521 B) | ~1,600 |
| **Total** | **~3,900** |

**Available in FTRBASE:** 5,120 − 1,082 (CFG) = **4,038 bytes**. It fits with ~138 bytes headroom. If tight, the save buffer can overlap COLEXP (256 B staging, only used during row dumps and window code controls when those happen).

> **WARNING:** This is tight. If the code grows past the estimate, two options:
> 1. Move the save buffer to page 3 RAM (below the stack, between ENDVARS and TXPAGE)
> 2. Reduce the largest dialog's footprint (fewer rows)

---

## 9. FTRBASE Budget Guard

> **CRITICAL ASYMMETRY.** After the window/menu system ships:
> - S6ED FTRBASE: ~9,600 B free (16,384 total)
> - S2ED FTRBASE: ~200 B free (5,120 total)
>
> Any new shared FTRBASE passenger MUST verify it fits on BOTH targets.

### Assembly-Time Guard

```asm
; IN BOTH S2ED.Z8A AND S6ED.Z8A (AFTER BLK0END):
FTRFREE         EQU     DATBLEN - BLK0LEN
                ASSERT  FTRFREE >= 128, "FTRBASE HEADROOM < 128 BYTES"
```

`FTRFREE` appears in both `.sym` files for instant inspection.

### Static Test Guard

`TEST/static.py` `ftr-budget`: fail if any `CORE/*.Z8A` file adds an `FCALL`
without a `FTR-BUDGET` comment within ±5 lines acknowledging both targets.

### Documentation Guard

CLAUDE.md and `.memory/project_s2ed.md` must note the budget difference
explicitly. See `SPEC_S2ED_FTRBASE_GUARD.md` companion document.

---

## 10. Performance Estimates

| Operation | Cost | Notes |
|---|---|---|
| Window open (save + compose + dump) | ~80 ms | Save: LDIR ~2 KB, compose: ~15 cells worth, dump: 8-12 rows × 256 B = ~25 ms |
| Item highlight change | ~15 ms | 1 color row dump (32 B × 8 = 256 B) |
| Window close (restore + dump) | ~60 ms | LDIR restore + row dumps |
| Full menu switch | ~140 ms | Close + open |

All well within interactive limits. The user will see an instant popup.

---

## 11. Implementation Phases

| Phase | Content |
|---|---|
| **W1** | Window engine core (`S2/WINDOW.Z8A`) + budget guards |
| **W2** | `DOQIT` — Quit confirmation dialog |
| **W3** | `DOABT` — About dialog |
| **W4** | Menu dropdown subsystem (`S2/MENU.Z8A`) + `MNUENT` wiring |
| **W5** | Suite S2 test cases (S2-11, S2-12, S2-13) |

---

## 12. Files Modified / Created

| File | Action |
|---|---|
| `CODE/SRC/S2/WINDOW.Z8A` | **NEW** — Window engine for TMS9918 |
| `CODE/SRC/S2/MENU.Z8A` | **NEW** — Menu subsystem for TMS9918 |
| `CODE/SRC/S2/CONST_S2.Z8A` | Add window-related constants |
| `CODE/SRC/VARS.Z8A` | Add S2 window variables (`IFDEF S2ED`: `WINR`, `WINC`, `WINNR`, `WINNC`) |
| `CODE/SRC/CORE/ACTION.Z8A` | Replace `MNUENT` S2ED stub, wire `ACTQUIT`/`ACTHELP` |
| `CODE/SRC/S2ED.Z8A` | Add `INCLUDE WINDOW.Z8A` + `INCLUDE MENU.Z8A` + `FTRFREE` guard |
| `CODE/SRC/S6ED.Z8A` | Add `FTRFREE` guard |
| `CODE/Makefile` | (if needed for new source dependencies) |

---

## 13. S6ED vs S2ED Difference Matrix

| Aspect | S6ED (V9938) | S2ED (TMS9918) |
|---|---|---|
| Composition buffer | Off-screen VRAM Y=768 | RAM shadow (PATSHAD + COLMAP) |
| Background save | VRAM Y=512 via `HMMM` | RAM buffer in FTRBASE |
| Window show | Single `HMMM` blit, VBLANK-synced | Row-by-row `VDPDUMP` + `COLDUMP` |
| Glyph rendering | `LMMM` from VRAM font tables | `COMCELL` using RAM font tables |
| Fill operations | `HMMV` (byte fill), `LMMV` (logical) | Direct pattern/color shadow writes |
| Drop shadow | `HMMV` rectangles (4 px, color 0) | Shadow-color cells in COLMAP |
| Title highlight | `LMMV \| XOR` pixel toggle | COLMAP nibble swap + color dump |
| Coordinates | Pixels (512 wide) | Cells (32 wide) |
| Button border | `LMMV` rectangle | Color swap on cell boundary |
| Partial update (`WINUPD`) | `HMMM` sub-rectangle | Dump specific rows only |
