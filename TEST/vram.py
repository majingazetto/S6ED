"""Screen 6 VRAM decoding, for verdicts taken off the screen itself.

G5 (Graphic 5) packs 4 pixels into every byte, 2 bits each, leftmost pixel in
the high bits, 128 bytes per display line.  Getting this wrong in the other
direction is what produced the clock residue: HMMV counts BYTES, so an NX of 30
truncates to 28 and leaves two pixel columns of the previous digit standing.
"""

BYTES_PER_LINE = 128
CELLW = 6
CELLH = 8
MARGPX = 16                 # text area X origin
TEXT_FIRST_LINE = 8         # display line of text row 0 (row 0 is the menu)

COL_BG, COL_FG, COL_UI, COL_HI = 0, 1, 2, 3


def pixel(buf, x, line, first_line=0):
    """Colour index at absolute pixel (x, line) inside a dump."""
    off = (line - first_line) * BYTES_PER_LINE + (x >> 2)
    return (buf[off] >> ((3 - (x & 3)) * 2)) & 3


def cell_rect(col, row):
    """Pixel box of one text cell, in text-area coordinates."""
    x0 = MARGPX + col * CELLW
    y0 = TEXT_FIRST_LINE + row * CELLH
    return x0, y0, CELLW, CELLH


def diff(a, b, ignore_cells=(), first_line=TEXT_FIRST_LINE):
    """Differing pixels between two dumps, skipping whole text cells.

    The cursor is an LMMV XOR over a cell and it blinks, so two dumps taken at
    the same document state legitimately differ there.  Everything else must
    match exactly.
    """
    if a is None or b is None or len(a) != len(b):
        return [(-1, -1)]
    boxes = [cell_rect(c, r) for (c, r) in ignore_cells]
    out = []
    for off in range(len(a)):
        if a[off] == b[off]:
            continue
        line = first_line + off // BYTES_PER_LINE
        base = (off % BYTES_PER_LINE) * 4
        for i in range(4):
            x = base + i
            if pixel(a, x, line, first_line) == pixel(b, x, line, first_line):
                continue
            if any(x0 <= x < x0 + w and y0 <= line < y0 + h
                   for (x0, y0, w, h) in boxes):
                continue
            out.append((x, line))
    return out


def ink_mask(buf, x0, y0, w=CELLW, h=CELLH, ground=COL_UI, first_line=0):
    """Which pixels of a box are NOT the background colour."""
    return [[pixel(buf, x0 + dx, y0 + dy, first_line) != ground
             for dx in range(w)] for dy in range(h)]


def glyph_mask(font, ch, variant=0, width=CELLW):
    """The 1bpp glyph bitmap as the font asset stores it.

    S6ED.FNT is four 2048-byte variants back to back: 256 glyphs of 8 bytes,
    one byte per scanline, MSB = column 0.  Only the first `width` columns are
    ever blitted.
    """
    base = variant * 2048 + (ch if isinstance(ch, int) else ord(ch)) * 8
    rows = font[base:base + 8]
    return [[bool(rows[y] & (0x80 >> x)) for x in range(width)]
            for y in range(8)]


def render_text(buf, rows=24, cols=80, font=None, first_line=TEXT_FIRST_LINE):
    """Best-effort OCR of the text area, for readable failure messages."""
    if font is None:
        return None
    table = {}
    for code in range(32, 127):
        table[tuple(tuple(r) for r in glyph_mask(font, code))] = chr(code)
    out = []
    for row in range(rows):
        line = []
        for col in range(cols):
            x0, y0, w, h = cell_rect(col, row)
            key = tuple(tuple(r) for r in
                        ink_mask(buf, x0, y0, w, h, ground=COL_BG,
                                 first_line=first_line))
            line.append(table.get(key, '?'))
        out.append(''.join(line).rstrip())
    return out
