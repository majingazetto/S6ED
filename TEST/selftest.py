"""Run the mutation self-test: one build and one session per defect.

A mutation only proves something if the checks it is supposed to redden were
GREEN to begin with.  `D8/content` was red for a while and `mut/d8-accents`
passed through it without noticing, which is exactly the hole this closes: the
baseline verdict for every expected check is established on the clean build
first, and a mutation whose checks were already failing is reported as a
failure of the self-test, not as a catch.
"""

import gate
import mutations
import static
from result import Check


def run(ctx, name_filter='', baseline=None):
    """`baseline` is {check name: ok} measured on the clean build.

    The caller passes the Gate it has just run so the same sessions are not
    paid for twice; anything missing from it is measured here.
    """
    muts = [m for m in mutations.MUTATIONS if _matches(m, name_filter)]
    if not muts:
        return [Check('selftest', False, 'no mutation matches %r' % name_filter)]

    base = dict(baseline or {})
    unmeasured = [m for m in muts if not _expected(m) <= set(base)]
    if unmeasured:
        base.update(_baseline(ctx, unmeasured))

    checks = []
    for mut in muts:
        stale = _stale(mut, base)
        if stale:
            checks.append(Check('mut/%s' % mut['name'], False,
                                'BASELINE NOT GREEN: %s -- a mutation caught '
                                'by an already failing check proves nothing'
                                % ', '.join(stale)))
            continue
        try:
            with mutations.Applied(ctx, mut):
                checks.append(_one(ctx, mut))
        except Exception as exc:                          # noqa: BLE001
            checks.append(Check('mut/%s' % mut['name'], False,
                                'could not apply: %s' % exc))
    # The sources are back: rebuild so the tree is left exactly as found.
    static.check_build_clean(ctx)
    ctx.reload_symbols()
    return checks


def _matches(mut, name_filter):
    if not name_filter:
        return True
    needle = name_filter.upper()
    return needle in mut['name'].upper() or needle in mut['filter'].upper()


def _expected(mut):
    return (set(mut.get('expect', [])) | set(mut.get('expect_static', []))
            | set(mut.get('expect_any', [])))


def _stale(mut, base):
    """Expected checks that are not green on the clean build."""
    out = [n for n in sorted(set(mut.get('expect', []))
                             | set(mut.get('expect_static', [])))
           if not base.get(n, False)]
    any_of = set(mut.get('expect_any', []))
    if any_of and not any(base.get(n, False) for n in any_of):
        out.append('none of %s' % ', '.join(sorted(any_of)[:3] + ['...']))
    return out


def _baseline(ctx, muts):
    """Verdicts on the CLEAN build for everything these mutations expect."""
    build = static.check_build_clean(ctx)
    if not build.ok:
        return {}
    ctx.reload_symbols()
    return _verdicts(ctx, muts)


def _verdicts(ctx, muts):
    out = {}
    for fn in static.ALL:
        if fn is static.check_build_clean:
            continue
        chk = fn(ctx)
        out[chk.name] = not chk.counts_as_failure
    filters = {m['filter'].upper() for m in muts}
    cases = [c for c in gate.CASES
             if any(f in c.name.upper() for f in filters)]
    for chk in gate.run(ctx, cases):
        out[chk.name] = not chk.counts_as_failure
    return out


def _one(ctx, mut):
    build = static.check_build_clean(ctx)
    if not build.ok:
        return Check('mut/%s' % mut['name'], False,
                     'mutated source does not assemble: %s' % build.detail)
    ctx.reload_symbols()

    red = {n for n, ok in _verdicts(ctx, [mut]).items() if not ok}
    want = set(mut.get('expect', [])) | set(mut.get('expect_static', []))
    any_of = set(mut.get('expect_any', []))
    missed = sorted(want - red)
    if any_of and not (any_of & red):
        missed.append('none of %s' % ', '.join(sorted(any_of)[:3] + ['...']))
    caught = sorted((red & want) | (red & any_of))
    return Check('mut/%s' % mut['name'], not missed,
                 'caught by %s' % ', '.join(caught) if not missed
                 else 'NOT CAUGHT: %s stayed green' % ', '.join(missed))
