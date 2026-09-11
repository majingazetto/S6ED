# S6ED — Font Asset Brief

S6ED is an MSX2 text editor running in SCREEN 6 (512x212, 4 colours). It renders
text as an 80 x 24 character grid with a 6 x 8 pixel cell. This brief describes
the one asset we need: a single-weight 256-glyph bitmap font.

## Files

| File | What it is |
|------|------------|
| `RES/FONTSHEET.SR6` | **The working file.** Raw SCREEN 6 VRAM page, 27136 bytes. Open in SRView. |
| `RES/FONTSHEET.PNG` | The same pixels as an 8-bit indexed PNG, for PC tools. |
| `RES/FONTSHEET.PL6` | Companion palette. A raw `.SRx` carries no palette of its own. |
| `RES/FONTGUIDE.SR6` `.PNG` `.PL6` | **Reference only.** The same grid with guides, samples and the rules painted on. Do not draw on this one. |
| `RES/mkfontsheet.py` | Regenerates all of the above. |
| `RES/fontcheck.py` | Reads an edited sheet back, checks it and writes `FONT.BIN`. |

Return the edited **FONTSHEET**, in either format, same dimensions, same layout.

### About the palette

A raw `.SRx` file is pixels only. A viewer that does not load the companion
`.PL6` falls back to the MSX default palette, where entry 0 is *transparent*.
The working sheet therefore uses only entries 1 (background) and 3 (ink), so it
stays legible either way. Keep drawing in those two.

## Layout

The sheet is 512 x 212. The top-left block is a 32 x 8 grid of 8 x 8 cells
holding the 256 glyphs in code order: **glyph N sits at
`((N & 31) * 8, (N >> 5) * 8)`**, origin `(0, 0)`. The rest of the canvas is
empty and is ignored.

That is exactly the layout the editor blits from, so an edited sheet converts
straight back with no re-layout step:

```
python3 RES/fontcheck.py RES/FONTSHEET.SR6 --out RES/FONT.BIN
```

`fontcheck.py` exits non-zero if any rule below is broken, so it can gate a
build. Run it before sending anything back.

The glyphs currently on the sheet are the stock MSX ROM charset. They are there
as a metric reference and a starting point — replace them.

Note the cells are 8 pixels wide but only the first 6 are ever drawn on screen.
Anything in columns 6-7 is silently discarded on import.

## The one hard rule

**Ink only in columns 0 to 4 of each cell. Column 5 must stay empty.**

Three separate things depend on that empty column:

1. **Letter spacing.** The renderer copies 6 pixels per cell and advances 6
   pixels. Column 5 *is* drawn. Ink there touches the next character.
2. **Bold.** Bold is not drawn by hand — it is generated at startup by
   thickening every stroke one pixel to the right. It needs column 5 to grow
   into.
3. **Italic.** Also generated: the top half of each glyph leans one pixel right,
   into the same column.

You draw **one weight**. Bold, italic and bold-italic are derived from it. The
reference sheet renders the same sample string three times, all three generated
by the real transforms, so you can see what your shapes will become.

Bold text has no gap between letters, because bold fills column 5. That is
expected at a 6 pixel pitch and is not something to design around.

### Why the bold transform will not eat your counters

The obvious way to embolden a bitmap is `row | (row >> 1)`. Measured against the
MSX ROM charset, that closes a one-pixel counter in **37 of the 95 printable
glyphs** — `A M N W m n u v w` and friends turn into blobs. S6ED instead masks
out any background pixel that has ink on *both* sides, so one-pixel holes
survive: 0 of 95 damaged. The rule is structural rather than tuned to one
typeface, so it holds for whatever font you draw — but keep interior gaps at one
pixel or more and they will be preserved.

## Vertical metrics

Eight rows per cell. Follow the reference:

- Rows 0-6: capitals and x-height.
- Baseline on row 6.
- Row 7: descenders only (`g j p q y`, and the comma and semicolon tails).

There is no blank separator row, so adjacent text lines touch where a descender
occurs. Normal for a 6 x 8 MSX font.

## Colour

None. The sheet is monochrome: a pixel is either ink or background. The editor
picks the colour at draw time — the same glyph is used for normal text, for
syntax highlighting and for the UI chrome. Do not encode colour in the glyphs.

## Character set

All 256 codes. Priority order if time is short:

1. `#20`-`#7E` — printable ASCII. This is what the editor shows 99% of the time.
2. `#80`-`#FF` — accented characters and box drawing. The MSX ROM set is
   localised per machine, which is the main reason we want our own font.
3. `#00`-`#1F` — control range. Currently unused by the editor; leave as-is or
   use for editor symbols (tab marker, end-of-line marker, cursor shapes).

## Style notes

It is a code and prose editor, shown at 80 columns on a CRT. Legibility at
small size beats personality. Specifically:

- Keep strokes one pixel where possible. The font previously bundled with S6ED
  (a cartridge boot-menu display face) used two-pixel left stems and read
  lopsided and cluttered.
- `0` / `O`, `1` / `l` / `I`, `5` / `S`, `8` / `B` must be distinguishable.
- Punctuation matters more than usual: `; : , . ' " ( ) [ ] { } < >` all carry
  meaning in source code.
