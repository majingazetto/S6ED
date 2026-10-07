# SXED Font System & Custom Font Creation Guide

This document details the typography architecture of the SXED editor family and provides instructions for creating, modifying, and compiling custom fonts.

---

## 1. Typography Across the SXED Family

SXED employs three distinct bitmap font engines adapted to the hardware capabilities of each target:

| Target | Cell Size | Visible Glyphs | Weights Supported | Storage & Format |
|:---|:---|:---|:---|:---|
| **S6ED** | **6×8** px | 256 glyphs | Normal, Bold, Italic, Bold-Italic | `S6ED.FNT` (8,192 bytes, raw VRAM pattern) |
| **S61ED** | **8×8** px | 256 glyphs | Normal, Bold, Italic, Bold-Italic | `S61ED.FNT` (8,192 bytes, byte-aligned VRAM) |
| **S2ED** | **4×8** px | 256 glyphs | Single weight (TMS9918 hardware) | `S2ED.FNT` (2,048 bytes, 8 bytes per glyph) |

---

## 2. Font Specifications

### 2.1 S6ED (6×8 font in Screen 6)
- **Cell:** $8 \times 8$ hardware cell in VRAM, but only columns $0 \dots 5$ are blitted to the screen; columns $6 \dots 7$ are discarded by the blitter.
- **Weights:** All 4 weights reside in VRAM simultaneously:
  - `NORMAL`: Base typography.
  - `BOLD`: 1-pixel horizontal weight expansion.
  - `ITALIC`: Slanted rightwards along scanlines.
  - `BOLD+ITALIC`: Combined slant and weight expansion.

### 2.2 S61ED (8×8 font in Screen 6)
- **Cell:** Full $8 \times 8$ pixels rendered directly.
- **Alignment:** Because 8 pixels at 2 bpp equal exactly 2 bytes in VRAM, character transfers use ultra-fast, byte-aligned VDP `HMMM` blits.
- **Geometry:** 61 columns centered horizontally with a 16 px margin on the left ($61 \times 8 = 488$ px, leaving $24$ px total border space: 16 px left, 8 px right).
- **Bundled Fonts:**
  - `DEFAULT`: Custom hand-drawn face by Miguel A. Fernandez.
  - `CGA`: Classic IBM PC CGA text font.
  - `CPC`: Amstrad CPC 464/6128 system font.
  - `BIOS`: Standard MSX BIOS CGROM font.

### 2.3 S2ED (4×8 font in Screen 2)
- **Cell:** Two 4-pixel-wide glyphs share one TMS9918 $8 \times 8$ cell (left nibble and right nibble).
- **Hardware:** In Screen 2, color attributes are assigned per $8 \times 1$ pixel block (2 characters share a color attribute). Selection and cursor rendering invert pattern bits directly via `PATINV`.

---

## 3. Font Sheets Layout (`RES/`)

Working font sheets are stored as 4-block layouts ($512 \times 212$ pixels, matching an entire Screen 6 VRAM page):

```
       x 0                        x 256                      x 512
y  20  +--------------------------+--------------------------+
       | NORMAL (256x64 px)       | BOLD (256x64 px)         |
y  84  +--------------------------+--------------------------+
y  96  +--------------------------+--------------------------+
       | ITALIC (256x64 px)       | BOLD+ITALIC (256x64 px)  |
y 160  +--------------------------+--------------------------+
```

Inside each $256 \times 64$ block, 256 glyphs are arranged in a $32 \times 8$ grid:
- Glyph index $N$ ($0 \dots 255$) is located at:
  $$\text{X} = (N \ \& \ 31) \times 8, \quad \text{Y} = (N \gg 5) \times 8$$
- Color palette for drawing:
  - `Color 1`: Background (Black).
  - `Color 3`: Ink (White) — **draw glyphs in this color**.
  - `Color 2`: Blue guide grids (do not paint over).

---

## 4. How to Create and Compile Custom Fonts

### 4.1 Creating an 8×8 Font for S61ED

1. **Generate the font sheet template:**
   ```bash
   python3 RES/mkfontsheet_s64.py
   ```
   This generates `RES/FONTSHEET_S64.PNG` (editable in Aseprite, GIMP, Photoshop, GrafX2) and `RES/FONTSHEET_S64.SR6` (viewable/editable in SRView).

2. **Draw the glyphs:**
   - Draw your characters in the **NORMAL** quadrant (top-left).
   - *Tip:* You only need to draw the NORMAL weight! The build tool can automatically derive BOLD, ITALIC, and BOLD-ITALIC for you.

3. **Compile the font binary:**
   ```bash
   python3 RES/mkfont61.py sheet --derive
   ```
   This generates `S61ED.FNT` (8,192 bytes) ready for use.

4. **Testing in openMSX:**
   Copy your new `.FNT` into `CODE/` and run:
   ```bash
   cd CODE
   make run-s61
   ```

---

### 4.2 Creating a 6×8 Font for S6ED

1. **Generate or open the sheet:**
   Open `RES/FONTSHEET.PNG` in your preferred graphic editor.
2. **Draw rules for 6×8:**
   - Draw within columns $0 \dots 5$ of each $8 \times 8$ cell.
   - Leave columns $6 \dots 7$ empty (they are ignored by the blitter).
3. **Compile the font binary:**
   ```bash
   python3 RES/fontcheck.py RES/FONTSHEET.PNG --out S6ED.FNT
   ```

---

### 4.3 Creating a 4×8 Font for S2ED

1. **Open the template:**
   Open `RES/FONT4X8.PNG` (a $128 \times 64$ grid containing 256 glyphs of $4 \times 8$ pixels).
2. **Draw rules:**
   - Each glyph must strictly fit in 4 pixels horizontally and 8 pixels vertically.
3. **Compile the binary:**
   ```bash
   python3 RES/fontcheck_s2.py RES/FONT4X8.PNG --out S2ED.FNT
   ```
