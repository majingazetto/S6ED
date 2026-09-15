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
