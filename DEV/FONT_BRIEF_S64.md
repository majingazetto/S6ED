# S64ED — 8x8 Font Asset Brief

S64ED is an MSX2 text editor running in SCREEN 6 (512x212, 4 colours) in **64 columns** with a native **8x8 pixel cell**. Because character cells are 8 pixels wide (exactly 2 bytes at 2 bpp), every column is byte-aligned and characters are blitted with high-speed VDP `HMMM` transfers.

This brief describes the asset required: a 256-glyph bitmap font in four weights — normal, bold, italic, and bold-italic.

---

## Files

| File | What it is |
|---|---|
| [`RES/FONTSHEET_S64.PNG`](file:///Users/armandoperezabad/Code/brew/S6ED/RES/FONTSHEET_S64.PNG) | **The working file.** 8-bit indexed PNG (512x212), for PC tools (Aseprite, Photoshop, GIMP, GrafX2). |
| [`RES/FONTSHEET_S64.SR6`](file:///Users/armandoperezabad/Code/brew/S6ED/RES/FONTSHEET_S64.SR6) | Raw SCREEN 6 VRAM dump (27,136 bytes). Open in SRView. |
| [`RES/FONTSHEET_S64.PL6`](file:///Users/armandoperezabad/Code/brew/S6ED/RES/FONTSHEET_S64.PL6) | Companion palette (Black, White, Blue, Yellow). |
| [`RES/FONTGUIDE_S64.PNG`](file:///Users/armandoperezabad/Code/brew/S6ED/RES/FONTGUIDE_S64.PNG) | **Reference guide.** Single labelled grid with 8x8 cell guidelines and hex row offsets (`+00`..`+E0`). |
| [`RES/mkfontsheet_s64.py`](file:///Users/armandoperezabad/Code/brew/S6ED/RES/mkfontsheet_s64.py) | Python generator script for the font sheets. |

---

## Layout

The sheet is 512 x 212 and carries **four blocks** of 256 x 64 pixels:

```
            x 0                        x 256
    y  20   NORMAL                     BOLD
    y  96   ITALIC                     BOLD+ITALIC
```

* Inside its own block, glyph $N$ sits at:
  $$\text{X} = (N \ \& \ 31) \times 8, \quad \text{Y} = (N \gg 5) \times 8$$
  with rows running `+00`, `+20`, `+40`, `+60`, `+80`, `+A0`, `+C0`, `+E0` top to bottom.
* Two blocks side by side total 512 pixels ($256 + 256 = 512$).
* The thin blue rules and titles are chrome/guides. Draw only inside the 8x8 glyph cells.

---

## Cell Rules for 8x8

1. **Full 8x8 Pixel Grid:**
   Unlike S6ED (which was restricted to 6x8 with columns 6-7 discarded), in S64ED **all 8x8 pixels of every cell are valid and blitted by the hardware**.
2. **Letter Spacing:**
   * For standard running text (letters, numbers, punctuation), leaving **column 7 empty** is recommended as natural letter spacing.
   * For box-drawing characters (`─`, `│`, `┌`, `┐`, `└`, `┘`, `┼`), block symbols, and full-width graphical characters, **use all 8 columns (0–7)** so lines connect seamlessly with neighbouring cells.
3. **Pre-filled Weights:**
   * **NORMAL** arrives pre-filled with the authentic MSX BIOS 8x8 CGROM font.
   * **BOLD**, **ITALIC**, and **BOLD+ITALIC** arrive pre-filled with machine derivations as a comfortable starting baseline for retouching.
4. **Palette:**
   * `Color 1`: Background (Black)
   * `Color 3`: Ink (White) — **draw in this color**.
   * `Color 2`: Blue guides / frames (do not paint over).
