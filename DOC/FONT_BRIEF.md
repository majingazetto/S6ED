# S6ED — Font Asset Brief

S6ED is an MSX2 text editor running in SCREEN 6 (512x212, 4 colours). It renders
text as an 80 x 24 character grid with a 6 x 8 pixel cell. This brief describes
the one asset we need: a single-weight 256-glyph bitmap font.

## Files

| File | What it is |
|------|------------|
| `RES/FONTSHEET.SR6` | The sheet, as a raw SCREEN 6 VRAM page (27136 bytes). Open in SRView. |
| `RES/FONTSHEET.PNG` | The same sheet as an indexed PNG, if you would rather work in a PC tool. |
| `RES/mkfontsheet.py` | Regenerates both. |

Return the edited sheet in either format, same dimensions, same layout.

## Layout

The sheet is 512 x 212. The top block is a 32 x 8 grid of 8 x 8 cells holding
the 256 glyphs, in code order: **glyph N sits at `((N & 31) * 8, (N >> 5) * 8)`**
relative to the grid origin. The row labels down the right edge give the code of
the first glyph in each row (`+00`, `+20`, `+40`, ...).

That is exactly the layout the editor blits from, so whatever comes back
converts straight into the engine with no re-layout step.

The glyphs currently on the sheet are the stock MSX ROM charset. They are there
as a metric reference and a starting point — replace them.

## The one hard rule

**Ink only in columns 0 to 4 of each cell. Column 5 must stay empty.**

The sheet marks column 5 with a dotted yellow line and puts a blue rule on the
last column of each cell. Three separate things depend on that empty column:

1. **Letter spacing.** The renderer copies 6 pixels per cell and advances 6
   pixels. Column 5 *is* drawn. Ink there touches the next character.
2. **Bold.** Bold is not drawn by hand — it is generated at startup as
   `row | (row >> 1)`, thickening every stroke one pixel to the right. It needs
   column 5 to grow into.
3. **Italic.** Also generated: the top half of each glyph leans one pixel right,
   into the same column.

You draw **one weight**. Bold, italic and bold-italic are derived from it. The
three sample lines on the sheet show all three generated from the current font,
so you can see what your shapes will become.

Note that bold text has no gap between letters, because bold fills column 5.
That is expected at a 6 pixel pitch and is not something to design around.

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

The other two colours on the sheet (blue rules, yellow dots) are guides. They
are ignored on import; only the white pixels are read.

## Character set

All 256 codes. Priority order if time is short:

1. `#20`-`#7E` — printable ASCII. This is what the editor shows 99% of the time.
2. `#80`-`#FF` — accented characters and box-drawing. The MSX ROM set is
   localised per machine, which is the main reason we want our own font.
3. `#00`-`#1F` — control range. Currently unused by the editor; leave as-is or
   use for editor symbols (tab marker, end-of-line marker, cursor shapes).

## Style notes

It is a code and prose editor, shown at 80 columns on a CRT. Legibility at
small size beats personality. Specifically:

- Keep strokes one pixel where possible. The current bundled font (a boot-menu
  display face) uses two-pixel left stems and reads lopsided and cluttered.
- `0` / `O`, `1` / `l` / `I`, `5` / `S`, `8` / `B` must be distinguishable.
- Punctuation matters more than usual: `; : , . ' " ( ) [ ] { } < >` all carry
  meaning in source code.
