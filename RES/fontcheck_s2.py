#!/usr/bin/env python3
"""Import and validate a 4x8 font sheet for S2ED (MSX SCREEN 2).

Reads a 16x16 glyph sheet (81x145 px, 1px grid between glyphs) from .PNG,
extracts the 256 glyphs (4x8 pixels each), packs them into high-nibble bytes
(bit 7..4 = pixels 0..3, bit 3..0 = 0), and writes a 2048-byte binary file.

Usage:
    python3 fontcheck_s2.py FONT4X8.PNG [--out S2ED.FNT]
"""

import argparse
import os
import sys

try:
    from PIL import Image
except ImportError:
    Image = None


GW, GH = 4, 8
COLS, ROWS = 16, 16
NCH = 256
SHEET_W = COLS * (GW + 1) + 1  # 81 px
SHEET_H = ROWS * (GH + 1) + 1  # 145 px
EXPECTED_LEN = NCH * GH        # 2048 bytes


def extract_glyphs_pil(im):
    rgb = im.convert("RGB")
    data = bytearray()
    for ch in range(NCH):
        cx = (ch % COLS) * (GW + 1) + 1
        cy = (ch // COLS) * (GH + 1) + 1
        for gy in range(GH):
            b = 0
            for gx in range(GW):
                r, g, b_val = rgb.getpixel((cx + gx, cy + gy))
                # Ink pixel if not dark background (threshold 64)
                if r > 64 or g > 64 or b_val > 64:
                    b |= (0x80 >> gx)
            data.append(b)
    return bytes(data)


def main():
    ap = argparse.ArgumentParser(description="Compile 4x8 font sheet for S2ED.")
    ap.add_argument("sheet", help="Path to 4x8 font PNG sheet (81x145 px)")
    ap.add_argument("--out", "-o", default=None, help="Output binary file (default: FONTS_S2.BIN)")
    args = ap.parse_args()

    if not os.path.exists(args.sheet):
        sys.exit("Error: sheet file not found: %s" % args.sheet)

    if Image is None:
        sys.exit("Error: PIL/Pillow is required to run fontcheck_s2.py")

    im = Image.open(args.sheet)
    if im.size != (SHEET_W, SHEET_H):
        sys.exit("Error: unexpected sheet dimensions %r, expected (%d, %d)"
                 % (im.size, SHEET_W, SHEET_H))

    data = extract_glyphs_pil(im)
    if len(data) != EXPECTED_LEN:
        sys.exit("Error: extracted %d bytes, expected %d" % (len(data), EXPECTED_LEN))

    out_path = args.out or os.path.join(os.path.dirname(args.sheet), "FONTS_S2.BIN")
    with open(out_path, "wb") as f:
        f.write(data)

    print("Successfully extracted %d glyphs (%d bytes) -> %s"
          % (NCH, len(data), out_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
