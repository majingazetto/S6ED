"""Run the mutation self-test: one build and one session per defect."""

import gate
import mutations
import static
from result import Check


def run(ctx):
    checks = []
    for mut in mutations.MUTATIONS:
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


def _one(ctx, mut):
    build = static.check_build_clean(ctx)
    if not build.ok:
        return Check('mut/%s' % mut['name'], False,
                     'mutated source does not assemble: %s' % build.detail)
    ctx.reload_symbols()

    red = set()
    for fn in static.ALL:
        if fn is static.check_build_clean:
            continue
        chk = fn(ctx)
        if not chk.ok:
            red.add(chk.name)
    cases = [c for c in gate.CASES if mut['filter'].upper() in c.name.upper()]
    for chk in gate.run(ctx, cases):
        if not chk.ok:
            red.add(chk.name)

    want = set(mut.get('expect', [])) | set(mut.get('expect_static', []))
    any_of = set(mut.get('expect_any', []))
    missed = sorted(want - red)
    if any_of and not (any_of & red):
        missed.append('none of %s' % ', '.join(sorted(any_of)[:3] + ['...']))
    caught = sorted((red & want) | (red & any_of))
    return Check('mut/%s' % mut['name'], not missed,
                 'caught by %s' % ', '.join(caught) if not missed
                 else 'NOT CAUGHT: %s stayed green' % ', '.join(missed))
