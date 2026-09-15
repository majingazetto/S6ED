"""S6ED test harness -- symbol table and source attribution.

Everything the suite asserts about addresses comes from the .sym file that the
build has JUST produced.  Hard-coding an address is the single most expensive
mistake in this harness: a rebuild moves every symbol and a stale script reads
back all zeros, which looks exactly like a broken program.
"""

import os
import re
import sys

SYM_RE = re.compile(r'^([\w.]+):\s*EQU\s*0x([0-9A-Fa-f]+)\s*$')

# A global label sits flush left.  An EQU on the same line makes it a constant
# instead: constants may legitimately hold any value (TXPAGE = #8000), labels
# may not live outside the image.
LABEL_RE = re.compile(r'^([A-Z][A-Z0-9]{0,15})(\s|$)')
EQU_RE = re.compile(r'^([A-Z][A-Z0-9]{0,15})\s+EQU\b')
LOCAL_RE = re.compile(r'^(\.[A-Z0-9]{1,15})(\s|$)')


class Symbols(object):
    """Parsed sjasmplus .sym, plus which source file defined each global."""

    def __init__(self, sym_path, src_dir):
        self.sym_path = sym_path
        self.src_dir = src_dir
        self.addr = {}
        self.owner = {}          # global label -> source file basename
        self.is_const = {}       # global label -> True when defined with EQU
        self._load_sym()
        self._attribute()

    def _load_sym(self):
        with open(self.sym_path) as fh:
            for line in fh:
                m = SYM_RE.match(line.strip())
                if m:
                    self.addr[m.group(1)] = int(m.group(2), 16)
        if not self.addr:
            raise RuntimeError('no symbols parsed from %s' % self.sym_path)

    def _attribute(self):
        for name in sorted(os.listdir(self.src_dir)):
            if not name.endswith('.Z8A'):
                continue
            with open(os.path.join(self.src_dir, name), errors='replace') as fh:
                for line in fh:
                    m = EQU_RE.match(line)
                    if m:
                        self.owner.setdefault(m.group(1), name)
                        self.is_const[m.group(1)] = True
                        continue
                    m = LABEL_RE.match(line)
                    if m:
                        self.owner.setdefault(m.group(1), name)
                        self.is_const.setdefault(m.group(1), False)

    # - accessors -------------------------------------------------------

    def __getitem__(self, name):
        try:
            return self.addr[name]
        except KeyError:
            raise KeyError('symbol %s not in %s (stale build?)'
                           % (name, self.sym_path))

    def get(self, name, default=None):
        return self.addr.get(name, default)

    def globals(self):
        """Every symbol that is not a sjasmplus PARENT.LOCAL entry."""
        return {n: a for n, a in self.addr.items() if '.' not in n}

    def labels_of(self, filename):
        """Global LABELS (not constants) defined in one source file."""
        return {n: self.addr[n] for n in self.addr
                if '.' not in n and self.owner.get(n) == filename
                and not self.is_const.get(n, False) and n in self.addr}


def load(code_dir):
    return Symbols(os.path.join(code_dir, 'S6ED.sym'),
                   os.path.join(code_dir, 'SRC'))


if __name__ == '__main__':
    s = load(sys.argv[1] if len(sys.argv) > 1 else '../CODE')
    print('%d symbols, %d globals' % (len(s.addr), len(s.globals())))
    for n in ('VARS', 'ENDVARS', 'MAINLOOP', 'SCRRDY', 'TOTLINES'):
        print('  %-10s #%04X' % (n, s[n]))
