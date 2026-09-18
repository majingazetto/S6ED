#!/usr/bin/env python3
"""Build the S6ED font sheet handed to the artist.

Produces a 512x212 Screen 6 canvas holding the 256 glyph cells in exactly the
layout the editor blits from: glyph N sits at ((N & 31) * 8, (N >> 5) * 8), so
whatever comes back converts straight into FONT.BIN with no re-layout.

With --variants it lays four of those grids out as 2x2 blocks -- NORMAL,
BOLD, ITALIC and BOLD+ITALIC -- and pre-fills the three derived blocks by
machine from NORMAL, so the artist retouches a starting point instead of
drawing 756 glyphs from scratch.

Colour 0 background, colour 1 ink (the only colour the artist draws in),
colour 2 chrome and guides, colour 3 the reserved column.
"""

import argparse
import struct
import sys
from pathlib import Path

CELL_W, CELL_H = 8, 8          # VRAM pitch of one glyph slot
DRAW_W = 5                     # columns 0-4: the artist's area
BOLD_COL = 5                   # column 5: the gap, and NORMAL must leave it
SCREEN_W, SCREEN_H = 512, 212

GRID_X, GRID_Y = 0, 12         # glyph grid origin
LABEL_X = 264                  # row labels sit right of the grid

# Index 0 is left unused on purpose: a raw .SRx carries no palette, so a viewer
# falls back to the MSX default where entry 0 is TRANSPARENT and the sheet would
# come up invisible. Entries 1 / 2 / 3 default to black / green / light green,
# which stays legible with or without the companion .PL6.
BG, INK, CHROME, WARN = 1, 3, 2, 0


def load_rom_charset(bios: Path, offset: int) -> bytes:
    data = bios.read_bytes()
    return data[offset:offset + 2048]


class Canvas:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.px = bytearray(w * h)

    def set(self, x, y, c):
        if 0 <= x < self.w and 0 <= y < self.h:
            self.px[y * self.w + x] = c

    def rect(self, x, y, w, h, c):
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self.set(xx, yy, c)

    def glyph(self, font, code, x, y, colour=INK, transform=None):
        rows = font[code * 8:code * 8 + 8]
        if transform:
            rows = transform(rows)
        for r, byte in enumerate(rows):
            for b in range(6):
                if byte & (0x80 >> b):
                    self.set(x + b, y + r, colour)

    def text(self, font, s, x, y, colour=INK, advance=6, transform=None):
        for i, ch in enumerate(s):
            self.glyph(font, ord(ch), x + i * advance, y, colour, transform)


def bold(rows):
    """Thicken one pixel right, but never close a one pixel counter.

    The obvious `row | (row >> 1)` fills any background pixel whose left
    neighbour is ink -- including the single pixel holes inside A M N W m n u v w
    and 34 other glyphs of the ROM charset, which turn into blobs. Masking out
    pixels that have ink on BOTH sides keeps every counter open, and the rule is
    structural rather than tuned to one typeface, so it survives a font change.
    """
    out = []
    for r in rows:
        hole = (~r) & (r >> 1) & (r << 1) & 0xFC
        out.append(((r | (r >> 1)) & ~hole) & 0xFC)
    return out


def italic(rows):
    """Top half leans one pixel right, bottom half stays put.

    DEV/DESIGN.md proposes +1 +1 +1 +1 0 -1 -1 -1, but shifting the bottom rows the
    other way pushes ink out of column 0 and loses it, and with bit 7 as the
    leftmost pixel that table actually produces a backslant. Leaning only the
    top half into the reserved column 5 is lossless and slants the right way.
    """
    return [(r >> 1) & 0xFC if i < 4 else r & 0xFC
            for i, r in enumerate(rows)]


def bolditalic(rows):
    """Slant first, then thicken. Lossy at the right edge, unavoidably.

    Either order pushes ink into column 6, which is never blitted: italic
    lifts column 4 into column 5, and bold then has nowhere left to grow. On
    the current face that costs 427 pixels across 91 of the 95 printable
    glyphs, and two of them come out identical to plain ITALIC. Six pixels do
    not hold both transforms, which is exactly why this block is the one worth
    drawing by hand rather than deriving.
    """
    return bold(italic(rows))


# --- FOUR WEIGHT SHEET LAYOUT --------------------------------------------
# Four 256x64 blocks in a 2x2 arrangement inside the same 512x212 page. Two
# blocks side by side come to 512 exactly, so there is no room for a gap or for
# the row labels; FONTGUIDE keeps the single labelled grid as the per-glyph
# reference. fontcheck.py carries the same origins -- keep the two in step.

QUAD_W, QUAD_H = 32 * CELL_W, 8 * CELL_H       # one block: 256 x 64
TITLE_Y = 1
ROW1_Y, ROW2_Y = 20, 96                        # top of each band of blocks
LEGEND_Y = 163

VARIANTS = (
    ("NORMAL",      (0,      ROW1_Y), None),
    ("BOLD",        (QUAD_W, ROW1_Y), bold),
    ("ITALIC",      (0,      ROW2_Y), italic),
    ("BOLD+ITALIC", (QUAD_W, ROW2_Y), bolditalic),
)

LEGEND = (
    "Blocks: NORMAL and BOLD on top, ITALIC and BOLD+ITALIC below. Rows: +00 +20 .. +E0.",
    "Glyph N sits at ((N & 31) * 8, (N >> 5) * 8) inside its own block.",
    "NORMAL: ink in columns 0-4. Column 5 stays empty; it is the gap between letters.",
    "The other three: column 5 is yours. Columns 6-7 are never drawn, in any block.",
    "The three derived blocks are pre-filled by machine from NORMAL. Redraw them freely.",
    "BOLD+ITALIC loses its bold pixel off the right edge. Redraw that block first.",
)


def build_variants(font: bytes) -> Canvas:
    """The four weight working sheet, pre-filled and ready to be drawn on."""
    c = Canvas(SCREEN_W, SCREEN_H)
    c.rect(0, 0, SCREEN_W, SCREEN_H, BG)
    c.text(font, "S6ED 6x8 FONT SHEET - FOUR WEIGHTS - DRAW ON THIS ONE",
           2, TITLE_Y, CHROME)

    # Frame the blocks from the gaps between them, never from inside a cell, so
    # nothing the artist gets can be mistaken for glyph ink. The one vertical
    # rule sits on column 7 of the last cell of each left hand block, which the
    # editor never blits and which fontcheck reads as chrome, not as ink.
    for name, (qx, qy), fn in VARIANTS:
        c.text(font, name, qx + 2, qy - CELL_H - 1, CHROME)
        for code in range(256):
            c.glyph(font, code,
                    qx + (code & 31) * CELL_W,
                    qy + (code >> 5) * CELL_H,
                    transform=fn)
    for y in (ROW1_Y, ROW2_Y):
        c.rect(0, y - 1, SCREEN_W, 1, CHROME)
        c.rect(0, y + QUAD_H, SCREEN_W, 1, CHROME)
        c.rect(QUAD_W - 1, y, 1, QUAD_H, CHROME)

    y = LEGEND_Y
    for line in LEGEND:
        c.text(font, line, 2, y, INK)
        y += 8
    return c


def build(font: bytes, guides: bool) -> Canvas:
    c = Canvas(SCREEN_W, SCREEN_H)
    c.rect(0, 0, SCREEN_W, SCREEN_H, BG)

    if not guides:
        # The working sheet: nothing but the glyphs, in grid order. Every
        # annotation lives in DEV/FONT_BRIEF.md instead, so nothing on the
        # canvas can be mistaken for content.
        for code in range(256):
            c.glyph(font, code,
                    (code & 31) * CELL_W,
                    (code >> 5) * CELL_H)
        return c

    c.text(font, "S6ED 6x8 FONT SHEET - REFERENCE, DO NOT DRAW ON THIS ONE", 2, 2, CHROME)

    # Guides first, so glyph ink always paints over them. Kept light: a solid
    # rule on the last column of each cell to separate slots, and a dotted mark
    # on column 5 so the reserved pixel is obvious without drowning the glyphs.
    for col in range(32):
        gx = GRID_X + col * CELL_W
        c.rect(gx + CELL_W - 1, GRID_Y, 1, 8 * CELL_H, CHROME)
        for y in range(GRID_Y, GRID_Y + 8 * CELL_H, 2):
            c.set(gx + BOLD_COL, y, WARN)
    # And a rule under each row of cells.
    for row in range(9):
        c.rect(GRID_X, GRID_Y + row * CELL_H - 1, 32 * CELL_W, 1, CHROME)

    for code in range(256):
        gx = GRID_X + (code & 31) * CELL_W
        gy = GRID_Y + (code >> 5) * CELL_H
        c.glyph(font, code, gx, gy)

    for row in range(8):
        c.text(font, "+%02X" % (row * 32), LABEL_X, GRID_Y + row * CELL_H, CHROME)

    # What the two derived weights will look like, generated the same way the
    # engine will generate them. This is why column 5 has to stay empty.
    sample = "Hamburgefonstiv 0123"
    y = GRID_Y + 8 * CELL_H + 10
    for name, fn in (("NORMAL", None), ("BOLD", bold),
                     ("ITALIC", italic), ("BOLD+ITALIC", bolditalic)):
        c.text(font, name, 2, y, CHROME)
        c.text(font, sample, 80, y, INK, transform=fn)
        y += 10

    y += 6
    for line in (
        "RULES",
        "  Ink only in columns 0-4 of each 8x8 cell of the NORMAL block.",
        "  Column 5 (dotted yellow) must stay empty there: it is what keeps",
        "  neighbouring characters from touching. Columns 6-7 are never drawn.",
        "  BOLD, ITALIC and BOLD+ITALIC have blocks of their own on FONTSHEET",
        "  and may use column 5. They arrive pre-filled by machine from NORMAL,",
        "  sampled above; redraw them, that derivation is only a starting point.",
        "  Rows 0-6 for caps and x-height, baseline row 6, row 7 for descenders.",
        "  Monochrome: colour is chosen by the editor, not by the glyph.",
    ):
        c.text(font, line, 2, y, CHROME if line == "RULES" else INK)
        y += 8

    return c


def to_sc6(c: Canvas) -> bytes:
    """Pack to Graphic 5: 2 bits per pixel, 4 pixels per byte, 128 bytes a line."""
    out = bytearray()
    for y in range(SCREEN_H):
        row = c.px[y * c.w:(y + 1) * c.w]
        for x in range(0, SCREEN_W, 4):
            out.append((row[x] << 6) | (row[x + 1] << 4) |
                       (row[x + 2] << 2) | row[x + 3])
    return bytes(out)


# 0 the reserved-column marker, 1 background, 2 guides, 3 ink. 3 bits a channel.
# The clean sheet uses only 1 and 3, so it stays legible under the MSX default
# palette where entry 0 is transparent; the reference sheet spends entry 0 on the
# column 5 dots and is always shipped with its .PL6.
PALETTE = [(255, 255, 0), (0, 0, 0), (36, 100, 220), (255, 255, 255)]


def to_pl6(palette) -> bytes:
    """MSX palette file: 16 entries of [R * 16 + B, G], 3 bits per channel."""
    out = bytearray()
    for i in range(16):
        r, g, b = palette[i] if i < len(palette) else (0, 0, 0)
        out.append(((r >> 5) << 4) | (b >> 5))
        out.append(g >> 5)
    return bytes(out)


def to_png(c: Canvas, palette) -> bytes:
    import zlib
    raw = bytearray()
    for y in range(c.h):
        raw.append(0)
        raw += c.px[y * c.w:(y + 1) * c.w]

    def chunk(tag, data):
        body = tag + data
        return (struct.pack(">I", len(data)) + body +
                struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF))

    plte = b"".join(bytes(p) for p in palette)
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", c.w, c.h, 8, 3, 0, 0, 0))
            + chunk(b"PLTE", plte)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + chunk(b"IEND", b""))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bios", help="MSX main BIOS ROM, to bootstrap from scratch")
    ap.add_argument("--font", help="FONT.BIN to build the sheets from (preferred)")
    ap.add_argument("--cgtable", default="0x1BBF",
                    help="charset offset inside the BIOS (default 0x1BBF)")
    ap.add_argument("--out", default="FONTSHEET", help="output basename")
    ap.add_argument("--guides", action="store_true",
                    help="annotated reference sheet instead of the clean one")
    ap.add_argument("--variants", action="store_true",
                    help="four weight 2x2 working sheet instead of one grid")
    a = ap.parse_args()

    if bool(a.bios) == bool(a.font):
        sys.exit("give exactly one of --bios or --font")
    if a.guides and a.variants:
        sys.exit("--guides and --variants are different sheets; pick one")

    if a.font:
        font = Path(a.font).read_bytes()
        if len(font) != 2048:
            sys.exit("%s is %d bytes, expected 2048" % (a.font, len(font)))
    else:
        font = load_rom_charset(Path(a.bios), int(a.cgtable, 0))
        if len(font) != 2048:
            sys.exit("charset offset is past the end of the ROM")

    base = Path(a.out)
    c = build_variants(font) if a.variants else build(font, guides=a.guides)
    base.with_suffix(".SR6").write_bytes(to_sc6(c))
    base.with_suffix(".PL6").write_bytes(to_pl6(PALETTE))
    # Screen 6 palette as the editor sets it: black, white, blue, yellow.
    base.with_suffix(".PNG").write_bytes(to_png(c, PALETTE))
    for ext in (".SR6", ".PL6", ".PNG"):
        print("%s%s  %d bytes" % (base, ext, base.with_suffix(ext).stat().st_size))


if __name__ == "__main__":
    main()
