"""Shared result types and the console report."""


class Check(object):
    """One assertion: a name, a verdict and enough detail to act on it."""

    def __init__(self, name, ok, detail='', xfail=False):
        self.name = name
        self.ok = bool(ok)
        self.detail = detail
        self.xfail = xfail

    @property
    def status(self):
        if self.xfail:
            return 'XPASS' if self.ok else 'XFAIL'
        return 'PASS' if self.ok else 'FAIL'

    @property
    def counts_as_failure(self):
        # An XFAIL that starts passing is a failure too: the deficiency was
        # fixed and nobody updated the suite.
        return (not self.ok) if not self.xfail else self.ok


GREEN, RED, YELLOW, GREY, RESET = (
    '\033[32m', '\033[31m', '\033[33m', '\033[90m', '\033[0m')

_COLOR = {'PASS': GREEN, 'FAIL': RED, 'XFAIL': YELLOW, 'XPASS': RED}


def report(title, checks, use_color=True):
    def c(s, col):
        return (col + s + RESET) if use_color else s
    print('\n%s' % c(title, '\033[1m' if use_color else ''))
    for chk in checks:
        st = chk.status
        print('  %s %-22s %s' % (c('%-5s' % st, _COLOR[st]), chk.name,
                                 c(chk.detail, GREY)))
    failed = [k for k in checks if k.counts_as_failure]
    return failed
