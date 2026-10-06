#!/usr/bin/env python3
"""Build the S64ED (MSX2 Screen 6, 64-columns) 8x8 font sheets for the artist.

Produces a 512x212 Screen 6 canvas holding the 256 glyph cells in exactly the
layout the S64ED editor blits from: glyph N sits at ((N & 31) * 8, (N >> 5) * 8).

Four 256x64 blocks in a 2x2 arrangement:
  - Top:    NORMAL (0, 20)       BOLD (256, 20)
  - Bottom: ITALIC (0, 96)       BOLD+ITALIC (256, 96)

Pre-fills NORMAL with the native 8x8 MSX BIOS CGROM font, and the three variants
with machine derivations as clean starting points for retouching.

Colour indices:
  0 = Guide markers / warn (yellow)
  1 = Background (black)
  2 = Chrome, labels & frame (blue)
  3 = Ink (white)
"""

import argparse
import os
import struct
import sys
import zlib
from pathlib import Path

CELL_W, CELL_H = 8, 8
SCREEN_W, SCREEN_H = 512, 212
QUAD_W, QUAD_H = 32 * CELL_W, 8 * CELL_H  # 256 x 64 px

TITLE_Y = 1
ROW1_Y, ROW2_Y = 20, 96
LEGEND_Y = 163

GRID_X, GRID_Y = 0, 12
LABEL_X = 264

BG, INK, CHROME, WARN = 1, 3, 2, 0
PALETTE = [(255, 255, 0), (0, 0, 0), (36, 100, 220), (255, 255, 255)]


def find_default_bios() -> Path:
    candidates = [
        Path("msx_dma_sw/modules/rom_patches/RES/hb-20p_basic-bios1.rom"),
        Path(os.path.expanduser("~/.openmsx/share/systemroms/machines/philips/nms8250_basic-bios2.rom")),
        Path(os.path.expanduser("~/.openmsx/share/systemroms/machines/sony/hb-20p_basic-bios1.rom")),
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


def load_rom_charset(bios_path: Path, offset: int = 0x1BBF) -> bytes:
    data = bios_path.read_bytes()
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
            for b in range(8):
                if byte & (0x80 >> b):
                    self.set(x + b, y + r, colour)

    def text(self, font, s, x, y, colour=INK, advance=8, transform=None):
        for i, ch in enumerate(s):
            self.glyph(font, ord(ch), x + i * advance, y, colour, transform)


def bold8(rows):
    """Thicken 1 pixel right, keeping single-pixel counters/holes open."""
    out = []
    for r in rows:
        hole = (~r) & (r >> 1) & (r << 1) & 0xFE
        out.append(((r | (r >> 1)) & ~hole) & 0xFF)
    return out


def italic8(rows):
    """Slant top rows 1 pixel right."""
    return [(r >> 1) & 0xFF if i < 4 else r
            for i, r in enumerate(rows)]


def bolditalic8(rows):
    return bold8(italic8(rows))


VARIANTS = (
    ("NORMAL",      (0,      ROW1_Y), None),
    ("BOLD",        (QUAD_W, ROW1_Y), bold8),
    ("ITALIC",      (0,      ROW2_Y), italic8),
    ("BOLD+ITALIC", (QUAD_W, ROW2_Y), bolditalic8),
)

LEGEND = (
    "S64ED (MSX2 Screen 6, 64 cols): 8x8 font sheet in four weights. Draw on this one.",
    "Blocks: NORMAL & BOLD (top, y=20), ITALIC & BOLD+ITALIC (bottom, y=96).",
    "Each block is 256x64 px (32x8 glyphs). Glyph N sits at ((N & 31)*8, (N >> 5)*8).",
    "Full 8x8 pixels per cell. Col 7 is normally letter-gap; symbols/boxes may use cols 0-7.",
    "Bold, Italic & Bold+Italic are pre-filled by machine from Normal. Retouch or redraw freely.",
    "Palette: 1=Black (BG), 3=White (Ink), 2=Blue (Guides/Chrome). Export as 8-bit PNG.",
)


def build_variants(font: bytes) -> Canvas:
    """The four-weight working sheet for S64ED."""
    c = Canvas(SCREEN_W, SCREEN_H)
    c.rect(0, 0, SCREEN_W, SCREEN_H, BG)
    c.text(font, "S64ED 8x8 FONT SHEET - FOUR WEIGHTS - DRAW ON THIS ONE",
           2, TITLE_Y, CHROME, advance=8)

    for name, (qx, qy), fn in VARIANTS:
        c.text(font, name, qx + 2, qy - CELL_H - 1, CHROME, advance=8)
        for code in range(256):
            c.glyph(font, code,
                    qx + (code & 31) * CELL_W,
                    qy + (code >> 5) * CELL_H,
                    transform=fn)

    for y in (ROW1_Y, ROW2_Y):
        c.rect(0, y - 1, SCREEN_W, 1, CHROME)
        c.rect(0, y + QUAD_H, SCREEN_W, 1, CHROME)
        # No vertical divider at x = QUAD_W - 1: that is column 7 of glyph
        # column 31, and a divider there painted over '_', the upper half
        # block and every glyph reaching the right edge (found 2026-10-06 by
        # mkfont62's sheet round trip).

    y = LEGEND_Y
    for line in LEGEND:
        c.text(font, line, 2, y, INK, advance=8)
        y += 8
    return c


def build_guide(font: bytes) -> Canvas:
    """Single labelled grid reference sheet with guidelines for 8x8."""
    c = Canvas(SCREEN_W, SCREEN_H)
    c.rect(0, 0, SCREEN_W, SCREEN_H, BG)

    c.text(font, "S64ED 8x8 FONT SHEET - REFERENCE GUIDE (DO NOT DRAW ON THIS ONE)",
           2, 2, CHROME, advance=8)

    # Grid guides
    for col in range(32):
        gx = GRID_X + col * CELL_W
        c.rect(gx + CELL_W - 1, GRID_Y, 1, 8 * CELL_H, CHROME)
        # Dotted line on col 7 (the standard letter spacing column)
        for y in range(GRID_Y, GRID_Y + 8 * CELL_H, 2):
            c.set(gx + 7, y, WARN)

    # Horizontal row rules
    for row in range(9):
        c.rect(GRID_X, GRID_Y + row * CELL_H - 1, 32 * CELL_W, 1, CHROME)

    # 256 glyphs
    for code in range(256):
        gx = GRID_X + (code & 31) * CELL_W
        gy = GRID_Y + (code >> 5) * CELL_H
        c.glyph(font, code, gx, gy)

    # Row hex labels
    for row in range(8):
        c.text(font, "+%02X" % (row * 32), LABEL_X, GRID_Y + row * CELL_H, CHROME, advance=8)

    # Samples
    sample = "Hamburgefonstiv 0123"
    y = GRID_Y + 8 * CELL_H + 10
    for name, fn in (("NORMAL", None), ("BOLD", bold8),
                     ("ITALIC", italic8), ("BOLD+ITALIC", bolditalic8)):
        c.text(font, name, 2, y, CHROME, advance=8)
        c.text(font, sample, 96, y, INK, advance=8, transform=fn)
        y += 10

    y += 6
    rules = (
        "RULES FOR 8x8 FONT (S64ED):",
        "  Full 8x8 pixels per cell are blitted directly via high-speed VDP HMMM.",
        "  Col 7 (dotted yellow) is the standard gap for proportional/running text.",
        "  Cols 0-7: Box-drawing, block symbols, and full-width glyphs may use all 8 cols.",
        "  Four weights: NORMAL, BOLD, ITALIC, BOLD+ITALIC on FONTSHEET_S64.",
        "  Monochrome: colour is chosen by editor themes (Color 1=BG, Color 3=Ink).",
    )
    for line in rules:
        c.text(font, line, 2, y, CHROME if "RULES" in line else INK, advance=8)
        y += 8

    return c


def to_sc6(c: Canvas) -> bytes:
    """Pack to Graphic 5 (Screen 6): 2bpp, 4 pixels per byte, 128 bytes/line."""
    out = bytearray()
    for y in range(SCREEN_H):
        row = c.px[y * c.w:(y + 1) * c.w]
        for x in range(0, SCREEN_W, 4):
            out.append((row[x] << 6) | (row[x + 1] << 4) |
                       (row[x + 2] << 2) | row[x + 3])
    return bytes(out)


def to_pl6(palette) -> bytes:
    """MSX palette file: 16 entries of [R * 16 + B, G], 3 bits per channel."""
    out = bytearray()
    for i in range(16):
        r, g, b = palette[i] if i < len(palette) else (0, 0, 0)
        out.append(((r >> 5) << 4) | (b >> 5))
        out.append(g >> 5)
    return bytes(out)


def to_png(c: Canvas, palette) -> bytes:
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
    ap.add_argument("--bios", help="MSX main BIOS ROM path")
    ap.add_argument("--font", help="Raw 2048-byte 8x8 font binary")
    ap.add_argument("--cgtable", default="0x1BBF", help="Offset in BIOS ROM (default 0x1BBF)")
    ap.add_argument("--out", default="FONTSHEET_S64", help="Output basename")
    ap.add_argument("--guides", action="store_true", help="Generate reference guide sheet")
    a = ap.parse_args()

    font = None
    if a.font:
        font = Path(a.font).read_bytes()
        if len(font) != 2048:
            sys.exit(f"Font file {a.font} is {len(font)} bytes, expected 2048.")
    else:
        bios_path = Path(a.bios) if a.bios else find_default_bios()
        if not bios_path or not bios_path.is_file():
            sys.exit("Error: No BIOS ROM specified or found in default locations.")
        font = load_rom_charset(bios_path, int(a.cgtable, 0))
        if len(font) != 2048:
            sys.exit(f"Failed to read 2048 bytes from {bios_path} at {a.cgtable}.")

    base = Path(a.out)
    c = build_guide(font) if a.guides else build_variants(font)

    base.with_suffix(".SR6").write_bytes(to_sc6(c))
    base.with_suffix(".PL6").write_bytes(to_pl6(PALETTE))
    base.with_suffix(".PNG").write_bytes(to_png(c, PALETTE))

    for ext in (".SR6", ".PL6", ".PNG"):
        p = base.with_suffix(ext)
        print(f"Wrote {p} ({p.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
