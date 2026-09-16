#!/usr/bin/env python3
"""S6ED regression suite.

    ./runtests.py            # T0 static + the Gate
    ./runtests.py --all      # the lot: T0 + Gate + mutation self-test
    ./runtests.py --static   # T0 only, no emulator (wired into `make build`)
    ./runtests.py --gate     # the Gate only
    ./runtests.py --selftest # the mutation self-test only
    ./runtests.py -k G4      # one case, or any name substring (also filters
                             # the mutations, by name or by the cases they hit)

Nothing short-circuits: every section that was asked for runs and every check
is printed, pass or fail, so one run shows the whole picture.  The single
exception is a build that does not assemble, which leaves nothing to test.

Exit code is 0 only when every check passes.  See README.md for what each case
protects and which historical defect it was derived from.
"""

import argparse
import os
import sys
import time

import result
import static
from context import Context


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument('--static', action='store_true', help='T0 checks only')
    ap.add_argument('--gate', action='store_true', help='runtime Gate only')
    ap.add_argument('-k', '--filter', default='',
                    help='run only cases whose name contains this')
    ap.add_argument('--out', default=None, help='output directory')
    ap.add_argument('--no-color', action='store_true')
    ap.add_argument('--selftest', action='store_true',
                    help='put each historical defect back and prove the Gate '
                         'still goes red')
    ap.add_argument('--all', action='store_true',
                    help='everything: T0 static, the Gate and the self-test')
    args = ap.parse_args()

    picked = args.static or args.gate or args.selftest
    run_static = args.all or args.static or not picked
    run_gate = args.all or args.gate or not picked
    run_selftest = args.all or args.selftest
    color = not args.no_color and sys.stdout.isatty()

    # out/ always holds the last run of every case: its disk, generated .tcl,
    # openMSX log and every dump.  That is where a failure gets diagnosed.
    ctx = Context(os.path.dirname(os.path.abspath(__file__)), args.out,
                  load_symbols=False)
    all_checks = []
    failed = []
    t0 = time.time()

    if run_static:
        checks = static.run(ctx)
        all_checks += checks
        failed += result.report('T0  STATIC', checks, color)
        if any(c.name == 'build-clean' and not c.ok for c in checks):
            print('\nbuild failed -- stopping before the emulator runs')
            return 1
    else:
        ctx.reload_symbols()

    if run_gate:
        import gate
        if ctx.sym is None:
            ctx.reload_symbols()
        cases = [c for c in gate.CASES if args.filter.upper() in c.name.upper()]
        if not cases and not run_selftest:
            print('no case matches %r' % args.filter)
            return 2
        checks = gate.run(ctx, cases) if cases else []
        all_checks += checks
        failed += result.report('T1/T2  GATE', checks, color)

    if run_selftest:
        import selftest
        # The Gate has just run on the clean build: reuse its verdicts as the
        # baseline instead of paying for the same sessions twice.
        baseline = {c.name: not c.counts_as_failure
                    for c in checks} if run_gate else None
        checks = selftest.run(ctx, args.filter, baseline)
        all_checks += checks
        failed += result.report('SELFTEST  MUTATIONS', checks, color)

    print('\n%d checks, %d failed, %.1fs'
          % (len(all_checks), len(failed), time.time() - t0))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
