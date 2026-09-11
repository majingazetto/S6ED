#!/usr/bin/env python3
"""Import an edited font sheet and check it against the S6ED rendering rules.

Reads a sheet back from .SR6 or .PNG, extracts the 256 glyphs from the grid the
editor addresses, reports anything the renderer or the derived weights cannot
cope with, and optionally writes FONT.BIN.

Exit status is non-zero when an error is found, so it can gate a build.
"""

import argparse
import struct
import sys
import zlib
from pathlib import Path

CELL_W, CELL_H = 8, 8
DRAW_W = 5                     # columns 0-4 belong to the artist
BOLD_COL = 5                   # column 5 is headroom for BOLD and ITALIC
SCREEN_W, SCREEN_H = 512, 212
INK_DEFAULT = 3


def read_sr6(path):
    d = path.read_bytes()
    if len(d) not in (SCREEN_W * SCREEN_H // 4, SCREEN_W * SCREEN_H // 4 + 7):
        sys.exit("%s is not a 512x212 Screen 6 page" % path)
    if len(d) % 128:                       # tolerate a BSAVE header
        d = d[7:]
    px = []
    for y in range(SCREEN_H):
        row = []
        for b in d[y * 128:(y + 1) * 128]:
            row += [(b >> 6) & 3, (b >> 4) & 3, (b >> 2) & 3, b & 3]
        px.append(row)
    return px


def read_png(path):
    d = path.read_bytes()
    i, w, h, idat, depth, ctype = 8, None, None, b"", None, None
    while i < len(d):
        ln = struct.unpack(">I", d[i:i + 4])[0]
        tag, body = d[i + 4:i + 8], d[i + 8:i + 8 + ln]
        if tag == b"IHDR":
            w, h, depth, ctype = (*struct.unpack(">II", body[:8]), body[8], body[9])
        elif tag == b"IDAT":
            idat += body
        i += 12 + ln
    if (w, h) != (SCREEN_W, SCREEN_H):
        sys.exit("%s is %dx%d, expected %dx%d" % (path, w, h, SCREEN_W, SCREEN_H))
    if ctype != 3 or depth != 8:
        sys.exit("%s must be an 8-bit indexed PNG" % path)
    raw = zlib.decompress(idat)
    stride = w + 1
    px = []
    prev = bytearray(w)
    for y in range(h):
        f = raw[y * stride]
        line = bytearray(raw[y * stride + 1:(y + 1) * stride])
        if f == 1:
            for x in range(1, w):
                line[x] = (line[x] + line[x - 1]) & 0xFF
        elif f == 2:
            for x in range(w):
                line[x] = (line[x] + prev[x]) & 0xFF
        elif f != 0:
            sys.exit("PNG filter %d not supported; re-save without filtering" % f)
        px.append(list(line))
        prev = line
    return px


def extract(px, ink, origin=(0, 0)):
    """Pull the 256 glyphs out of the grid into 1bpp rows, ink in bits 7-2."""
    font = bytearray(2048)
    for code in range(256):
        gx = origin[0] + (code & 31) * CELL_W
        gy = origin[1] + (code >> 5) * CELL_H
        for r in range(CELL_H):
            byte = 0
            for b in range(CELL_W):
                if px[gy + r][gx + b] == ink:
                    byte |= 0x80 >> b
            font[code * 8 + r] = byte
    return bytes(font)


def check(font, lo=0x20, hi=0x7F):
    errors, warnings, notes = [], [], []
    for n in range(lo, hi):
        g = font[n * 8:n * 8 + 8]
        ch = chr(n)
        if any(b & 0x04 for b in g):
            errors.append("%s (#%02X) draws in column 5, which BOLD and ITALIC "
                          "need and which keeps characters apart" % (ch, n))
        if any(b & 0x03 for b in g):
            warnings.append("%s (#%02X) draws in columns 6-7, never blitted" % (ch, n))
        if not any(g) and n != 0x20:
            notes.append("%s (#%02X) is blank" % (ch, n))
    return errors, warnings, notes


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("sheet", help="edited sheet, .SR6 or .PNG")
    ap.add_argument("--ink", type=int, default=INK_DEFAULT,
                    help="palette index the glyphs are drawn in (default 3)")
    ap.add_argument("--out", help="write the extracted FONT.BIN here")
    ap.add_argument("--origin", default="0,0",
                    help="grid origin in the sheet (the reference sheet is 0,12)")
    ap.add_argument("--strict", action="store_true",
                    help="treat warnings as errors too")
    a = ap.parse_args()

    p = Path(a.sheet)
    px = read_png(p) if p.suffix.lower() == ".png" else read_sr6(p)
    ox, oy = (int(v) for v in a.origin.split(","))
    font = extract(px, a.ink, (ox, oy))
    errors, warnings, notes = check(font)

    glyphs = sum(1 for n in range(256) if any(font[n * 8:n * 8 + 8]))
    print("%s: %d non-blank glyphs, ink index %d" % (p.name, glyphs, a.ink))
    for tag, items in (("ERROR", errors), ("WARN", warnings), ("note", notes)):
        for m in items:
            print("  %-5s %s" % (tag, m))
    if not errors and not warnings:
        print("  all printable glyphs respect the column 0-4 rule")

    if a.out and not errors:
        Path(a.out).write_bytes(font)
        print("wrote %s (%d bytes)" % (a.out, len(font)))

    sys.exit(1 if errors or (a.strict and warnings) else 0)


if __name__ == "__main__":
    main()
