# S62ED — MSX2 Screen 6 (62-Column, 8x8 Font) Text Editor Specification

## 1. Concept & Rationale

**S62ED** is a high-performance 62-column text editor for **MSX2** running in **SCREEN 6 (GRAPHIC 5, 512×212, 4 colors, 2 bpp)** with native **8×8 pixel character cells** and a **symmetric 8-pixel CRT safety margin** on each side.

It complements the existing SXED targets:
* **S6ED:** MSX2 Screen 6, 80 columns × 24 rows, 6×8 font, `LMMM` logical blit (~120–150 T/byte).
* **S2ED:** MSX1 Screen 2, 64 columns × 22 rows, 4×8 font, TMS9918 pattern shadow dump.
* **S62ED:** MSX2 Screen 6, 62 columns × 24 rows, 8×8 font, `HMMM` high-speed transfer blit (~12–24 T/byte).

### Why 62 Columns with 8×8 Font in Screen 6
1. **Byte Alignment in VRAM:**
   * In Screen 6 (2 bpp), 1 byte = 4 pixels. An 8-pixel character cell is **exactly 2 bytes**.
   * Left margin: 8 pixels = **2 bytes**.
   * Text area: 62 columns × 8 pixels = **496 pixels (124 bytes)**.
   * Right margin: 8 pixels = **2 bytes**.
   * Total scanline: $2 + 124 + 2 = \mathbf{128\text{ bytes}} = \mathbf{512\text{ pixels}}$.
   * Column $C \in [0..61]$ starts at coordinate $DX = 8 + C \times 8 = (C + 1) \times 8$ pixels, which maps to VRAM byte offset $(C + 1) \times 2$.
2. **High-Speed Blitting (`HMMM`):**
   * The V9938 `HMMM` command requires $SX$ and $DX$ to be byte-aligned (multiples of 4 pixels in Screen 6).
   * Since $DX = (C + 1) \times 8$ and $SX = (\text{Char} \ \& \ 31) \times 8$, both coordinates are multiples of 8 (and thus multiples of 4).
   * Blitting eliminates the ALU logic of `LMMM`, transferring bytes directly through the internal VRAM bus at **~12–24 cycles/byte** (2.5× to 4× faster than `LMMM`).
3. **CRT Overscan & Safety Margins:**
   * Full 64 columns (512 px) can touch the analog overscan area on CRT televisions.
   * The 8 px left and right margins guarantee that text is never cropped by monitor bezels.
   * Each margin equals 1 character cell width (8 px), preserving space for future gutters, markers, or a scrollbar.
4. **Legibility & BIOS Font Compatibility:**
   * MSX BIOS CGROM font (`0x1BBF`) is natively 8×8. It is used unclipped with 100% fidelity.
   * 8×8 allows comfortable spacing, proper Spanish accents (`á`, `é`, `í`, `ó`, `ú`, `ñ`, `¿`, `¡`), and room for bold/italic artwork.

---

## 2. Geometry & Metrics

```
Screen 6: 512 x 212 pixels, 4 colors (2 bpp)

  [Left Margin: 8px]  [Text Viewport: 496px (62 cols x 8px)]  [Right Margin: 8px]

Row 0:      Menu Bar (y = 0..7)
Rows 1-24:  Text Rows 1..24 (y = 8..199, 24 rows x 8px = 192px)
Row 25:     Status Bar (y = 200..211)
```

| Constant | Value | Description |
|---|---|---|
| `SCRCOLS` | 62 | Text area columns on screen |
| `SCRROWS` | 24 | Text area rows (rows 1..24) |
| `ROWSVIS` | 24 | Visible document lines |
| `CELLW` | 8 | Cell width in pixels |
| `CELLH` | 8 | Cell height in pixels |
| `TXAREAPX` | 496 | Text area pixel width ($62 \times 8$) |
| `MARGPX` | 8 | Side margin width in pixels |
| `TXORG_X` | 8 | Text area origin X (`MARGPX`) |
| `TXORG_Y` | 8 | Text area origin Y (`CELLH`) |
| `TEXTCOLS` | 62 | Maximum line length for physical display |
| `LINEREC` | 125 | Line record payload ($1 + 62 + 62$ bytes) |
| `UNDOSIZ` | 4096 | Ring buffer size (~32 undo states) |

---

## 3. VRAM Map (Screen 6, 128 KB)

```
00000H – 069FFH   Bitmap display (128 B/line × 212 lines = 27,136 B)
06A00H – 07FFFH   Free (R#23 hardware scroll safe zone)
08000H – 09FFFH   Font Table — NORMAL       (SY 256, 32 glyphs/row × 8 rows)
0A000H – 0BFFFH   Font Table — BOLD         (SY 320, 32 glyphs/row × 8 rows)
0C000H – 0DFFFH   Font Table — ITALIC       (SY 384, 32 glyphs/row × 8 rows)
0E000H – 0FFFFH   Font Table — BOLD+ITALIC  (SY 448, 32 glyphs/row × 8 rows)
10000H – 17FFFH   WINBUF:  Off-screen background save buffer (SY 512..723)
18000H – 1FFFFH   WINCOMP: Off-screen composition buffer (SY 768..979)
```

### Font Table Geometry
* 32 glyphs per row × 8 rows = 256 glyphs per table.
* One table = 64 VRAM lines × 128 bytes = 8 KB address span.
* Glyph $N$: $SX = (N \ \& \ 31) \times 8$, $SY = \text{Table\_SY} + (N \gg 5) \times 8$.
* The left 64 bytes of each scanline hold the normal glyphs; the right 64 bytes (bytes 64–127, $SX = 256..511$) store the UI-paper expanded copy (`EXPSTAT`) for single-pass opaque chrome blits.

---

## 4. Subsystem Specifications

### 4.1 Rendering Pipeline (`SRC/S62/RENDER.Z8A`)
* **`ROWSET`:** Pre-loads VDP register block: $DY = \text{Row} \times 8$, $NY = 8$, $NX = 8$, $ARG = 0$.
* **`CELLGLY`:** Sets $DX = (Col + 1) \times 8$, resolves weight $SY$ from attribute bits, executes `VDP_HMMM` (#D0).
* **`CELLBLK`:** Clears cell via `HMMV` with $NX = 8$, $NY = 8$, $CLR = \text{CLR\_BG}$ (#00).
* **`SCROLL`:** Full text area scrolled in hardware via `YMMM` or `HMMM` ($DX = 8, DY = 8, NX = 496, NY = 184$).
* **Selection / Cursor:** Inverts color via `LMMV | XOR` ($NX = 8, NY = 8, CLR = \text{COL\_HI}$).

### 4.2 Font Subsystem (`SRC/S62/FONT.Z8A`)
* **Assets:** `RES/FONTSHEET_S64.PNG` (512×212, 4 blocks of 256×64 px), converted by `RES/mkfont62.py sheet` into `S62ED.FNT` (8,192 bytes). Until the commissioned face arrives the default is the IBM CGA, built by `mkfont62.py import` from `RES/FONTS62/`.
* **BIOS Fallback:** If `S62ED.FNT` is absent, reads 2,048 bytes from BIOS CGROM (`0x1BBF`) and replicates it across all four weight tables.
* **`EXPNORM`:** Expands 8 bits of 1bpp row byte to 2 bytes of 2bpp Color 1 (Ink).
* **`EXPSTAT`:** Expands 8 bits to 2 bytes of 2bpp Color 1 on Color 2 (UI Paper).

### 4.3 UI & Modal Windows (`SRC/S62/UI.Z8A`, `WINDOW.Z8A`, `BROWSER.Z8A`, `MENU.Z8A`)
* **Menu Bar:** 3 menus (`File`, `Edit`, `Help`), item dispatch unified with CORE.
* **Settings Dialog (`DOSETT`):** 9 setting rows (Profile, Wrap, Autoalign, Clock, Tab, EOL, Markup, Theme, Shadow) + OK / Cancel buttons. Full-row selection bar in `COL_UI` / `COL_HI`.
* **File Browser (`DOBRW`):** 4×12 file grid, 54-character information line, 2D cursor navigation.
* **Overwrite Confirmation (`DOOVR`):** Save As existence check modal.

---

## 5. Build, Packaging & Toolchain Integration

### 5.1 Targets
* Program: `S62ED.COM`
* Data/Container: `S62ED.DAT`
* Font: `S62ED.FNT`
* Config: `S62ED.CFG`

### 5.2 Makefile Integration
* `make build-s62`: Assembles `S62ED.COM` and `S62ED.DAT`.
* `make s62`: Rebuilds and launches in openMSX (`Boosted_MSX2_EN`, 2 MB).
* `make run-s62-128`: Launches in stock 128 kB `Philips_NMS_8250`.
* Unified Floppy Image (`S6ED.DSK`):
  * `A:\TOOLS\S6ED.COM` + `S6ED.DAT` + `S6ED.FNT`
  * `A:\TOOLS\S62ED.COM` + `S62ED.DAT` + `S62ED.FNT`
  * `A:\TOOLS\S2ED.COM` + `S2ED.DAT` + `S2ED.FNT`
  * `A:\DEV\S62ED.CFG` + `TEST.TXT` + `AUTOEXEC.BAT`

---

## 6. Phased Implementation Plan

1. **Phase 0:** Target skeleton, directory `SRC/S62/`, `CONST_S62.Z8A`, Makefile build & clean targets.
2. **Phase 1:** 8×8 font loader, `EXPNORM`/`EXPSTAT` expanders, BIOS ROM fallback, `fontcheck_s62.py`.
3. **Phase 2:** High-speed `HMMM` renderer, `HMMV` cell clearer, cursor XOR, `YMMM` scroll.
4. **Phase 3:** 62-column UI chrome, dropdown menus, Settings dialog, File Browser (4×12 grid).
5. **Phase 4:** Headless openMSX test gate suite (`gate_s62.py`) and mutation tests.
6. **Phase 5:** Unified DSK integration and documentation updates.
