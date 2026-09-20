"""Paths and the freshly parsed symbol table, threaded through every check."""

import os

import symbols


class Context(object):
    def __init__(self, test_dir, out_dir=None, load_symbols=True):
        self.test_dir = os.path.abspath(test_dir)
        self.project_dir = os.path.dirname(self.test_dir)
        self.code_dir = os.path.join(self.project_dir, 'CODE')
        self.src_dir = os.path.join(self.code_dir, 'SRC')
        self.res_dir = os.path.join(self.project_dir, 'RES')
        self.workspace = os.path.dirname(self.project_dir)
        self.dsktool = os.path.join(self.workspace, 'msxtools', 'bin', 'dsktool')
        self.out_dir = os.path.abspath(out_dir or
                                       os.path.join(self.test_dir, 'out'))
        os.makedirs(self.out_dir, exist_ok=True)
        # Parsed after the build, never before: a stale .sym is the cheapest
        # way to spend a session reading zeros.
        self.sym = symbols.load(self.code_dir) if load_symbols else None

    def reload_symbols(self):
        self.sym = symbols.load(self.code_dir)
        return self.sym

    # The directories the S6ED build actually includes, in the Makefile's
    # order.  A recursive walk is wrong now that SRC holds two targets:
    # UI.Z8A and SCROLL.Z8A exist in both S6/ and S2/, os.walk order is
    # filesystem-dependent, and a mutation that lands in the S2 copy is
    # never compiled into S6ED.COM -- it fails silently as "anchor not
    # found" at best and as an uncaught mutation at worst.
    SRC_PATH = ('', 'CORE', 'S6')

    def find_src_file(self, filename):
        """Find a source file by basename along the S6ED include path."""
        for sub in self.SRC_PATH:
            candidate = os.path.join(self.src_dir, sub, filename)
            if os.path.exists(candidate):
                return candidate
        return os.path.join(self.src_dir, filename)
