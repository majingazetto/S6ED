"""Screen 2 verdicts with no golden images.

The S6 gate compares the screen against the screen: `G7/render-pure` repaints
with a full REDRAW and diffs, which proves the differential painters agree with
the bulk painter but says nothing about whether either is right.  On S2 we can
do better, because the whole rendering pipeline is closed-form:

    cell(c) = FONT4H[text[2c]] | FONT4L[text[2c + 1]]
    FONT4L  = FONT4H with the nibbles swapped

so the pattern table the VDP should be holding can be COMPUTED in Python from
`S2ED.FNT` and the document text, and compared byte for byte.  Nothing is
captured from a previous run, so nothing can be blessed by accident -- which is
exactly what the six defects of rounds 2 and 3 needed and did not have.

VRAM layout (CONST_S2.Z8A):

    #0000  pattern generator  6144 B   row r at r * 256, cell c at + c * 8
    #1800  name table          768 B   filled 0..255 x3, so every cell owns a
                                       unique pattern and the screen is a bitmap
    #2000  colour table       6144 B   same addressing as the patterns
"""

import os

ROWLEN = 256            # one screen row of patterns: 32 cells x 8 bytes
CELLS = 32              # cells per row
COLS = 64               # text columns (two 4 px characters per cell)
ROWS = 24               # physical screen rows
PATLEN = ROWLEN * ROWS  # 6144

MNUROW, TXRFIRST, TXRLAST, STBROW = 0, 1, 22, 23
ROWSVIS = TXRLAST - TXRFIRST + 1        # 22 document lines on screen

COLTXT, COLUI, COLBOLD = 0xF1, 0x1F, 0xB1


def load_font(ctx):
    """FONT4H and FONT4L exactly as FONTINIT builds them in VIDSEG."""
    path = os.path.join(ctx.code_dir, 'S2ED.FNT')
    with open(path, 'rb') as fh:
        high = fh.read()
    if len(high) != 2048:
        raise RuntimeError('S2ED.FNT is %d bytes, expected 2048' % len(high))
    low = bytes(((b << 4) | (b >> 4)) & 0xFF for b in high)
    return high, low


def compose_row(font, text):
    """The 256 pattern bytes one screen row must hold for `text`."""
    high, low = font
    line = text.ljust(COLS)[:COLS]
    out = bytearray()
    for cell in range(CELLS):
        l = ord(line[cell * 2]) & 0xFF
        r = ord(line[cell * 2 + 1]) & 0xFF
        for y in range(8):
            out.append(high[l * 8 + y] | low[r * 8 + y])
    return bytes(out)


def row_of(dump, row):
    """The 256 pattern bytes of one screen row, out of a #0000 dump."""
    return dump[row * ROWLEN:(row + 1) * ROWLEN]


def colour_row(dump, row):
    """The 256 colour bytes of one screen row, out of a #2000 dump."""
    return dump[row * ROWLEN:(row + 1) * ROWLEN]


def expected_screen(font, lines, topline):
    """Text rows 1..22 for a document scrolled to `topline`.

    Short documents leave the remaining rows blank, exactly as REDRAW does.
    """
    out = {}
    for i in range(ROWSVIS):
        n = topline + i
        out[TXRFIRST + i] = lines[n] if n < len(lines) else ''
    return {row: compose_row(font, text) for row, text in out.items()}


def mismatched_rows(dump, font, lines, topline, cursor=None):
    """Which text rows differ from the computed expectation, and how.

    `cursor` is (row, col) in screen coordinates: the cursor is an inversion
    of one text column and it BLINKS, so that one column may legitimately
    differ at any given instant.  Nothing else may.
    """
    want = expected_screen(font, lines, topline)
    cur_row, cur_col = cursor if cursor else (None, None)
    bad = []
    for row in sorted(want):
        got = row_of(dump, row)
        if got == want[row]:
            continue
        cols = differing_columns(got, want[row])
        if row == cur_row and cols in ([], [cur_col]):
            continue
        bad.append((row, cols[:8]))
    return bad


def invert_column(pattern_row, col):
    """A row of patterns with one text column's 4 pixel columns inverted.

    This is PATINV: a text column owns the high or the low nibble of its
    cell's 8 pattern bytes, and inverting it is what gives a one-column cursor
    and a selection a differential painter can extend one column at a time.
    The colour table cannot do it -- it addresses 8x1 slices, and a slice
    spans both characters of the cell, which is what made the cursor two
    characters wide and made consecutive selection deltas cancel out.
    """
    out = bytearray(pattern_row)
    cell, half = divmod(col, 2)
    mask = 0xF0 if half == 0 else 0x0F
    for y in range(8):
        out[cell * 8 + y] ^= mask
    return bytes(out)


def inverted_columns(got_row, plain_row):
    """Which text columns of a row are the inverse of the plain render."""
    cols = []
    for col in range(COLS):
        cell, half = divmod(col, 2)
        mask = 0xF0 if half == 0 else 0x0F
        g = [got_row[cell * 8 + y] & mask for y in range(8)]
        p = [plain_row[cell * 8 + y] & mask for y in range(8)]
        if g == [(~b) & mask for b in p]:
            cols.append(col)
    return cols


def differing_columns(a_row, b_row):
    """Which text columns differ at all between two rows of patterns."""
    cols = []
    for col in range(COLS):
        cell, half = divmod(col, 2)
        mask = 0xF0 if half == 0 else 0x0F
        if any((a_row[cell * 8 + y] ^ b_row[cell * 8 + y]) & mask
               for y in range(8)):
            cols.append(col)
    return cols


def uniform_colour_cells(coldump, row):
    """(cells whose 8 colour bytes agree, the set of colours they carry).

    COLMAP holds ONE byte per cell and COLDMPC expands it x8 on the way out,
    so a cell whose eight scanlines disagree means the expansion is broken.
    """
    crow = colour_row(coldump, row)
    uniform, colours = 0, set()
    for cell in range(CELLS):
        vals = {crow[cell * 8 + y] for y in range(8)}
        if len(vals) == 1:
            uniform += 1
            colours |= vals
    return uniform, colours
