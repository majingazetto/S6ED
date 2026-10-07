#!/usr/bin/env python3
"""utf8msx -- convert a UTF-8 text file to the MSX international charset.

A document kept in UTF-8 on the host shows every accented letter as two
glyphs on an MSX: "a acute" is the byte pair C3 A1.  The MSX international
charset puts the Western European letters at the same codes as IBM code page
437 from #80 to #AF (a acute #A0, e acute #82, n tilde #A4, inverted
question mark #A8 ...), which is the range converted here.  Above #AF the two
charsets part ways, so anything that would land there is refused.

    utf8msx.py [--lf] INPUT OUTPUT

Line endings become CR LF, which is what MSX-DOS TYPE and batch files expect;
--lf keeps bare LF.  A character with no MSX equivalent stops the conversion
with its line and column, so a manual never ships a glyph that silently
renders as garbage.
"""

import sys

MSXTOP = 0xAF                   # LAST CODE SHARED WITH CODE PAGE 437


def convert(text):
    out = bytearray()
    errors = []
    for lineno, line in enumerate(text.split('\n'), 1):
        for col, ch in enumerate(line, 1):
            code = ord(ch)
            if code < 0x80:
                out.append(code)
                continue
            try:
                byte = ch.encode('cp437')[0]
            except UnicodeEncodeError:
                byte = None
            if byte is None or byte > MSXTOP:
                errors.append(f'{lineno}:{col}: {ch!r} (U+{code:04X}) has no MSX code')
                continue
            out.append(byte)
        out.append(0x0A)
    if out.endswith(b'\n\n') and text.endswith('\n'):
        del out[-1]             # split() ADDS AN EMPTY LAST LINE
    return bytes(out), errors


def main(argv):
    lf = '--lf' in argv
    args = [a for a in argv if a != '--lf']
    if len(args) != 2:
        sys.exit(__doc__)
    with open(args[0], encoding='utf-8') as f:
        text = f.read().replace('\r\n', '\n')
    data, errors = convert(text)
    if errors:
        for e in errors:
            print(f'{args[0]}:{e}', file=sys.stderr)
        sys.exit(1)
    if not lf:
        data = data.replace(b'\n', b'\r\n')
    with open(args[1], 'wb') as f:
        f.write(data)


if __name__ == '__main__':
    main(sys.argv[1:])
