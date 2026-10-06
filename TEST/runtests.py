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
    ap.add_argument('--s2', action='store_true',
                    help='the S2ED (MSX1 / SCREEN 2) Gate only')
    ap.add_argument('--s62', action='store_true',
                    help='the S62ED (MSX2 / SCREEN 6, 62 columns) Gate only')
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

    picked = args.static or args.gate or args.selftest or args.s2 or args.s62
    run_static = args.all or args.static or not picked
    run_gate = args.all or args.gate or not picked
    run_s2 = args.all or args.s2 or not picked
    run_s62 = args.all or args.s62 or not picked
    run_selftest = args.all or args.selftest
    color = not args.no_color and sys.stdout.isatty()

    # out/ always holds the last run of every case: its disk, generated .tcl,
    # openMSX log and every dump.  That is where a failure gets diagnosed.
    ctx = Context(os.path.dirname(os.path.abspath(__file__)), args.out,
                  load_symbols=False)
    all_checks = []
    gate_checks = []
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
        gate_checks = checks
        all_checks += checks
        failed += result.report('T1/T2  GATE', checks, color)

    if run_s2:
        # The S2 target shares CORE with S6ED and nothing else: a separate
        # context, because the prefix, the include path, the .sym and the
        # machine all differ.
        import gate_s2
        s2ctx = ctx.for_target('S2ED')
        build = static.check_build_clean(s2ctx)
        build = result.Check('build-clean-s2', build.ok, build.detail)
        s2checks = [build]
        if build.ok:
            s2ctx.reload_symbols()
            s2cases = [c for c in gate_s2.CASES
                       if args.filter.upper() in c.name.upper()]
            s2checks += gate_s2.run(s2ctx, s2cases) if s2cases else []
        all_checks += s2checks
        failed += result.report('S2  GATE  (MSX1 / SCREEN 2)', s2checks, color)

    if run_s62:
        # Third target: Screen 6 like S6ED, but 8x8 byte-aligned cells, its
        # own driver (S62/) and its own .sym -- a separate context again.
        import gate_s62
        s62ctx = ctx.for_target('S62ED')
        build = static.check_build_clean(s62ctx)
        build = result.Check('build-clean-s62', build.ok, build.detail)
        s62checks = [build]
        if build.ok:
            s62ctx.reload_symbols()
            s62cases = [c for c in gate_s62.CASES
                        if args.filter.upper() in c.name.upper()]
            s62checks += gate_s62.run(s62ctx, s62cases) if s62cases else []
        all_checks += s62checks
        failed += result.report('S62  GATE  (MSX2 / SCREEN 6, 62 COLUMNS)',
                                s62checks, color)

    if run_selftest:
        import selftest
        # The Gate has just run on the clean build: reuse its verdicts as the
        # baseline instead of paying for the same sessions twice.
        baseline = {c.name: not c.counts_as_failure
                    for c in gate_checks} if run_gate else None
        checks = selftest.run(ctx, args.filter, baseline)
        all_checks += checks
        failed += result.report('SELFTEST  MUTATIONS', checks, color)

    print('\n%d checks, %d failed, %.1fs'
          % (len(all_checks), len(failed), time.time() - t0))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
