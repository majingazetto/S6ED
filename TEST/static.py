"""S6ED test harness -- T0: static checks, no emulator.

These run in well under a second and are wired into `make build`, because the
invariants they protect are the ones that cost whole sessions when they break:
where the image ends, where mutable state lives, and whether a record layout is
still the contract the code assumes.
"""

import hashlib
import os
import re
import struct
import subprocess

import symbols
from context import TARGETS
from result import Check

DATA_RE = re.compile(r'^([A-Z][A-Z0-9_]*)\s+(DEFB|DEFW|DEFS|DEFM)\b')
LABEL_RE = re.compile(r'^([A-Za-z][A-Za-z0-9_]*)')
LOCAL_RE = re.compile(r'^(\.[A-Za-z0-9_]+)')
# A hex literal in the forbidden forms.  Comments are stripped before matching.
BADHEX_RE = re.compile(r'(?<![\w#$%])(0x[0-9A-Fa-f]+|[0-9][0-9A-Fa-f]*[Hh])(?![\w])')
DEFB_RE = re.compile(r'\bDEFB\s+(.*)$')


def _src_files(src_dir):
    res = []
    for root, _, files in os.walk(src_dir):
        for f in files:
            if f.endswith('.Z8A'):
                res.append(os.path.relpath(os.path.join(root, f), src_dir))
    return sorted(res)


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
    text = open(ctx.find_src_file('S6ED.Z8A')).read()
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
    text = open(ctx.find_src_file('VARS.Z8A')).read()
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


# Buffers whose layout is 1 length byte + TEXTCOLS text + TEXTCOLS attributes.
# An offset into one of them is a target parameter, never a number.
LAYOUT_BUFS = ('WORKBUF', 'WORKBUF2', 'PREVBUF')
LAYOUT_OFF_RE = re.compile(
    r'\b(%s)\s*\+\s*(\d+)' % '|'.join(LAYOUT_BUFS))
# Immediates that are S6ED's geometry spelled out: the line width and the
# column and row indices derived from it.  In CORE they are always wrong.
GEOM_IMM_RE = re.compile(
    r'\b(?:CP|SUB|LD\s+(?:A|B|C|D|E|H|L|BC|DE|HL)\s*,)\s*'
    r'(23|24|63|64|65|79|80|81|128|129|159|160|161)\b')


def check_target_params(ctx):
    """Shared CORE code may not spell out a target's geometry as a number.

    This has now cost three rounds.  FILELOAD carried 80 / 81 / 79 and gave
    S2ED garbage attributes down the left of every line; EDDELBK and EDDELCHR
    carried `CP 79` and `WORKBUF + 80` and dragged an attribute byte into the
    last text column, after which EDINSCHR refuses every keystroke on that
    line because the record looks full; EDNWLIN carried `LD B, 23` and
    repainted the split head over the status bar.  Every one of them is
    invisible in a single-target tree and silent in a second one.

    Offsets into a line record derive from TEXTCOLS, viewport bounds from
    ROWSVIS.  Only the length byte (+0) and the first text column (+1, +2)
    may be written as numbers.
    """
    bad = []
    core = os.path.join(ctx.src_dir, 'CORE')
    for fname in sorted(os.listdir(core)):
        if not fname.endswith('.Z8A'):
            continue
        for n, line in enumerate(open(os.path.join(core, fname),
                                      errors='replace'), 1):
            code = _strip_comment(line)
            for m in LAYOUT_OFF_RE.finditer(code):
                if int(m.group(2)) > 2:
                    bad.append('CORE/%s:%d %s + %s'
                               % (fname, n, m.group(1), m.group(2)))
            m = GEOM_IMM_RE.search(code)
            if m:
                bad.append('CORE/%s:%d immediate %s'
                           % (fname, n, m.group(1)))
    return Check('target-params', not bad, '; '.join(bad[:8]) if bad else
                 'CORE derives every record offset from TEXTCOLS and every '
                 'viewport bound from ROWSVIS')


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
        if os.path.basename(fname) == 'VARS.Z8A':
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


def check_feature_discipline(ctx):
    """Feature passengers in FTRBLOB must obey mapper rules and size limits.

    Features in Page 2 must not call raw mapper manipulation routines
    (PUTP2, RECBANK, DIRBANK, GETP2, SEGGET, FRESEG).
    The feature blob must fit inside a single 16 KB mapper segment.
    """
    forbidden = {'PUTP2', 'RECBANK', 'DIRBANK', 'GETP2', 'SEGGET', 'FRESEG'}
    feature_files = ['CFG.Z8A', 'WINDOW.Z8A']
    bad = []
    for fname in feature_files:
        path = ctx.find_src_file(fname)
        if not os.path.exists(path):
            continue
        for n, line in enumerate(open(path, errors='replace'), 1):
            code = line.split(';')[0]
            for word in forbidden:
                if re.search(r'\b%s\b' % word, code):
                    bad.append('%s:%d calls forbidden mapper routine %s' % (fname, n, word))

    cfgload = ctx.sym.addr.get('CFGLOAD')
    if cfgload != 0x8000:
        bad.append('CFGLOAD at #%04X, expected #8000' % (cfgload or 0))
    ftrlen = ctx.sym.addr.get('FTRBLEN')
    if ftrlen is None or ftrlen > 16384:
        bad.append('FTRBLEN %s, expected <= 16384' % ftrlen)

    datpath = os.path.join(ctx.code_dir, 'S6ED.DAT')
    if not os.path.exists(datpath):
        bad.append('S6ED.DAT container file missing')
    else:
        dat = open(datpath, 'rb').read()
        if len(dat) < 24:
            bad.append('S6ED.DAT too small (%d bytes < 24)' % len(dat))
        else:
            if dat[0:4] != b'S6ED':
                bad.append('S6ED.DAT bad magic: %r' % dat[0:4])
            ver = struct.unpack_from('<H', dat, 4)[0]
            if ver != 1:
                bad.append('S6ED.DAT bad version: %d' % ver)
            if dat[6] != 0x1A:
                bad.append('S6ED.DAT missing EOF marker: #%02X' % dat[6])
            nblks = dat[7]
            if nblks < 1:
                bad.append('S6ED.DAT block count: %d' % nblks)
            tbloff = struct.unpack_from('<H', dat, 8)[0]
            if tbloff != 16:
                bad.append('S6ED.DAT table offset: %d' % tbloff)
            # Block descriptor 0
            blkid = dat[16]
            flags = dat[17]
            loadaddr = struct.unpack_from('<H', dat, 18)[0]
            blklen = struct.unpack_from('<H', dat, 20)[0]
            dataoff = struct.unpack_from('<H', dat, 22)[0]
            if blkid != 1 or loadaddr != 0x8000 or dataoff != 24:
                bad.append('S6ED.DAT block 0 mismatch: id=%d addr=#%04X off=%d' % (blkid, loadaddr, dataoff))
            if blklen != ftrlen:
                bad.append('S6ED.DAT block 0 len %d != FTRBLEN %d' % (blklen, ftrlen or 0))
            if len(dat) != dataoff + blklen:
                bad.append('S6ED.DAT file size %d != off %d + len %d' % (len(dat), dataoff, blklen))

    return Check('feature-discipline', not bad, '; '.join(bad) if bad else
                 'S6ED.DAT (%dB) FTRBLEN %d <= 16384, CFGLOAD phased at #8000, mapper discipline clean'
                 % (len(dat) if 'dat' in locals() else 0, ftrlen or 0))


def check_build_clean(ctx):
    """The build itself: 0 errors, 0 warnings, every ASSERT satisfied."""
    # -B: force the assembly even when nothing changed, so every ASSERT in
    # the sources is actually evaluated on every run.
    # Per-target names, never the umbrella `build`: it assembles both and
    # the summary parsed below is whichever ran first.
    target = 'build-s6' if ctx.prefix == 'S6ED' else 'build-s2'
    r = subprocess.run(['make', '-B', target], cwd=ctx.code_dir,
                       capture_output=True, text=True)
    tail = (r.stdout + r.stderr).strip().splitlines()
    summary = next((l for l in tail if l.startswith('Errors:')), '')
    ok = r.returncode == 0 and 'Errors: 0, warnings: 0' in summary
    return Check('build-clean', ok, summary or (r.stderr.strip()[:200]))


def check_window_discipline(ctx):
    """Window engine implementation rules and invariants (Fases C2 y C3).

    WINOPEN must round WINW up capturing carry before masking.
    Geometry bounds (504, 508, 207, 208 — C3 reserves the 4-px shadow)
    must be clamped in WINOPEN.
    WINKIL must be called in WINOPEN.
    WINACTV must be managed in WINOPEN and WINCLOS.
    WINSTR must not clobber IXH/IXL, must skip spaces and honor WINCLIPX.
    WINSHOW/WINRST must sync to VBLANK via WINVSY (C3).
    The frame must be painted as HMMV bands (WINBAND) with a WINSHDW shadow.
    .STRVER must compose version dynamically from VERSION.MAJOR and VERSION.MINOR.
    """
    path = ctx.find_src_file('WINDOW.Z8A')
    if not os.path.exists(path):
        return Check('window-discipline', False, 'WINDOW.Z8A missing')
    src = open(path).read()
    bad = []

    # Check carry ordering in WINOPEN
    m = re.search(r'ADD\s+A,\s*3[\s\S]*?JR\s+NC,\s*\.NOWINC[\s\S]*?AND\s+%11111100', src)
    if not m:
        bad.append('WINOPEN WINW rounding does not preserve carry before AND')

    # Check bounds (C3: shadow margin reserved — 504/508 horizontal, 207/208 vertical)
    for bound in (r'DE,\s*504\b', r'HL,\s*508\b', r'DE,\s*207\b', r'HL,\s*208\b'):
        if not re.search(bound, src):
            bad.append('WINOPEN missing geometry clamp %s' % bound)

    if 'CALL    WINKIL' not in src:
        bad.append('WINOPEN does not call WINKIL to flush keyboard buffer')

    if 'VERSION.MAJOR' not in src or 'VERSION.MINOR' not in src:
        bad.append('.STRVER does not reference VERSION.MAJOR and VERSION.MINOR')

    if 'IXH' in src or 'IXL' in src:
        bad.append('WINDOW.Z8A uses IXH/IXL (forbidden: preserves IX for selection)')

    # C3: VBLANK sync on the two visible full blits
    if not re.search(r'WINSHOW\s+CALL\s+WINVSY', src):
        bad.append('WINSHOW does not sync to VBLANK via WINVSY')
    if not re.search(r'WINRST\s+CALL\s+WINVSY', src):
        bad.append('WINRST does not sync to VBLANK via WINVSY')

    # C3: band-decomposed frame with shadow
    if 'CALL    WINBAND' not in src:
        bad.append('WINBOX is not band-decomposed (no WINBAND calls)')
    if 'WINSHDW' not in src:
        bad.append('WINBOX/WINSAV do not paint/save the WINSHDW shadow margin')

    # C3: space skip and clipping in WINSTR
    if "CP      ' '" not in src:
        bad.append('WINSTR does not skip spaces (all-zero glyph, TIMP/TOR no-op)')
    if 'WINCLIPX' not in src:
        bad.append('WINSTR/WINOPEN do not implement the WINCLIPX text clip')

    # C3: partial re-blit primitive and its use in the Quit dialog nav
    if not re.search(r'WINUPD\s+PUSH\s+AF', src):
        bad.append('WINUPD partial re-blit primitive missing')
    if 'CALL    WINUPD' not in src:
        bad.append('DOQIT navigation does not re-blit via WINUPD')

    return Check('window-discipline', not bad,
                 '; '.join(bad) if bad else
                 'window engine invariants clean (carry, clamps, WINKIL, dynamic version, '
                 'IX-clean, vsync, bands, shadow, clip, WINUPD)')


def check_ftr_budget(ctx):
    """Every FCALL into FTRBASE must acknowledge BOTH targets' budgets.

    The window/menu system leaves the two FTRBASE containers in radically
    different states -- S6ED with ~9,600 B free, S2ED with ~200 B once the
    menus land (DEV/SPEC_S2ED_FTRBASE_GUARD.md).  A shared passenger that
    fits on one target can silently overflow the other.  Three layers form
    the net: the FTR-BUDGET comment required at every FCALL site in CORE,
    the ASSERT FTRFREE >= 128 in both root sources, and the FTRFREE value
    itself, read back from each .sym file when one exists.
    """
    bad = []
    core = os.path.join(ctx.src_dir, 'CORE')
    for fname in sorted(os.listdir(core)):
        if not fname.endswith('.Z8A'):
            continue
        lines = open(os.path.join(core, fname),
                     errors='replace').read().splitlines()
        for n, line in enumerate(lines):
            code = _strip_comment(line)
            if not re.search(r'\b(?:CALL|JP)\s+FCALL\b', code):
                continue
            near = lines[max(0, n - 5):n + 6]
            if not any('FTR-BUDGET' in l for l in near):
                bad.append('CORE/%s:%d FCALL without FTR-BUDGET comment'
                           % (fname, n + 1))
    for root in ('S6ED.Z8A', 'S2ED.Z8A'):
        text = open(os.path.join(ctx.src_dir, root),
                    errors='replace').read()
        if not re.search(r'^FTRFREE\s+EQU\b', text, re.M):
            bad.append('%s does not define FTRFREE' % root)
        if not re.search(r'\bASSERT\s+FTRFREE\s*>=\s*128\b', text):
            bad.append('%s does not ASSERT FTRFREE >= 128' % root)
    for prefix in ('S6ED', 'S2ED'):
        symfile = os.path.join(ctx.code_dir, prefix + '.sym')
        if not os.path.exists(symfile):
            continue
        sym = symbols.load(ctx.code_dir, prefix, TARGETS[prefix])
        free = sym.get('FTRFREE')
        if free is None:
            bad.append('%s.sym has no FTRFREE' % prefix)
        elif free < 128:
            bad.append('%s FTRFREE = %d (< 128)' % (prefix, free))
    return Check('ftr-budget', not bad,
                 '; '.join(bad) if bad else
                 'every FCALL documented, FTRFREE >= 128 asserted on both '
                 'targets')


def check_tpa_chain(ctx):
    """TPA buffers chain off each other; none of them names an address.

    The feature container taught this the hard way: target-specific code at a
    fixed address looks like free space to the target that does not declare
    it.  The TPA block at the foot of VARS.Z8A is additive by construction --
    each buffer starts where the previous one ends -- and this check keeps it
    that way, because one literal address in there reintroduces exactly the
    same failure, silently, on whichever target does not declare the buffer.

    It does NOT prove two buffers cannot overlap; that is a runtime property
    and S2-12 is the case that measures it.
    """
    bad = []
    path = ctx.find_src_file('VARS.Z8A')
    lines = open(path, errors='replace').read().splitlines()
    tail = None
    for n, line in enumerate(lines):
        if line.strip() == 'ENDVARS':
            tail = lines[n + 1:]
            break
    if tail is None:
        return Check('tpa-chain', False, 'VARS.Z8A has no ENDVARS')
    defined = {'ENDVARS'}
    for n, line in enumerate(tail):
        code = _strip_comment(line)
        m = re.match(r'^([A-Z][A-Z0-9]*)\s+EQU\s+(.+?)\s*$', code)
        if not m:
            continue
        name, expr = m.group(1), m.group(2)
        # A bare address -- the thing this check exists to forbid.
        if re.search(r'(?<![\w#])#[0-9A-Fa-f]{3,4}\b', expr) or \
                re.fullmatch(r'\d{3,}', expr.strip()):
            bad.append('VARS.Z8A: %s = %s names an address; chain it off the '
                       'previous allocation instead' % (name, expr))
        elif not any(re.search(r'\b%s\b' % re.escape(d), expr)
                     for d in defined):
            bad.append('VARS.Z8A: %s = %s does not build on the chain'
                       % (name, expr))
        defined.add(name)
    for want in ('UNDOBAS', 'TPATOP', 'TPAFREE'):
        if want not in defined:
            bad.append('VARS.Z8A: the TPA chain does not define %s' % want)
    if not re.search(r'ASSERT\s+TPATOP\s*<=\s*TXPAGE', '\n'.join(tail)):
        bad.append('VARS.Z8A does not ASSERT TPATOP <= TXPAGE')
    for prefix in ('S6ED', 'S2ED'):
        if not os.path.exists(os.path.join(ctx.code_dir, prefix + '.sym')):
            continue
        sym = symbols.load(ctx.code_dir, prefix, TARGETS[prefix])
        free = sym.get('TPAFREE')
        if free is None:
            bad.append('%s.sym has no TPAFREE' % prefix)
        elif not 0 <= free < 0x4000:
            bad.append('%s TPAFREE = %s (TPA overflowed page 2)'
                       % (prefix, free))
    return Check('tpa-chain', not bad, '; '.join(bad) if bad else
                 'TPA allocations chain off ENDVARS, no fixed addresses, '
                 'TPATOP asserted below page 2')


def check_build_symmetry(ctx):
    """`make clean` and `make build` must cover the same targets.

    They did not: `clean` removed the artefacts of both editors while `build`
    assembled S6ED alone, so `make clean build` left the tree half built and
    the S2 half of the harness died on a .sym that did not exist -- reported
    by the user on 2026-09-22 after it had bitten a session.  The shape is
    what matters, so the shape is what is checked: `build` reaches both
    per-target builds, each per-target build produces its own binary, and
    `clean` names both.
    """
    bad = []
    path = os.path.join(ctx.code_dir, 'Makefile')
    text = open(path, errors='replace').read()

    def rule(name):
        """The prerequisites and recipe of one target, as one string."""
        m = re.search(r'^%s:(.*?)(?=^\S|\Z)' % re.escape(name), text,
                      re.M | re.S)
        return m.group(1) if m else None

    build = rule('build')
    if build is None:
        bad.append('Makefile has no build target')
    else:
        for want in ('build-s6', 'build-s2'):
            if not re.search(r'\b%s\b' % want, build):
                bad.append('build does not reach %s' % want)
    for name, var in (('build-s6', 'OUTPUT'), ('build-s2', 'OUTPUT_S2')):
        r = rule(name)
        if r is None:
            bad.append('Makefile has no %s target' % name)
        elif '$(%s)' % var not in r:
            bad.append('%s does not build $(%s)' % (name, var))
    clean = rule('clean')
    if clean is None:
        bad.append('Makefile has no clean target')
    else:
        for var in ('OUTPUT', 'OUTPUT_S2'):
            if '$(%s)' % var not in clean:
                bad.append('clean does not remove $(%s)' % var)
    # The S6ED disk carries S2ED too, so one image runs both editors on an
    # MSX2.  Nothing in a build failure would reveal a tidied-up DSKCONT --
    # the disk would simply come out with one editor on it.
    m = re.search(r'^DSKCONT\s*=(.*?)^\s*$', text, re.M | re.S)
    if m is None:
        bad.append('Makefile has no DSKCONT')
    elif '$(OUTPUT_S2)' not in m.group(1):
        bad.append('the S6ED disk does not carry $(OUTPUT_S2)')
    return Check('build-symmetry', not bad, '; '.join(bad) if bad else
                 'build reaches both targets, clean removes what both '
                 'produce, and the S6ED disk carries both')


ALL = [check_build_clean, check_image_end, check_vars_block, check_init_clear,
       check_layout_asserts, check_record_exclusive, check_target_params,
       check_data_placement,
       check_label_style,
       check_number_notation, check_defb_width, check_page1_hooks,
       check_assets, check_feature_discipline, check_window_discipline,
       check_ftr_budget, check_tpa_chain, check_build_symmetry]


def run(ctx):
    """Build first, then parse the .sym the build just produced."""
    checks = [check_build_clean(ctx)]
    if not checks[0].ok:
        return checks
    ctx.reload_symbols()
    return checks + [fn(ctx) for fn in ALL if fn is not check_build_clean]
