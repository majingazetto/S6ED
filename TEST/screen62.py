"""S62ED screen model: what page 0 must hold, computed from S62ED.FNT.

S62ED's cells are 8x8 and byte aligned -- column c starts at x = 8 + 8 * c,
two bytes of Screen 6 (four 2-bit pixels per byte) -- so the expected image of
any text cell is the glyph's eight 1bpp rows expanded to 2bpp, with no
neighbouring cell involved.  That makes the S2 gate's method possible here
too: no golden images, the verdict is computed from the font and the document.

Text area:  rows 1..24, y = 8 * row, ink COL_FG (%01) on COL_BG (%00).
Status bar: text at y = 202, x = 8 + 8 * c, ink COL_FG on COL_UI (%10) --
            the UI-paper copy EXPSTAT builds in the right half of the font.
Cursor:     DRWCUR XORs the cell with COL_FG, so a cell under the cursor is
            accepted either plain or with every pixel XOR %01 (its blink
            phase at the moment of the dump).
"""

import os

LINE = 128                  # bytes per Screen 6 scanline
CELLW = 8
TXORG_X = 8
ROWS = 24                   # text rows 1..24
COLS = 62
STB_X = 8
STB_Y = 202
STATCOLS = 62

COL_BG, COL_FG, COL_UI, COL_HI = 0, 1, 2, 3


NORMAL, BOLD, ITALIC, BOLDITALIC = 0, 1, 2, 3


def load_font(ctx, variant=NORMAL):
    """One variant of the shipped S62ED.FNT (2,048 bytes).

    Window titles and the selected menu item are drawn BOLD: compare them
    with the BOLD variant.  With a font whose four variants are equal (the
    BIOS one S62ED first shipped) any variant would do, which is exactly why
    the distinction went unnoticed until the CGA font arrived.
    """
    path = os.path.join(ctx.code_dir, 'S62ED.FNT')
    if not os.path.exists(path):
        return None
    with open(path, 'rb') as fh:
        return fh.read()[variant * 2048:(variant + 1) * 2048]


def expand(bits, ink, paper):
    """One 1bpp glyph row -> the two Screen 6 bytes it paints."""
    out = []
    for half in (0, 4):
        byte = 0
        for k in range(4):
            on = bits & (0x80 >> (half + k))
            byte = (byte << 2) | (ink if on else paper)
        out.append(byte)
    return bytes(out)


def cell_bytes(screen, x, y):
    """The 8 rows x 2 bytes of the cell whose top-left pixel is (x, y)."""
    off = x // 4
    return [bytes(screen[(y + r) * LINE + off:(y + r) * LINE + off + 2])
            for r in range(8)]


def expected_cell(font, ch, ink=COL_FG, paper=COL_BG):
    return [expand(font[ch * 8 + r], ink, paper) for r in range(8)]


def inverted(rows):
    return [bytes(b ^ 0x55 for b in row) for row in rows]


def visible_text(lines, top, left):
    """The 24 x 62 characters the text area should show."""
    out = []
    for r in range(ROWS):
        n = top + r
        s = lines[n] if n < len(lines) else ''
        s = s[left:left + COLS]
        out.append(s.ljust(COLS))
    return out


def text_mismatches(screen, font, lines, top=0, left=0, cursor=None):
    """Cells of the text area that differ from the computed image.

    screen: a 'screen' dump (212 x 128 bytes, page 0 from line 0).
    cursor: (row, col) on screen, 0-based in the text area, or None.
    Returns [(row, col), ...].
    """
    bad = []
    for r, text in enumerate(visible_text(lines, top, left)):
        y = 8 * (r + 1)
        for c, ch in enumerate(text):
            got = cell_bytes(screen, TXORG_X + CELLW * c, y)
            want = expected_cell(font, ord(ch) & 0xFF)
            if got == want:
                continue
            if cursor == (r, c) and got == inverted(want):
                continue
            bad.append((r, c))
    return bad


def margin_dirty(screen):
    """Text-area scanlines with ink in the 8 px margins (x 0..7, 504..511)."""
    bad = []
    for y in range(8, 200):
        row = screen[y * LINE:(y + 1) * LINE]
        if row[0] or row[1] or row[126] or row[127]:
            bad.append(y)
    return bad


def status_mismatches(screen, font, statbuf):
    """Status bar cells that differ from STATBUF rendered on UI paper."""
    bad = []
    for c in range(STATCOLS):
        ch = statbuf[c] if c < len(statbuf) and statbuf[c] else 0x20
        got = cell_bytes(screen, STB_X + CELLW * c, STB_Y)
        if got != expected_cell(font, ch, COL_FG, COL_UI):
            bad.append(c)
    return bad


def cell_text(screen, font, x, y, count, ink=COL_FG, paper=COL_BG):
    """Read `count` cells starting at (x, y) back into text ('?' = unknown)."""
    table = {}
    for ch in range(32, 256):
        table.setdefault(b''.join(expected_cell(font, ch, ink, paper)), chr(ch))
    out = []
    for i in range(count):
        got = b''.join(cell_bytes(screen, x + CELLW * i, y))
        out.append(table.get(got, '?'))
    return ''.join(out)
