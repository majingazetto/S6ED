"""Paths and the freshly parsed symbol table, threaded through every check."""

import os

import symbols


# The two build targets of the SXED tree.  Everything that differs between them
# lives here: the file-name prefix and the assembler include path -- which is
# also the harness's source-resolution path.  A recursive walk of SRC/ is wrong
# now that it holds two targets: UI.Z8A and SCROLL.Z8A exist in both S6/ and
# S2/, os.walk order is filesystem-dependent, and a mutation that lands in the
# copy the target does not compile fails silently as "anchor not found" at best
# and as an uncaught mutation at worst.
TARGETS = {
    'S6ED': ('', 'CORE', 'S6'),
    'S2ED': ('', 'CORE', 'S2'),
}


class Context(object):
    def __init__(self, test_dir, out_dir=None, load_symbols=True,
                 target='S6ED'):
        self.target = target
        self.prefix = target
        self.SRC_PATH = TARGETS[target]
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
        self.sym = (symbols.load(self.code_dir, self.prefix, self.SRC_PATH)
                    if load_symbols else None)

    def reload_symbols(self):
        self.sym = symbols.load(self.code_dir, self.prefix, self.SRC_PATH)
        return self.sym

    def for_target(self, target):
        """A sibling context on the other target, sharing the output root.

        Symbols are NOT parsed here: that target has not been built yet, and
        a .sym read before its build is the cheapest way to spend a session
        reading zeros.  Call reload_symbols() after building.
        """
        return Context(self.test_dir, self.out_dir, load_symbols=False,
                       target=target)

    def find_src_file(self, filename):
        """Find a source file by basename along this target's include path."""
        for sub in self.SRC_PATH:
            candidate = os.path.join(self.src_dir, sub, filename)
            if os.path.exists(candidate):
                return candidate
        return os.path.join(self.src_dir, filename)
