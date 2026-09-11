#!/usr/bin/env python3
"""Build the S6ED font sheet handed to the artist.

Produces a 512x212 Screen 6 canvas holding the 256 glyph cells in exactly the
layout the editor blits from: glyph N sits at ((N & 31) * 8, (N >> 5) * 8), so
whatever comes back converts straight into FONT.BIN with no re-layout.

Colour 0 background, colour 1 ink (the only colour the artist draws in),
colour 2 chrome and guides, colour 3 the reserved column.
"""

import argparse
import struct
import sys
from pathlib import Path

CELL_W, CELL_H = 8, 8          # VRAM pitch of one glyph slot
DRAW_W = 5                     # columns 0-4: the artist's area
BOLD_COL = 5                   # column 5: left free so BOLD can grow into it
SCREEN_W, SCREEN_H = 512, 212

GRID_X, GRID_Y = 0, 12         # glyph grid origin
LABEL_X = 264                  # row labels sit right of the grid

BG, INK, CHROME, WARN = 0, 1, 2, 3


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
    """What FONTINIT will do for the bold variant: thicken one pixel right."""
    return [(r | (r >> 1)) & 0xFC for r in rows]


def italic(rows):
    """Top half leans one pixel right, bottom half stays put.

    DESIGN.md proposes +1 +1 +1 +1 0 -1 -1 -1, but shifting the bottom rows the
    other way pushes ink out of column 0 and loses it, and with bit 7 as the
    leftmost pixel that table actually produces a backslant. Leaning only the
    top half into the reserved column 5 is lossless and slants the right way.
    """
    return [(r >> 1) & 0xFC if i < 4 else r & 0xFC
            for i, r in enumerate(rows)]


def build(font: bytes) -> Canvas:
    c = Canvas(SCREEN_W, SCREEN_H)

    c.text(font, "S6ED 6x8 FONT SHEET - DRAW IN WHITE ONLY", 2, 2, CHROME)

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
    for name, fn in (("NORMAL", None), ("BOLD", bold), ("ITALIC", italic)):
        c.text(font, name, 2, y, CHROME)
        c.text(font, sample, 56, y, INK, transform=fn)
        y += 10

    y += 6
    for line in (
        "RULES",
        "  Ink only in columns 0-4 of each 8x8 cell.",
        "  Column 5 (dotted yellow) must stay empty. BOLD grows one pixel right",
        "  into it, ITALIC leans the top half into it, and it is what keeps",
        "  neighbouring characters from touching. Columns 6-7 are never drawn.",
        "  Rows 0-6 for caps and x-height, baseline row 6, row 7 for descenders.",
        "  Monochrome: colour is chosen by the editor, not by the glyph.",
        "  BOLD and ITALIC are generated from this one weight. Do not draw them.",
        "  BOLD fills column 5, so bold text has no gap between letters. Expected.",
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
    ap.add_argument("--bios", required=True, help="MSX main BIOS ROM")
    ap.add_argument("--cgtable", default="0x1BBF",
                    help="charset offset inside the BIOS (default 0x1BBF)")
    ap.add_argument("--out", default="FONTSHEET", help="output basename")
    a = ap.parse_args()

    font = load_rom_charset(Path(a.bios), int(a.cgtable, 0))
    if len(font) != 2048:
        sys.exit("charset offset is past the end of the ROM")

    c = build(font)
    base = Path(a.out)
    base.with_suffix(".SR6").write_bytes(to_sc6(c))
    # Screen 6 palette as the editor sets it: black, white, blue, yellow.
    base.with_suffix(".PNG").write_bytes(
        to_png(c, [(0, 0, 0), (255, 255, 255), (36, 100, 220), (255, 255, 0)]))
    print("%s.SR6  %d bytes" % (base, base.with_suffix('.SR6').stat().st_size))
    print("%s.PNG  %d bytes" % (base, base.with_suffix('.PNG').stat().st_size))


if __name__ == "__main__":
    main()
