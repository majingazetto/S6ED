#!/usr/bin/env python3
"""mkfont62 -- S62ED 8x8 fonts: build them from other machines, or from a sheet.

S62ED.FNT is four variants of 2,048 bytes -- NORMAL, BOLD, ITALIC, BOLD+ITALIC,
in that order -- each 256 glyphs of 8 rows, 1bpp, bit 7 the leftmost pixel, in
the MSX international character set order.  All eight columns are blitted:
the letter spacing is whatever the artwork leaves blank (column 7 by custom).

    mkfont62.py import --src CGA-TH.F08 --cp cp437 [--bold-src CGA.F08]
                       --out CGA.FNT [--sheet CGA.PNG]
    mkfont62.py sheet  FONTSHEET.PNG --out S62ED.FNT

`import` takes a raw 2,048-byte 8x8 font in its own machine's order (cp437 for
the IBM PC, cpc for the Amstrad CPC, msx for one already in MSX order) and
remaps every MSX code by MEANING, through Unicode: MSX #A4 is n-tilde, and it
is fetched from wherever the source keeps n-tilde.  A character the source
lacks is composed when it is a letter with a diacritic the source has as a
separate mark (CPC: acute, grave, circumflex, diaeresis and tilde on any base;
cedilla and ring are drawn), and otherwise taken from the MSX BIOS font
(FONT_BIOS8X8.BIN) -- mostly the geometric mosaics at #C0-#DF, which the BIOS
already draws edge to edge.  BOLD comes from --bold-src when the source
machine had one (the IBM CGA's thick font is the bold of its thin one),
otherwise it is derived; ITALIC leans the top half one pixel right.  Box,
block and mosaic characters are never derived: their lines must meet the
neighbouring cell.

`sheet` reads a 512x212 sheet in the FONTSHEET_S64 layout (four 256x64 blocks:
NORMAL at (0,20), BOLD at (256,20), ITALIC at (0,96), BOLD+ITALIC at (256,96),
glyph N at ((N & 31) * 8, (N >> 5) * 8), ink = palette index 3) -- the sheet
`import --sheet` writes and the one the artist draws on.
"""

import argparse
import os
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mkfontsheet_s64 as sheetlib                                  # noqa: E402

FONTSIZ = 2048
HERE = os.path.dirname(os.path.abspath(__file__))

# --- the MSX international character set, as Unicode ---------------------
# 0x01-0x1F are the graphic characters reached through the 0x01 prefix,
# identified on the BIOS bitmaps (#10 and #1F are MSX-only crosses: none).
# 0x80-0xFF from Wikipedia "MSX character set" (MSX International), whose
# source is Unicode L2/19-025; the mosaics outside the BMP are left out, the
# BIOS glyph is the right answer for them anyway.
MSX = {}
for _i, _c in enumerate('☺☻♥♦♣♠•◘'
                        '○◙♂♀♪♫☼', 1):
    MSX[_i] = _c
for _i, _c in enumerate('┴┬┤├┼│─┌'
                        '┐└┘╳╱╲', 0x11):
    MSX[_i] = _c
for _i in range(0x20, 0x7f):
    MSX[_i] = chr(_i)
for _i, _c in enumerate('Çüéâäàåç'
                        'êëèïîìÄÅ'
                        'ÉæÆôöòûù'
                        'ÿÖÜ¢£¥₧ƒ'
                        'áíóúñÑªº'
                        '¿⌐¬½¼¡«»'
                        'ÃãĨĩÕõŨũ'
                        'Ĳĳ¾∽◊‰¶§', 0x80):
    MSX[_i] = _c
for _i, _c in {0xC0: '▂', 0xC1: '▚', 0xC2: '▆', 0xC4: '▬',
               0xC6: '▎', 0xC7: '▞', 0xC8: '▊', 0xD3: '▘',
               0xD4: '▗', 0xD5: '▝', 0xD6: '▖', 0xD8: 'Δ',
               0xD9: '‡', 0xDA: 'ω', 0xDB: '█', 0xDC: '▄',
               0xDD: '▌', 0xDE: '▐', 0xDF: '▀'}.items():
    MSX[_i] = _c
for _i, _c in enumerate('αßΓπΣσµτ'
                        'ΦΘΩδ∞⌀∈∩'
                        '≡±≥≤⌠⌡÷≈'
                        '°∙·√ⁿ²■', 0xE0):
    MSX[_i] = _c

# --- source code pages, as Unicode ---------------------------------------
CP437 = {}
for _i, _c in enumerate('☺☻♥♦♣♠•◘'
                        '○◙♂♀♪♫☼►'
                        '◄↕‼¶§▬↨↑'
                        '↓→←∟↔▲▼', 1):
    CP437[_i] = _c
for _i in range(0x20, 0x100):
    CP437[_i] = bytes([_i]).decode('cp437') if _i != 0x7f else '⌂'

# Amstrad CPC, from Wikipedia "Amstrad CPC character set" (ROM #3800). ASCII
# except #5E (an up arrow, ^ lives at #A0) and #27 (a right single quote).
CPC = {}
for _i in range(0x20, 0x7f):
    CPC[_i] = chr(_i)
CPC[0x27], CPC[0x5e] = '’', '↑'
for _i, _c in enumerate(' ▘▝▀▖▌▞▛'
                        '▗▚▐▜▄▙▟█'
                        '·╵╶└╷│┌├'
                        '╴┘─┴┐┤┬┼'
                        '^´¨£©¶§‘'
                        '¼½¾±÷¬¿¡'
                        'αβγδεθλμ'
                        'πσφψχωΣΩ',
                        0x80):
    CPC[_i] = _c
for _i, _c in {0xCB: '╳', 0xCC: '╱', 0xCD: '╲', 0xCF: '▒',
               0xE0: '☺', 0xE1: '☹', 0xE2: '♣', 0xE3: '♦',
               0xE4: '♥', 0xE5: '♠', 0xE6: '○', 0xE7: '●',
               0xE8: '□', 0xE9: '■', 0xEA: '♂', 0xEB: '♀',
               0xEC: '♩', 0xED: '♪', 0xEE: '☼',
               0xF4: '▲', 0xF5: '▼', 0xF6: '▶',
               0xF7: '◀'}.items():
    CPC[_i] = _c

CODEPAGES = {'cp437': CP437, 'cpc': CPC, 'msx': MSX}

# Spacing forms of the combining marks, looked up in the source font.
MARKS = {'́': '´', '̀': '`', '̂': '^', '̈': '¨',
         '̃': '~'}


def glyph(font, code):
    return list(font[code * 8:code * 8 + 8])


def ink_rows(rows):
    return [i for i, r in enumerate(rows) if r]


def is_graphic(ch):
    """Box drawing, blocks, mosaics, geometric shapes: never derived."""
    return 0x2500 <= ord(ch) <= 0x25ff or ord(ch) >= 0x1fb00


def squeeze(rows, top):
    """Make a glyph start at row `top` or lower by dropping rows.

    A row equal to its neighbour (a straight stem) is dropped first, from the
    middle out, so 'E' loses a stem row and keeps its arms. The baseline never
    moves: an accented letter must sit on the same line as a plain one, which
    is how the IBM CGA and the MSX BIOS draw theirs.
    """
    rows = list(rows)
    while ink_rows(rows) and ink_rows(rows)[0] < top:
        ink = ink_rows(rows)
        first, last = ink[0], ink[-1]
        mid = (first + last) / 2
        dup = [i for i in range(first + 1, last + 1) if rows[i] == rows[i - 1]]
        pick = (min(dup, key=lambda i: abs(i - mid)) if dup else
                min(range(first + 1, last), key=lambda i: abs(i - mid)))
        rows = [0] + rows[:pick] + rows[pick + 1:]
    return rows


def compose(font, uni, cp):
    """A letter with a diacritic the source lacks, built from its parts."""
    parts = unicodedata.normalize('NFD', uni)
    if len(parts) != 2:
        return None
    base, mark = parts
    inv = {v: k for k, v in cp.items()}
    if base not in inv:
        return None
    rows = glyph(font, inv[base])
    if mark == '̧':                            # cedilla: drawn
        ink = ink_rows(rows)
        if not ink or ink[-1] >= 7:
            return None
        cols = rows[ink[-1]]
        left = next(b for b in range(8) if cols & (0x80 >> b))
        hook = (0x80 >> (left + 1)) | (0x80 >> (left + 2))
        rows[ink[-1] + 1] |= hook
        return rows
    if mark == '\u030a':                       # ring: drawn
        mrow = [0x10, 0x28]                         # two rows, or A is squashed
    elif MARKS.get(mark) in inv:
        m = glyph(font, inv[MARKS[mark]])
        ink = ink_rows(m)
        if not ink:
            return None
        # One row for acute, grave and diaeresis -- the CGA's own choice --
        # two for tilde and circumflex, whose shape needs them.
        mark_rows = m[ink[0]:ink[-1] + 1]
        if mark in ('\u0302', '\u0303'):
            mrow = mark_rows[-2:]                       # tilde, circumflex: 2 rows
        elif mark in ('\u0301', '\u0300'):
            mrow = mark_rows[:1]                        # acute, grave: the TOP row,
                                                    # whose offset keeps the slant
        else:
            mrow = mark_rows[-1:]                       # diaeresis: one row
    else:
        return None
    if base in 'ij':                                # a mark replaces the dot:
        ink = ink_rows(rows)                        # drop the rows before the
        gap = next((r for r in range(ink[0], 8) if not rows[r]), None)
        if gap is not None:                         # first blank one
            rows = [0] * gap + rows[gap:]
    rows = squeeze(rows, len(mrow) + 1)
    top = ink_rows(rows)[0]
    for i, r in enumerate(mrow):
        rows[top - 1 - len(mrow) + i] |= r
    return rows


def remap(font, cp, bios):
    """The source font in MSX order. Returns (glyphs, origin per code)."""
    inv = {}
    for code, ch in sorted(cp.items(), reverse=True):
        inv[ch] = code
    out, origin = [], []
    for code in range(256):
        uni = MSX.get(code)
        src = None
        if uni is not None:
            if 0x20 <= code < 0x7f and cp.get(code) == uni:
                src = code
            elif uni in inv:
                src = inv[uni]
            elif 0x20 <= code < 0x7f:
                src = code                          # ' and the like
        if src is not None:
            out.append(glyph(font, src))
            origin.append('src')
            continue
        made = compose(font, uni, cp) if uni else None
        if made:
            out.append(made)
            origin.append('composed')
        else:
            out.append(glyph(bios, code))
            origin.append('bios')
    return out, origin


def derive(glyphs, fn):
    return [rows if not MSX.get(code) or is_graphic(MSX[code])
            else fn(rows) for code, rows in enumerate(glyphs)]


def pack(glyphs):
    return bytes(b & 0xFF for rows in glyphs for b in rows)


def write_sheet(path, variants, title):
    c = sheetlib.Canvas(sheetlib.SCREEN_W, sheetlib.SCREEN_H)
    c.rect(0, 0, sheetlib.SCREEN_W, sheetlib.SCREEN_H, sheetlib.BG)
    normal = pack(variants[0])
    c.text(normal, title[:63], 2, sheetlib.TITLE_Y, sheetlib.CHROME)
    for (name, (qx, qy), _), glyphs in zip(sheetlib.VARIANTS, variants):
        font = pack(glyphs)
        c.text(normal, name, qx + 2, qy - 9, sheetlib.CHROME)
        for code in range(256):
            c.glyph(font, code, qx + (code & 31) * 8, qy + (code >> 5) * 8)
    for y in (sheetlib.ROW1_Y, sheetlib.ROW2_Y):
        c.rect(0, y - 1, sheetlib.SCREEN_W, 1, sheetlib.CHROME)
        c.rect(0, y + sheetlib.QUAD_H, sheetlib.SCREEN_W, 1, sheetlib.CHROME)
        # No vertical divider: x = 255 is column 7 of glyph column 31, and
        # FONTSHEET_S64's divider there painted over '_', the upper half
        # block and every other glyph that reaches the right edge.
    y = sheetlib.LEGEND_Y
    for line in ('S62ED 8x8 font sheet, four weights, MSX international order.',
                 'Glyph N at ((N & 31) * 8, (N >> 5) * 8) in each 256x64 block.',
                 'Ink is palette index 3. Rebuild: mkfont62.py sheet THIS.PNG',
                 'Hamburgefonstiv 0123 áéíóú '
                 'ñÑ ¿? ¡!'):
        c.text(normal, ''.join(chr(_msx_code(ch)) for ch in line), 2, y,
               sheetlib.INK)
        y += 9
    with open(path, 'wb') as fh:
        fh.write(sheetlib.to_png(c, sheetlib.PALETTE))


def _msx_code(ch):
    for code, uni in MSX.items():
        if uni == ch:
            return code
    return 0x3f


def read_sheet(path):
    from PIL import Image
    im = Image.open(path)
    if im.mode != 'P' or im.size != (sheetlib.SCREEN_W, sheetlib.SCREEN_H):
        sys.exit('%s: want an 8-bit indexed %dx%d PNG, got %s %s'
                 % (path, sheetlib.SCREEN_W, sheetlib.SCREEN_H, im.mode, im.size))
    px = im.load()
    out = bytearray()
    for _, (qx, qy), _ in sheetlib.VARIANTS:
        for code in range(256):
            gx, gy = qx + (code & 31) * 8, qy + (code >> 5) * 8
            for r in range(8):
                b = 0
                for x in range(8):
                    if px[gx + x, gy + r] == sheetlib.INK:
                        b |= 0x80 >> x
                out.append(b)
    return bytes(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    imp = sub.add_parser('import', help='remap a raw 8x8 font into S62ED.FNT')
    imp.add_argument('--src', required=True, help='raw 2,048-byte 8x8 font')
    imp.add_argument('--cp', required=True, choices=sorted(CODEPAGES))
    imp.add_argument('--bold-src', help='the same machine\'s bold font, if any')
    imp.add_argument('--bios', default=os.path.join(HERE, 'FONT_BIOS8X8.BIN'))
    imp.add_argument('--title', default='S62ED 8x8 font')
    imp.add_argument('--out', required=True)
    imp.add_argument('--sheet', help='also write the editable PNG sheet')
    imp.add_argument('--report', action='store_true',
                     help='list the codes composed or taken from the BIOS')
    sh = sub.add_parser('sheet', help='build S62ED.FNT from a PNG sheet')
    sh.add_argument('png')
    sh.add_argument('--out', required=True)
    a = ap.parse_args()

    if a.cmd == 'sheet':
        data = read_sheet(a.png)
    else:
        def load(p):
            data = open(p, 'rb').read()
            if len(data) != FONTSIZ:
                sys.exit('%s: %d bytes, want %d' % (p, len(data), FONTSIZ))
            return data
        cp, bios = CODEPAGES[a.cp], load(a.bios)
        normal, origin = remap(load(a.src), cp, bios)
        if a.bold_src:
            bold, _ = remap(load(a.bold_src), cp, bios)
        else:
            bold = derive(normal, sheetlib.bold8)
        variants = [normal, bold, derive(normal, sheetlib.italic8),
                    derive(bold, sheetlib.italic8)]
        data = b''.join(pack(v) for v in variants)
        if a.sheet:
            write_sheet(a.sheet, variants, a.title)
        if a.report:
            for kind in ('composed', 'bios'):
                codes = [c for c in range(256) if origin[c] == kind]
                print('%-8s %3d: %s' % (kind, len(codes), ' '.join(
                    '%02X%s' % (c, MSX[c] if c in MSX and c >= 0x20 else '')
                    for c in codes)))
    if len(data) != 4 * FONTSIZ:
        sys.exit('internal: %d bytes' % len(data))
    with open(a.out, 'wb') as fh:
        fh.write(data)
    print('wrote %s (%d bytes)' % (a.out, len(data)))


if __name__ == '__main__':
    main()
