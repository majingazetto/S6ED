# Architectural Specification: Universal Horizontal Viewport (`LEFTCOL`) & Parametric `TEXTWIDTH`

**Date:** 2026-09-27  
**Status:** Approved Specification (Phase 1 SDD)  
**Authors:** Armando Pérez Abad & Gemini / Antigravity  
**Target Systems:** MSX2 Screen 6 (S6ED, 80 cols) & MSX1 Screen 2 (S2ED, 64 cols)  

---

## 1. Executive Summary & Design Pivot

The SXED editor family operates across two hardware resolutions with a shared core:
* **S6ED (MSX2 Screen 6):** 80 columns visible ($512\times 212$, 6px font).
* **S2ED (MSX1 Screen 2):** 64 columns visible ($256\times 192$, two 4px glyphs per $8\times 8$ cell).

### 1.1 The Cross-Resolution Problem
Standard MSX documentation, source files, and terminal manuals (e.g. `YAT/DOC/YAT.TXT`) are typically formatted at 72–80 columns. In S2ED (64 cols), treating the physical screen width as the hard document boundary previously caused either data truncation upon load or forced word-wrapping when editing.

### 1.2 The Solution: Decouple Viewport from Typing Policy
1. **Universal Horizontal Viewport (`LEFTCOL`):** The screen is a sliding window `[LEFTCOL .. LEFTCOL + TEXTCOLS - 1]` over variable-length records (up to 255 columns). Lines longer than the screen width are fully preserved, readable, and editable via horizontal scrolling on **both** S6ED and S2ED.
2. **Parametric `TEXTWIDTH` (Vim `:set tw=XX` & TED `F2/R` standard):**
   * `TEXTWIDTH = 0` (Wrap OFF / DEV mode): Free horizontal typing up to 255 columns with automatic horizontal scroll. Zero automatic line splitting.
   * `TEXTWIDTH = N` (Wrap ON / TXT mode, e.g. 32, 64, 72, 80): When typing actively reaches column `N`, smart push-wrap (`EDPSHWR`) moves the active word to the next line.
   * Existing lines longer than `TEXTWIDTH` are never broken merely by viewing, navigating, or editing elsewhere.
3. **Zero Soft-Wrap Complexity:** By relying on horizontal scrolling for long lines, the editor preserves the exact $O(1)$ invariant:
   $$\text{Screen Row} = \text{DOCLINE} - \text{TOPLINE}$$
   Hardware VDP block moves (`HMMM`/`YMMM`) and differential rendering (`RENDIFF`) remain ultra-fast (sub-11ms).

---

## 2. Phase Breakdown

```
+---------------------------------------------------------------------------------+
| PHASE C1: Universal Horizontal Viewport (LEFTCOL) & Auto-Scroll Engine          |
|   - Variable LEFTCOL in VARS.Z8A (0 .. MAXCOLS - TEXTCOLS).                     |
|   - Screen column mapping: SCREEN_X = CURX - LEFTCOL.                           |
|   - Auto-scroll routine ADJLEFTCOL with hysteresis chunking (8 columns).        |
|   - Render adaptation: RENDEROW, RENDIFF, DRWCUR, SELPAIN in S6 and S2.         |
|   - Real-world integration test with YAT.TXT (818 lines, 120 lines > 64 cols).  |
|   - 100% test gate clean on S6 and S2.                                          |
+---------------------------------------------------------------------------------+
                                       |
                                       v
+---------------------------------------------------------------------------------+
| PHASE C2: Parametric TEXTWIDTH & Unified Wrap Policy                            |
|   - Variable TEXTWIDTH in VARS.Z8A (0 = OFF, 1..255 = wrap margin).             |
|   - EDINSCHR / EDPSHWR uses (TEXTWIDTH) instead of fixed TEXTCOLS.              |
|   - Config integration: TEXTWIDTH= in S6ED.CFG / S2ED.CFG.                      |
|   - VI Ex-mode commands: :set tw=XX, :set textwidth=XX.                         |
|   - Status bar indicator [D] (TW=0) vs [T] (TW>0).                              |
+---------------------------------------------------------------------------------+
```

---

## 3. Phase C1 Specification: Viewport Engine (`LEFTCOL`)

### 3.1 State & Arithmetic
* **Variable `LEFTCOL` (`VARS.Z8A`):**
  - Type: 1 byte (`0 .. MAXCOLS - TEXTCOLS`).
  - Maximum value in S6ED: $255 - 80 = 175$.
  - Maximum value in S2ED: $255 - 64 = 191$.
  - Initialized to 0 by `INIT`, `FILELOAD`, and `NEWFILE`.

* **Coordinate Transform:**
  $$\text{SCREEN\_X} = \text{CURX} - \text{LEFTCOL}$$
  - Cursor is visible if and only if $\text{CURX} \ge \text{LEFTCOL}$ and $\text{CURX} < \text{LEFTCOL} + \text{TEXTCOLS}$.
  - In S6ED, physical pixel X is $\text{TXORG\_X} + \text{SCREEN\_X} \times 6$.
  - In S2ED, cell index is $\text{SCREEN\_X} / 2$, nibble is $\text{SCREEN\_X} \pmod 2$.

### 3.2 Auto-Scroll Algorithm (`ADJLEFTCOL`)
Called after any cursor move (`EDMOVCHR`, `EDCLMPX`, `ACTMVL`, `ACTMVR`, `ACTMVEOL`, `ACTMVBOL`) or text edit (`EDINSCHR`, `WBINSN`, `ACTABS`):

1. **Right Margin Overrun (`CURX >= LEFTCOL + TEXTCOLS`):**
   - Shift viewport right with an 8-column lead to provide visual typing context:
     $$\text{TARGET} = \text{CURX} - \text{TEXTCOLS} + 1 + 8$$
     $$\text{LEFTCOL} = \min(\text{MAXCOLS} - \text{TEXTCOLS}, \; \text{TARGET})$$
   - Sets `DIRTY_SCROLL = 1` $\to$ triggers `REDRAW`.
2. **Left Margin Overrun (`CURX < LEFTCOL`):**
   - Shift viewport left with an 8-column lead:
     $$\text{LEFTCOL} = \max(0, \; \text{CURX} - 8)$$
   - Sets `DIRTY_SCROLL = 1` $\to$ triggers `REDRAW`.
3. **In-Bounds (`LEFTCOL <= CURX < LEFTCOL + TEXTCOLS`):**
   - `LEFTCOL` unchanged. Returns Carry=0. Only local cursor (`DRWCUR`) or row (`RENDIFF`) is updated.

### 3.3 Render Pipeline Updates

#### A. Full Row Render (`RENDEROW`)
* Let $L$ be the record length in `WORKBUF[0]`.
* If $L \le \text{LEFTCOL}$: the entire visible screen row is beyond line content.
  - Fill row with `CLR_BG` via single hardware `HMMV` (S6) or blank pattern/color cells (S2).
* If $L > \text{LEFTCOL}$:
  - Visible text length: $V = \min(\text{TEXTCOLS}, \; L - \text{LEFTCOL})$.
  - Text pointer: `HL = WORKBUF + 1 + LEFTCOL`.
  - Attribute pointer: `WORKBUF + 1 + WORKATTR + LEFTCOL`.
  - Blit $V$ glyphs starting at screen column 0.
  - If $V < \text{TEXTCOLS}$, clear remaining tail columns ($V .. \text{TEXTCOLS}-1$) with background color.

#### B. Differential Row Render (`RENDIFF`)
* Compares `PREVBUF[c]` against `WORKBUF[1 + LEFTCOL + c]` for $c \in [0 .. \text{TEXTCOLS}-1]$.
* Updates only dirty visible cells.

#### C. Hardware Cursor (`DRWCUR`)
* If $\text{CURX} < \text{LEFTCOL}$ or $\text{CURX} \ge \text{LEFTCOL} + \text{TEXTCOLS}$, exit immediately (`RET`).
* Otherwise, compute $\text{SCREEN\_X} = \text{CURX} - \text{LEFTCOL}$ and XOR the cell.

#### D. Selection Inversion (`SELPAIN` / `SELXOR`)
* Clip logical selection interval $[\text{SELSTRX}, \text{SELENDX}]$ against $[\text{LEFTCOL}, \text{LEFTCOL} + \text{TEXTCOLS} - 1]$:
  $$\text{VIS\_STRX} = \max(0, \; \text{SELSTRX} - \text{LEFTCOL})$$
  $$\text{VIS\_ENDX} = \min(\text{TEXTCOLS} - 1, \; \text{SELENDX} - \text{LEFTCOL})$$
* If $\text{VIS\_STRX} \le \text{VIS\_ENDX}$, apply hardware XOR inversion over the visible span.

---

## 4. Phase C2 Specification: Parametric `TEXTWIDTH`

### 4.1 Variables and Semantics
* **`TEXTWIDTH` (`VARS.Z8A`):**
  - 1 byte, values $0 .. 255$.
  - `0`: Auto-wrap disabled. Lines grow up to `MAXCOLS = 255` with horizontal scroll.
  - `> 0`: Auto-wrap threshold.
* **Wrap Modes as Behavioral Profiles:**
  - `WRAP = DEV`: Sets `TEXTWIDTH = 0`. Disables cascade reflow on Backspace (`JOIN2L` only). Confines horizontal cursor at line boundaries. Enables `AUTOALGN` for code.
  - `WRAP = TXT`: Uses configured `TEXTWIDTH` (default `TEXTCOLS`). Enables cascade paragraph reflow (`REFLOW`). Enables fluid cursor wrapping across lines.

### 4.2 Push-Wrap Threshold (`EDINSCHR` / `EDPSHWR`)
* When typing character $C$ at `CURX`:
  - If `TEXTWIDTH == 0`:
    - If `CURX >= MAXCOLS`, reject (`CLAMP`).
    - Otherwise, insert character into `WORKBUF`. If `CURX >= LEFTCOL + TEXTCOLS`, auto-scroll right.
  - If `TEXTWIDTH > 0`:
    - If `CURX < TEXTWIDTH - 1`, plain insert.
    - If `CURX >= TEXTWIDTH - 1`:
      - If $C == \text{' '}$, trigger clean newline (`EDNWLIN`).
      - Otherwise, trigger push-wrap (`EDPSHWR`), scanning backward from `CURX` to the previous space and moving the active word to line `DOCLINE + 1`.

---

## 5. Verification Plan & Test Matrix

### 5.1 Real-World Fixture: `YAT.TXT`
* File: `YAT/DOC/YAT.TXT` (818 lines, 120 lines $> 64$ cols, 5 lines $> 80$ cols, max length 86).
* **Test Case S2-YatLoad:**
  - Load `YAT.TXT` on `Custom_MSX1_DOS2`.
  - Assert `TOTLINES == 818`.
  - Navigate to line 129 (length 84).
  - Move cursor to column 80.
  - Assert `LEFTCOL > 0` and `SCREEN_X == CURX - LEFTCOL`.
  - Save file to disk.
  - Empirical verification via `dsktool E`: saved file is **byte-for-byte identical** to `YAT/DOC/YAT.TXT`.
* **Test Case S6-YatLong:**
  - Load `YAT.TXT` on `Boosted_MSX2_EN`.
  - Navigate to line 492 (length 85).
  - Move cursor past column 80; assert horizontal scroll activates.

### 5.2 Quality Invariants
* Clean assembly on both targets with 0 errors and 0 warnings.
* Full regression gate clean: 19 static checks (`make check`), 377 S6 checks (`make gate`), and all S2 checks (`make test-s2`).
