"""S6ED test harness -- T0: static checks, no emulator.

These run in well under a second and are wired into `make build`, because the
invariants they protect are the ones that cost whole sessions when they break:
where the image ends, where mutable state lives, and whether a record layout is
still the contract the code assumes.
"""

import hashlib
import os
import re
import subprocess

from result import Check

DATA_RE = re.compile(r'^([A-Z][A-Z0-9_]*)\s+(DEFB|DEFW|DEFS|DEFM)\b')
LABEL_RE = re.compile(r'^([A-Za-z][A-Za-z0-9_]*)')
LOCAL_RE = re.compile(r'^(\.[A-Za-z0-9_]+)')
# A hex literal in the forbidden forms.  Comments are stripped before matching.
BADHEX_RE = re.compile(r'(?<![\w#$%])(0x[0-9A-Fa-f]+|[0-9][0-9A-Fa-f]*[Hh])(?![\w])')
DEFB_RE = re.compile(r'\bDEFB\s+(.*)$')


def _src_files(src_dir):
    return sorted(f for f in os.listdir(src_dir) if f.endswith('.Z8A'))


def _strip_comment(line):
    out = []
    in_str = False
    for ch in line:
        if ch == '"':
            in_str = not in_str
        if ch == ';' and not in_str:
            break
        out.append(ch)
    return ''.join(out)


# --- CHECKS ------------------------------------------------------------


def check_image_end(ctx):
    """OUTEND must land exactly at the end of the emitted file.

    Everything below OUTEND only reserves TPA addresses and is never written to
    the .COM, so it boots holding whatever the previous program left behind.
    VARS is the first symbol after OUTEND: if it is not at #0100 + filesize,
    either something is emitted after it (and the variables have moved) or
    something below it is not being emitted at all.
    """
    size = os.path.getsize(os.path.join(ctx.code_dir, 'S6ED.COM'))
    want = 0x100 + size
    got = ctx.sym['VARS']
    return Check('image-end',
                 got == want,
                 'VARS #%04X, #0100 + %d bytes = #%04X' % (got, size, want))


def check_vars_block(ctx):
    """Every variable lives inside the block INIT clears, and only there."""
    lo, hi = ctx.sym['VARS'], ctx.sym['ENDVARS']
    bad = []
    for name, addr in ctx.sym.labels_of('VARS.Z8A').items():
        if name == 'ENDVARS':
            continue                        # the exclusive bound, not a variable
        if not (lo <= addr < hi):
            bad.append('%s #%04X outside [#%04X,#%04X)' % (name, addr, lo, hi))
    for name, addr in ctx.sym.globals().items():
        if ctx.sym.is_const.get(name, False):
            continue                        # a constant's VALUE may be anything
        if lo <= addr < hi and ctx.sym.owner.get(name) not in (None, 'VARS.Z8A'):
            bad.append('%s #%04X declared in %s' % (name, addr,
                                                    ctx.sym.owner[name]))
    return Check('vars-block', not bad,
                 '; '.join(bad) if bad else
                 '%d variables inside [#%04X,#%04X)'
                 % (len(ctx.sym.labels_of('VARS.Z8A')), lo, hi))


def check_init_clear(ctx):
    """INIT must zero the whole variable block, VARS..ENDVARS-1."""
    text = open(os.path.join(ctx.src_dir, 'S6ED.Z8A')).read()
    want = [r'LD\s+HL,\s*VARS\b', r'LD\s+DE,\s*VARS\s*\+\s*1\b',
            r'LD\s+BC,\s*ENDVARS\s*-\s*VARS\s*-\s*1\b',
            r'LD\s+\(HL\),\s*0\b', r'\bLDIR\b']
    missing = [w for w in want if not re.search(w, text)]
    return Check('init-clear', not missing,
                 'missing: %s' % missing if missing else
                 'INIT clears VARS..ENDVARS-1')


def check_layout_asserts(ctx):
    """Record layouts addressed by IX+n or copied by LDIR are contracts.

    The selection defect of 2026-09-15 was exactly this: the painted range was
    declared as a lone DEFW, so its last four bytes were somebody else's
    scratch and SELDIFF corrupted the range while reading it.  Four bytes of
    RAM, no code change -- and the build must never let it happen silently
    again.
    """
    text = open(os.path.join(ctx.src_dir, 'VARS.Z8A')).read()
    want = ['SELSTRX == SELSTRL + 2', 'SELENDL == SELSTRL + 3',
            'SELENDX == SELSTRL + 5', 'DRWSTRX == DRWSTRL + 2',
            'DRWENDL == DRWSTRL + 3', 'DRWENDX == DRWSTRL + 5']
    missing = [w for w in want
               if not re.search(r'ASSERT\s+' +
                                r'\s*'.join(re.escape(t) for t in w.split()),
                                text)]
    return Check('layout-asserts', not missing,
                 'missing: %s' % missing if missing else
                 '%d record-layout ASSERTs enforced by the build' % len(want))


# Records that code addresses as a block -- by IX + n, or copied with LDIR.
# Nothing else may live inside one.
# base, size, and the fields that legitimately make it up.
RECORDS = [
    ('SELSTRL', 6, ('SELSTRX', 'SELENDL', 'SELENDX')),
    ('DRWSTRL', 6, ('DRWSTRX', 'DRWENDL', 'DRWENDX')),
    ('CLKBUF', 6, ()),
    ('SEGTBL', 32, ()),
]


def check_record_exclusive(ctx):
    """No variable may live inside a record that is addressed as a block.

    This is the check the ASSERTs cannot make.  DRWSTRL used to be a lone DEFW
    whose last four bytes happened to be SELTMPL / SELTMPXA / SELTMPXB -- and
    the offset ASSERTs were satisfied by that layout too, because the offsets
    were right; what was wrong was that the storage belonged to someone else.
    """
    labels = ctx.sym.labels_of('VARS.Z8A')
    bad = []
    for rec, size, fields in RECORDS:
        if rec not in ctx.sym.addr:
            continue
        base = ctx.sym[rec]
        for name, addr in labels.items():
            if name in (rec,) + fields:
                continue
            if base < addr < base + size:
                bad.append('%s (#%04X) lies inside %s[%d]'
                           % (name, addr, rec, size))
    return Check('record-exclusive', not bad, '; '.join(bad) if bad else
                 '%d block records own every byte they span' % len(RECORDS))


def check_data_placement(ctx):
    """Mutable state belongs in VARS.Z8A; anything else needs classifying.

    Data defined outside VARS.Z8A is emitted into the .COM, which is right for
    read-only tables and wrong for state.  The baseline lists the ones already
    reviewed; a new name fails the gate until it is added deliberately.
    """
    base_path = os.path.join(ctx.test_dir, 'data_baseline.txt')
    baseline = set()
    if os.path.exists(base_path):
        baseline = {l.split('#')[0].strip() for l in open(base_path)
                    if l.split('#')[0].strip()}
    found = set()
    for fname in _src_files(ctx.src_dir):
        if fname == 'VARS.Z8A':
            continue
        for line in open(os.path.join(ctx.src_dir, fname), errors='replace'):
            m = DATA_RE.match(line)
            if m:
                found.add(m.group(1))
    new = sorted(found - baseline)
    return Check('data-placement', not new,
                 'unclassified data outside VARS.Z8A: %s' % new if new else
                 '%d reviewed tables, 0 new' % len(found))


def check_label_style(ctx):
    """Labels <= 8 chars (the dot of a local counts), no underscores."""
    bad = []
    for fname in _src_files(ctx.src_dir):
        for n, line in enumerate(open(os.path.join(ctx.src_dir, fname),
                                      errors='replace'), 1):
            m = LABEL_RE.match(line) or LOCAL_RE.match(line)
            if not m:
                continue
            name = m.group(1)
            if re.match(r'^[A-Za-z][A-Za-z0-9_]*\s+EQU\b', line):
                continue                    # constants may use underscores
            if len(name) > 8:
                bad.append('%s:%d %s (%d chars)' % (fname, n, name, len(name)))
            elif '_' in name:
                bad.append('%s:%d %s (underscore)' % (fname, n, name))
    return Check('label-style', not bad, '; '.join(bad) if bad else
                 'all labels <= 8 chars, no underscores')


def check_number_notation(ctx):
    """Hex is #XX and binary is %XXXX. Never 0x.. and never ..H."""
    bad = []
    for fname in _src_files(ctx.src_dir):
        for n, line in enumerate(open(os.path.join(ctx.src_dir, fname),
                                      errors='replace'), 1):
            code = _strip_comment(line)
            m = BADHEX_RE.search(code)
            if m:
                bad.append('%s:%d %s' % (fname, n, m.group(1)))
    return Check('number-notation', not bad, '; '.join(bad[:8]) if bad else
                 'no 0x / XXh literals')


def check_defb_width(ctx):
    """At most 8 values per DEFB line, split on 8-byte boundaries."""
    bad = []
    for fname in _src_files(ctx.src_dir):
        for n, line in enumerate(open(os.path.join(ctx.src_dir, fname),
                                      errors='replace'), 1):
            code = _strip_comment(line)
            m = DEFB_RE.search(code)
            if not m or '"' in m.group(1):
                continue
            if len(m.group(1).split(',')) > 8:
                bad.append('%s:%d' % (fname, n))
    return Check('defb-width', not bad, '; '.join(bad) if bad else
                 'no DEFB line over 8 values')


def check_page1_hooks(ctx):
    """No interrupt hook may point into page 1.

    Learned twice.  The Disk ROM banks itself over #4000-#7FFF whenever disk
    code runs and the VBLANK can fire exactly then, so a hook into our own
    image lands in FDC ROM and the stack runs away.  Measured: 3 of 2,174
    H.TIMI calls fired with page 1 not ours, on a fully idle editor.
    """
    bad = []
    for fname in _src_files(ctx.src_dir):
        for n, line in enumerate(open(os.path.join(ctx.src_dir, fname),
                                      errors='replace'), 1):
            code = _strip_comment(line).upper()
            if re.search(r'LD\s+\(\s*(#FD9F|HTIMI|#FD9A|HKEYI)\s*\)', code):
                bad.append('%s:%d writes an interrupt hook' % (fname, n))
    return Check('page1-hooks', not bad, '; '.join(bad) if bad else
                 'no code installs an H.TIMI / H.KEYI hook')


def check_assets(ctx):
    """The font ships as a file; its size is the contract FONTINIT checks."""
    res = os.path.join(ctx.project_dir, 'RES', 'FONTS.BIN')
    fnt = os.path.join(ctx.code_dir, 'S6ED.FNT')
    if not (os.path.exists(res) and os.path.exists(fnt)):
        return Check('assets', False, 'FONTS.BIN or S6ED.FNT missing')
    size = os.path.getsize(res)
    same = (hashlib.md5(open(res, 'rb').read()).digest() ==
            hashlib.md5(open(fnt, 'rb').read()).digest())
    ok = size == 8192 and same
    return Check('assets', ok,
                 'FONTS.BIN %d bytes, S6ED.FNT %s' %
                 (size, 'identical' if same else 'DIFFERENT'))


def check_build_clean(ctx):
    """The build itself: 0 errors, 0 warnings, every ASSERT satisfied."""
    # -B: force the assembly even when nothing changed, so every ASSERT in
    # the sources is actually evaluated on every run.
    r = subprocess.run(['make', '-B', 'build'], cwd=ctx.code_dir,
                       capture_output=True, text=True)
    tail = (r.stdout + r.stderr).strip().splitlines()
    summary = next((l for l in tail if l.startswith('Errors:')), '')
    ok = r.returncode == 0 and 'Errors: 0, warnings: 0' in summary
    return Check('build-clean', ok, summary or (r.stderr.strip()[:200]))


ALL = [check_build_clean, check_image_end, check_vars_block, check_init_clear,
       check_layout_asserts, check_record_exclusive, check_data_placement,
       check_label_style,
       check_number_notation, check_defb_width, check_page1_hooks,
       check_assets]


def run(ctx):
    """Build first, then parse the .sym the build just produced."""
    checks = [check_build_clean(ctx)]
    if not checks[0].ok:
        return checks
    ctx.reload_symbols()
    return checks + [fn(ctx) for fn in ALL if fn is not check_build_clean]
