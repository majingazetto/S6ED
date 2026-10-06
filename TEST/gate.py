"""The Gate -- the cases that must pass before an integration is closed.

Each one was derived backwards from a defect that actually reached `dev` and
had to be hunted down with the emulator afterwards.  The point is not coverage:
it is that the whole set runs at the end of EVERY integration, whatever was
touched, because not one of these defects was found by the feature that broke
it.  `origin` on each case says which.
"""

import hashlib
import os
import re

import vram
from cases import (Case, DEFAULT_CFG, HomePathCase, LongPathCase,
                   ShippedDiskCase, crlf, io_fixture, numbered)
from harness import MACH_128K, MACH_2MB, MACH_JP
from keys import Timeline
from result import Check

LINEREC = 161
SEGLAST = 100 * LINEREC


def image_of(ctx):
    with open(os.path.join(ctx.code_dir, 'S6ED.COM'), 'rb') as fh:
        return fh.read()


def font_of(ctx):
    with open(os.path.join(ctx.code_dir, 'S6ED.FNT'), 'rb') as fh:
        return fh.read()


def asciiz(run, label, name):
    """A captured ASCIIZ byte range as text; None when it was not captured.

    run.var() of a byte range the snapshot does not carry is None, and
    `None or b''` reads as an empty string -- which is how G3's
    filename-cleared check passed for months without FILENAME ever being
    captured.  Callers must treat None as a failure.
    """
    raw = run.snaps.get(label, {}).get(name)
    if raw is None:
        return None
    return bytes(raw).split(b'\0')[0].decode('ascii', 'replace')


def one(runs):
    return runs[None]


# --- G1  CODE IMAGE INTEGRITY -----------------------------------------


class G1Image(Case):
    name = 'G1-image'
    desc = 'no editing path writes into the program image'
    origin = ('line directory pinned at #4000: a 200-line document overwrote '
              '#4000-#4257, DISPKEY among the casualties, and the first '
              'keystroke left the editor')

    def fixture(self, ctx, variant=None):
        # Below the 128 kB capacity (101 lines since Fase 1a reserved FTRSEG),
        # so the Enter/Backspace pairs and the multi-line paste have room to
        # land -- at capacity they are refused and the stress passes vacuously.
        return crlf(numbered(80))

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.snap('boot', image=True)
        # Deliberately broad: every structure that has ever grown into someone
        # else's memory gets exercised before the second sample.
        t.press('DOWN', repeat=8)
        for _ in range(12):
            t.press('RETURN')
            t.press('BS')
        t.text('STRESS')
        t.press('DOWN', mods=['GRAPH'])
        t.press('UP', mods=['GRAPH'])
        t.press('DOWN', mods=['SHIFT'], repeat=4)
        t.press('C', mods=['CTRL'])
        t.press('DOWN', mods=['CTRL'])
        t.press('V', mods=['CTRL'])
        t.snap('after', image=True)
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        want = image_of(ctx)[:ctx.sym['VARS'] - 0x100]
        checks = []
        # The stress must actually have happened, or the case passes vacuously.
        moved = (run.var('after', 'TOTLINES') != run.var('boot', 'TOTLINES')
                 and run.var('after', 'MODIFIED') == 0xFF)
        checks.append(Check('G1/stress-landed', moved,
                            'TOTLINES %s -> %s, MODIFIED %s'
                            % (run.var('boot', 'TOTLINES'),
                               run.var('after', 'TOTLINES'),
                               run.var('after', 'MODIFIED'))))
        for label in ('boot', 'after'):
            got = run.blob(label, 'image')
            if got is None:
                checks.append(Check('G1/%s-image' % label, False, 'no dump'))
                continue
            first = next((i for i in range(min(len(got), len(want)))
                          if got[i] != want[i]), None)
            checks.append(Check('G1/%s-image' % label, first is None,
                                'identical to S6ED.COM (%d bytes)' % len(want)
                                if first is None else
                                'MODIFIED, first difference at #%04X'
                                % (0x100 + first)))
        return checks


# --- G2  SAVE OVER AN EXISTING FILE -----------------------------------


class G2Save(Case):
    name = 'G2-save'
    desc = 'saving twice over a file that already exists'
    origin = ('DCREATE did not initialise B, so DOS 2 _CREATE returned .FILEX '
              '(#B7) on an existing file and FILESAVE silently did nothing')

    LINES = ['FIRST LINE', 'SECOND LINE', 'THIRD LINE']

    def fixture(self, ctx, variant=None):
        return crlf(self.LINES)

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.snap('boot')
        t.text('AA')
        t.press('S', mods=['CTRL'])
        t.wait(2.0)
        t.snap('save1')
        t.text('BB')
        t.press('S', mods=['CTRL'])
        t.wait(2.0)
        t.snap('save2')
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        checks = []
        for label in ('save1', 'save2'):
            checks.append(Check('G2/%s-clean' % label,
                                run.var(label, 'MODIFIED') == 0,
                                'MODIFIED = %s after save'
                                % run.var(label, 'MODIFIED')))
        got = run.session.extract(run.dsk, 'DOC.TXT')
        want = crlf(['AABB' + self.LINES[0]] + self.LINES[1:])
        checks.append(Check('G2/content', got == want,
                            'file on disk matches byte for byte'
                            if got == want else
                            'got %r, want %r' % (got, want)))
        return checks


# --- G3  GRACEFUL EXHAUSTION ------------------------------------------


class G3Oom(Case):
    name = 'G3-oom'
    desc = 'oversized file is refused, keeps the editor alive, disk file intact'
    origin = ('oversized file (> capacity) must not load partially to prevent '
              'silent data loss on save; editor rolls back to 1 empty line and '
              'clears FILENAME')
    machine = MACH_128K
    FIXTURE_LINES = 150
    PREFIX = 'G3'
    # 128 kB DOS 2: 2 free segments, both reserved (DIRSEG + FTRSEG), so the
    # text pool is DEFSEG2 alone.  CHKFLEN's byte ceiling is
    # (SEGAVL + 1) * 101 * (TEXTCOLS + 2): 8,282 with the pool claimed and
    # 16,564 without the FTRSEG claim (mut/f1a-noftr).  150 lines of 79 chars
    # = 12,150 bytes sits exactly between the two ceilings, and their real
    # storage (150 x 164 = 24,600) fits the doubled pool -- so the mutation
    # is precisely the difference between refused and loaded.

    def fixture(self, ctx, variant=None):
        return crlf([('LINE %05d ' % i) + ('X' * 68) for i in range(1, self.FIXTURE_LINES + 1)])

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.snap('loaded')
        # An attempt to save (Ctrl+S) should not overwrite DOC.TXT because
        # FILENAME was cleared on load refusal.
        t.press('S', mods=['CTRL'])
        t.wait(3.0)
        t.snap('saved')
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        tot = run.var('loaded', 'TOTLINES')
        loaderr = run.var('loaded', 'LOADERR')
        fname = asciiz(run, 'loaded', 'FILENAME')
        checks = [
            Check('%s/load-refused' % self.PREFIX, tot == 1 and loaderr == 1,
                  'oversized file refused (TOTLINES=%s, LOADERR=%s)'
                  % (tot, loaderr)),
            Check('%s/filename-cleared' % self.PREFIX, fname == '',
                  'FILENAME cleared on refusal to protect disk file (%r)'
                  % fname),
            Check('%s/alive' % self.PREFIX, run.var('loaded', 'SCRRDY') == 0xFF,
                  'editor still running after refusal'),
        ]
        got = run.session.extract(run.dsk, 'DOC.TXT')
        want = self.fixture(ctx)
        checks.append(Check('%s/document-intact' % self.PREFIX, got == want,
                            'disk file DOC.TXT preserved intact with all %d lines'
                            % self.FIXTURE_LINES
                            if got == want else
                            'disk file corrupted: got %d bytes, expected %d'
                            % (len(got or b''), len(want or b''))))
        return checks


class G3BOomShort(G3Oom):
    name = 'G3B-oomshort'
    desc = ('many one-char lines pass the size pre-check but exhaust real '
            'records mid-read: the rollback must still fire')
    origin = ('CHKFLEN estimates worst-case (long-line) capacity, so a file '
              'of one-char lines passes it and then OOMs halfway through the '
              'read: 36 bytes per record x 600 lines = 21,600 over the '
              '16,384 the single text segment holds.  Without the .OOMNL '
              'rollback the editor keeps ~455 truncated lines and FILENAME, '
              'and the next Ctrl+S destroys the disk file')
    FIXTURE_LINES = 600
    PREFIX = 'G3B'

    def fixture(self, ctx, variant=None):
        return crlf(['X'] * self.FIXTURE_LINES)


# --- G4  DELETED RECORDS ARE RECYCLED ---------------------------------


class G4FreeList(Case):
    name = 'G4-freelist'
    desc = 'deleted line records come back through the free list'
    origin = ('LINEDEL abandoned the 161-byte record while the append cursor '
              'only moved forward: 200 alternating Enter/Backspace presses '
              'consumed two whole 16 kB segments on a 128 kB machine')
    cfg = DEFAULT_CFG.replace('AUTOALIGN=DEV', 'AUTOALIGN=OFF')
    N = 40

    def fixture(self, ctx, variant=None):
        return crlf(numbered(5))

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.snap('base')
        t.press('RETURN', repeat=self.N)      # claim N records
        t.snap('grown')
        t.press('BS', repeat=self.N)          # give them all back
        t.snap('freed')
        t.press('RETURN', repeat=self.N)      # must come out of the free list
        t.snap('reused')
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        grown, freed, reused = (run.snaps.get(k, {}) for k in
                                ('grown', 'freed', 'reused'))
        checks = [
            Check('G4/claimed', grown.get('LINEOFF', 0) >
                  run.var('base', 'LINEOFF'),
                  'LINEOFF %s -> %s over %d Returns'
                  % (run.var('base', 'LINEOFF'), grown.get('LINEOFF'), self.N)),
            Check('G4/freed', freed.get('FREEHD') != 0xFF,
                  'free list head = %s after %d Backspaces'
                  % (freed.get('FREEHD'), self.N)),
            Check('G4/no-growth',
                  reused.get('LINEOFF') == grown.get('LINEOFF'),
                  'LINEOFF flat at %s across the second burst'
                  % reused.get('LINEOFF')),
            Check('G4/no-segment-claim',
                  reused.get('SEGCNT') == grown.get('SEGCNT'),
                  'SEGCNT %s -> %s' % (grown.get('SEGCNT'),
                                       reused.get('SEGCNT'))),
            Check('G4/list-drained', reused.get('FREEHD') == 0xFF,
                  'free list drained to FREENIL'),
            Check('G4/lines', reused.get('TOTLINES') == grown.get('TOTLINES'),
                  'TOTLINES %s -> %s' % (grown.get('TOTLINES'),
                                         reused.get('TOTLINES'))),
        ]
        return checks


# --- G5  THE CLOCK LEAVES NO RESIDUE ----------------------------------


class G5Clock(Case):
    name = 'G5-clock'
    desc = 'every clock cell is exactly its glyph, across minute changes'
    origin = ('UPDMCLK cleared its HH:MM box with HMMV, a byte-unit command on '
              'a 4-pixel-per-byte screen: NX = 30 truncated to 28 and the '
              'right stroke of the previous digit survived, accumulating')
    CLOCK_X = 476               # DX of "HH:MM" in the menu row

    # A truncated clear only SHOWS on a digit change that removes ink from the
    # last two pixel columns, so one minute change is not enough and the RTC
    # follows the host clock -- the test would be flaky by time of day.
    # Measured against the shipped font: of the ten consecutive units-digit
    # transitions, 6 reveal the residue and the non-revealing ones are
    # (1,2) (3,4) (8,9) (9,0), whose longest consecutive run is two (8->9->0).
    # THREE minute changes therefore always contain at least one revealing
    # transition.
    # Sampling intervals tuned to the MSX hardware frame rate:
    # On PAL (Philips NMS 8250 at 50.157 Hz), 50 frames is ~0.99687 s.
    # Stepping by exactly 31 50-frame cycles (31 * 50 / 50.157 ≈ 30.903 s)
    # alternates the blink phase (31 is odd) while keeping the sample locked
    # to the midpoint of the 1-second window with strictly zero accumulated drift.
    # 7 samples span ~3.1 minutes, guaranteeing observation of at least 4 distinct
    # minutes across any boot time.
    SAMPLES = [3.5 + (31 * (50.0 / 50.15738)) * i for i in range(7)]
    MIN_MINUTES = 4             # 4 distinct minutes = 3 transitions

    def fixture(self, ctx, variant=None):
        return crlf(numbered(5))

    def timeline(self, ctx, variant=None):
        t = Timeline()
        # Sampling across ~2.5 emulated minutes catches at least two real
        # minute changes, in both colon blink phases.
        for i, at in enumerate(self.SAMPLES):
            t.t = at
            t.snap('c%d' % i, vram='menu')
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        font = font_of(ctx)
        checks = []
        seen = set()
        for i in range(len(self.SAMPLES)):
            label = 'c%d' % i
            buf = run.blob(label, 'menu')
            snap = run.snaps.get(label, {})
            if buf is None or 'CLKBUF' not in snap:
                checks.append(Check('G5/%s' % label, False, 'no sample'))
                continue
            text = ''.join(chr(c) for c in snap['CLKBUF'][:5])
            seen.add(text[:2] + text[3:])
            bad = []
            for pos, ch in enumerate(text):
                if pos == 2:
                    # The colon cell is driven by the blink phase, not CLKBUF.
                    ch = ':' if snap.get('CLKPH') == 0 else ' '
                x0 = self.CLOCK_X + pos * vram.CELLW
                got = vram.ink_mask(buf, x0, 0, ground=vram.COL_UI)
                want = vram.glyph_mask(font, ch)
                if got != want:
                    extra = sum(1 for y in range(8) for x in range(6)
                                if got[y][x] and not want[y][x])
                    missing = sum(1 for y in range(8) for x in range(6)
                                  if want[y][x] and not got[y][x])
                    bad.append('cell %d (%r): %d stray, %d missing px'
                               % (pos, ch, extra, missing))
            checks.append(Check('G5/%s' % label, not bad,
                                '%s phase %s: clean'
                                % (text, snap.get('CLKPH'))
                                if not bad else '%s: %s' % (text, '; '.join(bad))))
        checks.append(Check('G5/minute-changed', len(seen) >= self.MIN_MINUTES,
                            'observed %d distinct minutes (need %d for the '
                            'revealing-transition guarantee)'
                            % (len(seen), self.MIN_MINUTES)))
        return checks


# --- G6  NOTHING LIVES IN PAGE 1 BEHIND AN INTERRUPT ------------------


class G6Hooks(Case):
    name = 'G6-hooks'
    desc = 'no interrupt hook of ours, and a stack that stays put'
    origin = ('the RTC colon blink hooked H.TIMI at an address inside the '
              'image: the Disk ROM banks itself over page 1 whenever disk code '
              'runs, so 3 of 2,174 VBLANKs jumped into FDC ROM and SP ran away '
              'from #D6F4 to #3CBB')
    SP_LO, SP_HI = 0xD600, 0xD800

    def fixture(self, ctx, variant=None):
        return crlf(numbered(30))

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.snap('boot')
        t.text('EDIT')
        t.press('S', mods=['CTRL'])       # disk I/O: the Disk ROM banks in
        t.wait(3.0)
        t.snap('after-io')
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        checks = []
        boot = run.snaps.get('boot', {}).get('HTIMI')
        after = run.snaps.get('after-io', {}).get('HTIMI')
        checks.append(Check('G6/hook-stable', boot == after,
                            'H.TIMI %s' % (' '.join('%02X' % b for b in boot)
                                           if boot else '?')))
        page1 = False
        if boot and boot[0] in (0xC3, 0xCD):       # JP / CALL
            target = boot[1] + 256 * boot[2]
            page1 = 0x4000 <= target < 0x8000
        checks.append(Check('G6/hook-not-page1', not page1,
                            'no hook vector points into #4000-#7FFF'))
        for label in ('boot', 'after-io'):
            sp = run.var(label, 'SP')
            checks.append(Check('G6/sp-%s' % label,
                                sp is not None and self.SP_LO <= sp <= self.SP_HI,
                                'SP = #%04X' % sp if sp else 'SP unread'))
        return checks


# --- G7  RENDER PURITY AND SELECTION RESIDUE --------------------------


class G7Selection(Case):
    name = 'G7-selection'
    desc = 'the screen is a pure function of the document state'
    origin = ('the painted selection range was declared as a lone DEFW, so its '
              'last four bytes were SELDIFF\'s own scratch: it corrupted the '
              'range while reading it, every row but the first inverted only '
              'its line-break cell, and Ctrl+C left 15 cells of residue')

    def fixture(self, ctx, variant=None):
        return crlf(numbered(60))

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.press('DOWN', mods=['SHIFT'], repeat=4)
        t.snap('selected', vram=True)
        t.press('C', mods=['CTRL'])
        t.press('LEFT')                      # any plain motion deselects
        t.press('RIGHT')
        t.snap('deselected', vram=True)
        # A full REDRAW repaints from the document alone.  Whatever the
        # differential painters left behind shows up as a difference here.
        t.press('DOWN', mods=['GRAPH'])
        t.press('UP', mods=['GRAPH'])
        t.snap('redrawn', vram=True)
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        sel = run.snaps.get('selected', {})
        checks = [
            Check('G7/selection-active', sel.get('SELACT') == 1,
                  'SELACT = %s over %s lines'
                  % (sel.get('SELACT'), sel.get('DOCLINE'))),
            Check('G7/painted-range', sel.get('DRWSTRL') == sel.get('SELSTRL'),
                  'painted %s == logical %s'
                  % (sel.get('DRWSTRL'), sel.get('SELSTRL'))),
            Check('G7/clipboard', run.var('deselected', 'CLIPLEN') > 0,
                  'CLIPLEN = %s' % run.var('deselected', 'CLIPLEN')),
        ]
        a, b = run.snaps.get('deselected', {}), run.snaps.get('redrawn', {})
        same_state = all(a.get(k) == b.get(k) for k in
                         ('TOPLINE', 'DOCLINE', 'CURX', 'CURY', 'TOTLINES'))
        checks.append(Check('G7/viewport-returned', same_state,
                            'TOPLINE %s/%s DOCLINE %s/%s CURX %s/%s'
                            % (a.get('TOPLINE'), b.get('TOPLINE'),
                               a.get('DOCLINE'), b.get('DOCLINE'),
                               a.get('CURX'), b.get('CURX'))))
        if same_state:
            cursor = [(a.get('CURX', 0), a.get('CURY', 0))]
            d = vram.diff(run.blob('deselected', 'vram'),
                          run.blob('redrawn', 'vram'), ignore_cells=cursor)
            checks.append(Check('G7/render-pure', not d,
                                'screen identical to a full REDRAW'
                                if not d else
                                '%d stray pixels, first at (%d,%d)'
                                % (len(d), d[0][0], d[0][1])))
        return checks


# --- G8  CONFIGURATION, IN THE FORM THAT BROKE ------------------------


class G8Config(Case):
    name = 'G8-config'
    desc = 'every S6ED.CFG key parsed, spaced form, and both ends of each range'
    origin = ('CFGVAL matched the key as a bare prefix, so "TABWIDTH = 8" with '
              'spaces failed and the whole line was ignored -- reported as '
              '"the CFG is ignored".  The second variant exists because one '
              'value per key is not coverage: PARSALN dispatched on the FIRST '
              'letter of the value, OFF and ON collide there, and the table '
              'sent both to ALGN_ON -- so AUTOALIGN=OFF turned auto-align on '
              'and the case that only ever tried ON never noticed.')
    # Spaced form, trailing comments, CRLF -- and every value different from
    # the other variant's, so each parser is exercised at both ends.
    SPACED = ("; spaced form, trailing comments, CRLF\r\n"
              "PROFILE = VI\r\n"
              "WRAP  =  TXT\r\n"
              "MARKUP = LIT\r\n"
              "CLOCK = 0\r\n"
              "TABWIDTH = 8\r\n"
              "EOL = UNIX\r\n"
              "AUTOALIGN = ON\r\n"
              "THEME = AMBER\r\n")
    COMPACT = ("PROFILE=STD\n"
               "WRAP=DEV\n"
               "MARKUP=MD\n"
               "CLOCK=1\n"
               "TABWIDTH=2\n"
               "EOL=DOS\n"
               "AUTOALIGN=OFF\n"
               "THEME=GREEN\n")
    # THMAMBR and THMGRN in CFG.Z8A
    AMBER = [0x00, 0x00, 0x70, 0x04, 0x20, 0x01, 0x70, 0x06]
    GREEN = [0x00, 0x00, 0x11, 0x07, 0x00, 0x02, 0x40, 0x07]

    variants = ('spaced', 'compact')

    WANT = {
        'spaced': ([('KMAPID', 3, 'PROFILE=VI'), ('WRAPMODE', 1, 'WRAP=TXT'),
                    ('MKUPMD', 2, 'MARKUP=LIT'), ('SHOWCLK', 0, 'CLOCK=0'),
                    ('TABWIDTH', 8, 'TABWIDTH=8'), ('SAVEEOL', 1, 'EOL=UNIX'),
                    ('AUTOALGN', 1, 'AUTOALIGN=ON')], AMBER),
        'compact': ([('KMAPID', 0, 'PROFILE=STD'), ('WRAPMODE', 0, 'WRAP=DEV'),
                     ('MKUPMD', 1, 'MARKUP=MD'), ('SHOWCLK', 1, 'CLOCK=1'),
                     ('TABWIDTH', 2, 'TABWIDTH=2'), ('SAVEEOL', 0, 'EOL=DOS'),
                     ('AUTOALGN', 0, 'AUTOALIGN=OFF')], GREEN),
    }

    def config(self, ctx, variant=None):
        return self.SPACED if variant == 'spaced' else self.COMPACT

    def fixture(self, ctx, variant=None):
        return crlf(numbered(5))

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.snap('boot', palette=True)
        return t

    def verify(self, ctx, runs):
        checks = []
        for variant, run in sorted(runs.items()):
            want, theme = self.WANT[variant]
            checks += [Check('G8/%s/%s' % (variant, why.split('=')[0].lower()),
                             run.var('boot', name) == value,
                             '%s -> %s = %s' % (why, name,
                                                run.var('boot', name)))
                       for name, value, why in want]
            pal = run.snaps.get('boot', {}).get('PALDATA')
            checks.append(Check('G8/%s/theme' % variant, pal == theme,
                                'PALDATA = %s'
                                % (' '.join('%02X' % b for b in pal)
                                   if pal else '?')))
            vdp = run.blob('boot', 'pal')
            checks.append(Check('G8/%s/vdp-palette' % variant,
                                vdp is not None and list(vdp[:8]) == theme,
                                'VDP palette registers 0-3 match the theme'
                                if vdp else 'no palette dump'))
        return checks


# --- B4  CFG BEYOND THE BUFFER ------------------------------------------


class B4CfgStream(Case):
    name = 'B4-cfg-stream'
    desc = 'a CFG far past the old 1024-byte cap and the 2048-byte chunk'
    origin = ('CFGLOAD read at most 1024 bytes of S6ED.CFG and silently '
              'dropped the rest, and the shipped CFG was already 922 bytes.  '
              'The loader now streams CLIPMAX-byte chunks and parses line by '
              'line, so the file size is no longer capped by any buffer')
    AMBER = [0x00, 0x00, 0x70, 0x04, 0x20, 0x01, 0x70, 0x06]

    # 32 comment lines of 81 bytes push every real key past byte 2048, so a
    # single-chunk loader cannot see them.  The overlong line (130 spaces
    # before the key) must be dropped whole: if its TABWIDTH=2 leaked
    # through, it would win over the TABWIDTH=8 above it.  PROFILE comes
    # last with no trailing EOL, the EOF-with-pending-line path.
    cfg = ((';' + ' pad' * 19 + '\r\n') * 32 +
           "TABWIDTH = 8\r\n" +
           ' ' * 130 + "TABWIDTH = 2\r\n" +
           "THEME = AMBER\r\n" +
           "PROFILE=TED")

    def fixture(self, ctx, variant=None):
        return crlf(numbered(5))

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.snap('boot', palette=True)
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        checks = []
        checks.append(Check('B4/past-chunk',
                            run.var('boot', 'TABWIDTH') == 8,
                            'TABWIDTH=%s (key past byte 2048, overlong '
                            'sibling dropped)' % run.var('boot', 'TABWIDTH')))
        checks.append(Check('B4/no-final-eol',
                            run.var('boot', 'KMAPID') == 1,
                            'KMAPID=%s (PROFILE=TED, no trailing EOL)'
                            % run.var('boot', 'KMAPID')))
        pal = run.snaps.get('boot', {}).get('PALDATA')
        checks.append(Check('B4/theme', pal == self.AMBER,
                            'PALDATA = %s'
                            % (' '.join('%02X' % b for b in pal)
                               if pal else '?')))
        return checks


# --- G9  THE LINE DIRECTORY SURVIVES BANKING --------------------------


class G9Directory(Case):
    name = 'G9-directory'
    desc = 'mid-document insert and join round-trip through DIRBANK'
    origin = ('DIRBANK did not preserve HL -- PUTP2 destroys it with the '
              'mapper routine address while DIRREAD/DIRWRITE carry the line '
              'number there, so every entry was read and written at a garbage '
              'address')
    LINES = 60

    def fixture(self, ctx, variant=None):
        return crlf(numbered(self.LINES))

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.snap('boot', dirseg=True)
        t.press('DOWN', repeat=29)
        t.press('RETURN')                 # LINEINS shifts ~30 entries
        t.snap('inserted', dirseg=True)
        t.press('BS')                     # join it straight back
        t.snap('joined', dirseg=True)
        t.press('S', mods=['CTRL'])
        t.wait(3.0)
        t.snap('saved', dirseg=True)
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        checks = [
            Check('G9/inserted', run.var('inserted', 'TOTLINES') ==
                  self.LINES + 1,
                  'TOTLINES %s after the insert'
                  % run.var('inserted', 'TOTLINES')),
            Check('G9/restored', run.var('joined', 'TOTLINES') == self.LINES,
                  'TOTLINES back to %s' % run.var('joined', 'TOTLINES')),
            Check('G9/record-recycled',
                  run.var('joined', 'FREEHD') != 0xFF,
                  'the joined record went on the free list (head %s)'
                  % run.var('joined', 'FREEHD')),
        ]
        for label in ('boot', 'joined'):
            bad = self._walk(run, label)
            checks.append(Check('G9/walk-%s' % label, not bad,
                                '%s entries well formed'
                                % run.var(label, 'TOTLINES')
                                if not bad else bad))
        got = run.session.extract(run.dsk, 'DOC.TXT')
        want = crlf(numbered(self.LINES))
        checks.append(Check('G9/round-trip', got == want,
                            'document identical after insert + join'
                            if got == want else 'document changed'))
        return checks

    def _walk(self, run, label):
        """Every directory entry must name a tracked segment and a real slot."""
        blob = run.blob(label, 'dir')
        if blob is None:
            return 'no directory dump'
        tot = run.var(label, 'TOTLINES') or 0
        segs = set(int(x) for x in run.var(label, 'SEGTBL').split() if int(x))
        segs.add(run.var(label, 'TXSEG0'))
        for i in range(tot):
            seg = blob[i * 3]
            off = blob[i * 3 + 1] + 256 * blob[i * 3 + 2]
            if seg not in segs:
                return 'entry %d names segment %d, not in %s' % (i, seg,
                                                                 sorted(segs))
            if off >= 16384 or off % 2:
                return 'entry %d offset %d is not a record boundary' % (i, off)
        return None


# --- G10  AUTOALIGN PROMISES INDENTATION, IT DOES NOT WRITE IT --------


class G10Autoalign(Case):
    name = 'G10-autoalign'
    desc = 'Enter under AUTOALIGN leaves no trailing spaces on disk'
    origin = ('Enter without typing left CURX past the length, missed the '
              'CURX == length gate and took the classic split, whose .TRUNC '
              'stretched the head to SPLCOL: the blank line came back holding '
              '13 spaces and the cursor dropped to column 0')
    SOURCE = 'LABEL   LD      A, 1'
    ALIGN = 8                   # the column of the token after the label

    def fixture(self, ctx, variant=None):
        return crlf([self.SOURCE])

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.press('RIGHT', mods=['CTRL'])       # end of line
        t.press('RETURN')
        t.snap('nl1')
        t.press('RETURN')
        t.press('RETURN')
        t.snap('nl3')
        t.press('S', mods=['CTRL'])
        t.wait(3.0)
        t.snap('saved')
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        checks = [
            Check('G10/aligned', run.var('nl1', 'CURX') == self.ALIGN,
                  'cursor at column %s (expected %d)'
                  % (run.var('nl1', 'CURX'), self.ALIGN)),
            Check('G10/chained', run.var('nl3', 'CURX') == self.ALIGN,
                  'still column %s after three Returns'
                  % run.var('nl3', 'CURX')),
            Check('G10/lines', run.var('nl3', 'TOTLINES') == 4,
                  'TOTLINES = %s' % run.var('nl3', 'TOTLINES')),
        ]
        got = run.session.extract(run.dsk, 'DOC.TXT')
        if got is None:
            checks.append(Check('G10/no-trailing-spaces', False, 'no file'))
            return checks
        lines = got.decode('latin-1').split('\r\n')
        dirty = [i for i, l in enumerate(lines) if l != l.rstrip()]
        checks.append(Check('G10/no-trailing-spaces', not dirty,
                            'no line holds trailing spaces'
                            if not dirty else
                            'lines %s hold trailing spaces' % dirty))
        checks.append(Check('G10/source-intact', lines[0] == self.SOURCE,
                            'first line unchanged'
                            if lines[0] == self.SOURCE else
                            'first line is %r' % lines[0]))
        return checks


# --- G11  BATCH INSERT == CHARACTER INSERT ----------------------------


class G11Paste(Case):
    name = 'G11-paste'
    desc = 'pasting a run and typing the same characters agree exactly'
    origin = ('ACTPAST was rewritten to insert runs (EDINSRUN / WBINSN) '
              'instead of characters: 40 chars 2,043 -> 82 ms. Equivalence '
              'with the per-character path is the whole safety argument')
    variants = ('paste', 'type')
    PAYLOAD = 'ABCDEFGHIJ0123456789'
    LINES = ['TARGET LINE', 'SECOND LINE', 'THIRD LINE']

    def fixture(self, ctx, variant=None):
        return crlf([self.PAYLOAD] + self.LINES)

    def timeline(self, ctx, variant=None):
        t = Timeline()
        if variant == 'paste':
            # Select the payload line, copy it, then insert it as one run.
            t.press('RIGHT', mods=['SHIFT', 'CTRL'])   # select to end of line
            t.snap('selected')
            t.press('C', mods=['CTRL'])
            t.press('DOWN')
            t.press('LEFT', mods=['CTRL'])             # column 0 of line 2
            t.press('V', mods=['CTRL'])
        else:
            t.press('DOWN')
            t.press('LEFT', mods=['CTRL'])
            t.text(self.PAYLOAD)                       # one EDINSCHR per char
        t.snap('inserted', vram=True)
        t.press('S', mods=['CTRL'])
        t.wait(3.0)
        t.snap('saved', vram=True)
        return t

    def verify(self, ctx, runs):
        paste, typed = runs['paste'], runs['type']
        checks = []
        clip = paste.var('inserted', 'CLIPLEN')
        checks.append(Check('G11/clipboard', clip == len(self.PAYLOAD),
                            'CLIPLEN = %s for a %d character line'
                            % (clip, len(self.PAYLOAD))))
        want = crlf([self.PAYLOAD, self.PAYLOAD + self.LINES[0]] +
                    self.LINES[1:])
        for label, run in (('paste', paste), ('type', typed)):
            got = run.session.extract(run.dsk, 'DOC.TXT')
            checks.append(Check('G11/%s-content' % label, got == want,
                                'document as expected' if got == want else
                                'got %r' % (got[:60] if got else None)))
        for name in ('TOTLINES', 'CURX', 'DOCLINE'):
            checks.append(Check('G11/%s' % name.lower(),
                                paste.var('inserted', name) ==
                                typed.var('inserted', name),
                                '%s %s / %s' % (name,
                                                paste.var('inserted', name),
                                                typed.var('inserted', name))))
        cursor = [(paste.var('inserted', 'CURX') or 0,
                   paste.var('inserted', 'CURY') or 0),
                  (typed.var('inserted', 'CURX') or 0,
                   typed.var('inserted', 'CURY') or 0)]
        d = vram.diff(paste.blob('inserted', 'vram'),
                      typed.blob('inserted', 'vram'), ignore_cells=cursor)
        checks.append(Check('G11/screen-equal', not d,
                            'both paths paint the same screen' if not d else
                            '%d differing pixels, first at (%d,%d)'
                            % (len(d), d[0][0], d[0][1])))
        return checks


# --- G12 SCREEN RESTORATION ON EXIT ----------------------------------


class G12ScreenRestore(Case):
    name = 'G12-screen-restore'
    desc = 'screen mode, width, text colors and VDP palette match pre-entry state upon exit'
    origin = ('exit to DOS left Screen 6 palette active, corrupting text colors 0-3, '
              'and did not formally restore screen mode, line width or text colors; '
              'CHGMOD does not restore R#8 either, so DOS kept SPD=1 (no sprites) '
              'and TP=1 for whatever ran next')

    DEFPLT = [
        0x00, 0x00, 0x00, 0x00, 0x11, 0x06, 0x33, 0x07,
        0x17, 0x01, 0x27, 0x03, 0x51, 0x01, 0x27, 0x06,
        0x71, 0x01, 0x73, 0x03, 0x61, 0x06, 0x64, 0x06,
        0x11, 0x04, 0x65, 0x02, 0x55, 0x05, 0x77, 0x07,
    ]

    def fixture(self, ctx, variant=None):
        return crlf(numbered(5))

    def timeline(self, ctx, variant=None):
        t = Timeline()
        # 1. Capture running state inside S6ED (Screen 6 active, modified palette 0..3)
        t.snap('boot', palette=True, vdpregs=True)
        # 2. Arm exit snap at TERM.TERMDON so breakpoint is active when TERM runs
        t.snap('exit', palette=True, vdpregs=True, at='TERM.TERMDON')
        # 3. Press Ctrl+Q: ACTQUIT now asks first (DOQIT dialog); 'Y' confirms
        #    and only then does ACTQUIT -> TERM run
        t.press('Q', mods=['CTRL'])
        t.press('Y')
        t.wait(1.0)
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        checks = []

        # S6ED must have changed screen mode to 6 while active
        active_mode = run.var('boot', 'SCRMOD')
        checks.append(Check('G12/active-mode', active_mode == 6,
                            'SCRMOD = 6 inside editor' if active_mode == 6 else
                            'SCRMOD = %s (expected 6)' % active_mode))

        # Restored screen mode at exit must match pre-entry saved mode (Screen 0)
        exit_mode = run.var('exit', 'SCRMOD')
        saved_mode = run.var('exit', 'SAVSCRMD')
        checks.append(Check('G12/restored-mode',
                            exit_mode == saved_mode == 0,
                            'SCRMOD = %s matches saved mode %s (Screen 0)'
                            % (exit_mode, saved_mode)))

        # Restored width at exit must match pre-entry saved width
        exit_width = run.var('exit', 'LINLEN')
        saved_width = run.var('exit', 'SAVLLEN')
        checks.append(Check('G12/restored-width',
                            exit_width == saved_width,
                            'LINLEN = %s matches saved width %s'
                            % (exit_width, saved_width)))

        # Restored colors (FORCLR, BAKCLR, BDRCLR) must match saved values
        colors_match = (run.var('exit', 'FORCLR') == run.var('exit', 'SAVFORC') and
                        run.var('exit', 'BAKCLR') == run.var('exit', 'SAVBAKC') and
                        run.var('exit', 'BDRCLR') == run.var('exit', 'SAVBDRC'))
        checks.append(Check('G12/restored-colors', colors_match,
                            'FORCLR/BAKCLR/BDRCLR match saved entry colors (%s/%s/%s)'
                            % (run.var('exit', 'FORCLR'),
                               run.var('exit', 'BAKCLR'),
                               run.var('exit', 'BDRCLR'))))

        # VDP palette must have differed inside the editor (guarantees test is non-vacuous)
        boot_pal = list(run.blob('boot', 'pal') or [])
        exit_pal = list(run.blob('exit', 'pal') or [])
        checks.append(Check('G12/palette-changed',
                            boot_pal != exit_pal,
                            'VDP palette was altered during editing'))

        # VDP palette at exit must match standard MSX2 palette byte-for-byte across all 32 bytes
        checks.append(Check('G12/vdp-palette',
                            exit_pal == self.DEFPLT,
                            'VDP palette restored to standard MSX2 palette (32 bytes)'
                            if exit_pal == self.DEFPLT else
                            'VDP palette mismatch at exit: %r' % exit_pal[:8]))

        # R#8: SCRINIT ORs in SPD|VR|TP, and CHGMOD leaves R#8 alone on the
        # way out, so only RSTPAL can hand DOS its own value back.  Read the
        # VDP itself, not RG8SAV, which is just the BIOS's copy.
        entry = run.var('exit', 'SAVRG8')
        boot_vdp = run.blob('boot', 'vdp')
        exit_vdp = run.blob('exit', 'vdp')
        boot_r8 = boot_vdp[8] if boot_vdp else None
        exit_r8 = exit_vdp[8] if exit_vdp else None
        checks.append(Check('G12/r8-changed',
                            entry is not None and boot_r8 is not None and
                            boot_r8 != entry,
                            'R#8 = #%02X inside the editor, entry value #%02X'
                            % (boot_r8 or 0, entry or 0)))
        checks.append(Check('G12/restored-r8',
                            exit_r8 is not None and exit_r8 == entry and
                            run.var('exit', 'RG8SAV') == entry,
                            'R#8 = %s, RG8SAV = %s at exit (entry value %s)'
                            % (exit_r8, run.var('exit', 'RG8SAV'), entry)))

        return checks


# --- G13 FEATURE SEGMENT RESIDENCY & INTER-SEGMENT INTEGRITY ------------


class G13FeatureResidency(Case):
    name = 'G13-feature-residency'
    desc = 'FTRSEG stays resident in SEGTBL[1], HOMESEG clean at idle, CFG applied'
    origin = ('Fase 1b inter-segment architecture: feature code lives in FTRSEG, '
              'is copied at boot, and retains residency across execution')
    cfg = ("; spaced form, trailing comments, CRLF\r\n"
           "PROFILE = TED\r\n"
           "WRAP = TXT\r\n"
           "TABWIDTH = 4\r\n")

    def fixture(self, ctx, variant=None):
        return crlf(numbered(5))

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.snap('boot')
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        checks = []

        # 1. SEGCNT must be 2 on stock 128 kB machine (DIRSEG + FTRSEG)
        segcnt = run.var('boot', 'SEGCNT')
        checks.append(Check('G13/segcnt', segcnt == 2,
                            'SEGCNT = %s (expected 2: DIRSEG + FTRSEG)' % segcnt))

        # 2. SEGTBL[0] is DIRSEG, SEGTBL[1] is FTRSEG, both non-zero and distinct
        dirseg = run.var('boot', 'DIRSEG')
        ftrseg = run.var('boot', 'FTRSEG')
        raw_tbl = [int(x) for x in run.var('boot', 'SEGTBL').split()]
        tbl_match = len(raw_tbl) >= 2 and raw_tbl[0] == dirseg and raw_tbl[1] == ftrseg
        checks.append(Check('G13/segtbl-entries',
                            tbl_match and dirseg != 0 and ftrseg != 0 and dirseg != ftrseg,
                            'SEGTBL[0..1] = [%s, %s] (DIRSEG=%s, FTRSEG=%s)'
                            % (raw_tbl[0] if raw_tbl else None,
                               raw_tbl[1] if len(raw_tbl) > 1 else None,
                               dirseg, ftrseg)))

        # 3. HOMESEG must be 0 at MAINLOOP (core is running, no feature active)
        homeseg = run.var('boot', 'HOMESEG')
        checks.append(Check('G13/homeseg-idle', homeseg == 0,
                            'HOMESEG = %s (expected 0 when idle in core)' % homeseg))

        # 4. SEGSP must be 0 at MAINLOOP (stack clean, no unbalanced FCALLs)
        segsp = run.var('boot', 'SEGSP')
        checks.append(Check('G13/segsp-clean', segsp == 0,
                            'SEGSP = %s (expected 0: inter-segment stack clean)' % segsp))

        # 5. Config loaded via FCALL was applied
        checks.append(Check('G13/cfg-applied',
                            run.var('boot', 'KMAPID') == 1 and
                            run.var('boot', 'WRAPMODE') == 1 and
                            run.var('boot', 'TABWIDTH') == 4,
                            'KMAPID=%s WRAPMODE=%s TABWIDTH=%s from CFG'
                            % (run.var('boot', 'KMAPID'),
                               run.var('boot', 'WRAPMODE'),
                               run.var('boot', 'TABWIDTH'))))

        return checks


# --- H1-H4  COMMAND-LINE PARAMETERS & SWITCHES ------------------------


class _HelpCase(Case):
    absolute = True               # never reaches MAINLOOP: no T0 to anchor to
    cfg = None                    # help must not depend on S6ED.CFG

    def timeline(self, ctx, variant=None):
        t = Timeline(start=2.0)   # arm early: the breakpoint then just waits
        t.snap('exit', vram='text', at='TERM.TERMDON')
        t.t = 45.0                # finish well past boot; MAINLOOP never comes
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        ver = self._version(ctx)
        want = b'S6ED v' + ver
        text = run.blob('exit', 'text')
        printed = text is not None and want in text
        tag = self.name.split('-')[0].upper()
        return [
            Check('%s/help-printed' % tag, printed,
                  'text VRAM holds the %r banner' % want if printed else
                  'banner %r not found in the text-mode name table' % want),
            Check('%s/no-screen6' % tag,
                  run.var('exit', 'SCRRDY') == 0 and
                  run.var('exit', 'SCRMOD') == 0,
                  'SCRRDY %s / SCRMOD %s: never entered graphic mode'
                  % (run.var('exit', 'SCRRDY'), run.var('exit', 'SCRMOD'))),
            Check('%s/no-segments' % tag, run.var('exit', 'SEGCNT') == 0,
                  'SEGCNT %s: exit before SEGRESV claims nothing'
                  % run.var('exit', 'SEGCNT')),
        ]

    def _version(self, ctx):
        """The version the banner must show, straight from CONST.Z8A (or CONST_CORE.Z8A)."""
        path = ctx.find_src_file('CONST_CORE.Z8A')
        if not os.path.exists(path):
            path = ctx.find_src_file('CONST.Z8A')
        with open(path) as fh:
            src = fh.read()
        m_maj = re.search(r"\.MAJOR\s+EQU\s+'(.)'", src)
        if not m_maj:
            with open(ctx.find_src_file('CONST.Z8A')) as fh:
                src = fh.read()
            m_maj = re.search(r"\.MAJOR\s+EQU\s+'(.)'", src)
        maj = m_maj.group(1)
        mnr = re.search(r"\.MINOR\s+EQU\s+'(.)'", src).group(1)
        return ('%s.%s' % (maj, mnr)).encode('ascii')


class H1Help(_HelpCase):
    name = 'H1-help'
    desc = '/H prints version and usage in text mode and exits before SCREEN 6'
    origin = ('command-line switches: PARAMS now runs in text mode before '
              'MAPINIT/SEGRESV, so /H must print and exit with no segment '
              'claimed and the screen untouched')
    autoexec = 'S6ED /H'


class H2HelpQuestion(_HelpCase):
    name = 'H2-help-question'
    desc = '/? prints version and usage in text mode and exits before SCREEN 6'
    origin = '/? is the traditional DOS alias for /H'
    autoexec = 'S6ED /?'


class H3HelpFile(_HelpCase):
    name = 'H3-help-file'
    desc = '/H takes precedence over a filename argument'
    origin = '/H wins over everything on the line, even with a file target'
    autoexec = 'S6ED DOC.TXT /H'


class H4FileSwitch(Case):
    name = 'H4-file-switch'
    desc = 'filename loaded normally when preceded by an ignored switch'
    origin = 'CHKFILE must skip / switches and find the bare filename'
    autoexec = 'S6ED /X DOC.TXT'

    def fixture(self, ctx, variant=None):
        return crlf(numbered(5))

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.snap('boot', vram=True)
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        return [
            Check('H4/screen6',
                  run.var('boot', 'SCRRDY') == 255 and
                  run.var('boot', 'SCRMOD') == 6,
                  'entered SCREEN 6 normally'),
            Check('H4/file-loaded', run.var('boot', 'TOTLINES') == 5,
                  'loaded 5 fixture lines (TOTLINES = %s)'
                  % run.var('boot', 'TOTLINES')),
        ]


class H5Verbose(Case):
    name = 'H5-verbose'
    desc = '/V switch shows startup banner and memory statistics in text mode'
    origin = 'verbose boot switch /V requested for startup diagnostic'
    autoexec = 'S6ED /V DOC.TXT'
    absolute = True

    def fixture(self, ctx, variant=None):
        return crlf(numbered(5))

    def timeline(self, ctx, variant=None):
        t = Timeline(start=2.0)
        t.snap('textmode', vram='text', at='SEGRESV.KEYWAIT')
        t.snap('boot', at='MAINLOOP')
        t.t = 30.0
        t.press('RETURN')
        t.t = 45.0
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        text = run.blob('textmode', 'text')
        want_title = b'S6ED v'
        want_author = b'Armando Perez Abad'
        want_mapper = b'Total mapper:'
        want_file = b'DOC.TXT'
        has_title = text is not None and want_title in text
        has_author = text is not None and want_author in text
        has_mapper = text is not None and want_mapper in text
        has_file = text is not None and want_file in text
        return [
            Check('H5/text-printed',
                  has_title and has_author and has_mapper and has_file,
                  'text mode printed title, author, mapper info, and file' if (has_title and has_author and has_mapper and has_file) else
                  'missing text mode output: title=%s author=%s mapper=%s file=%s' % (has_title, has_author, has_mapper, has_file)),
            Check('H5/verbose-set', run.var('boot', 'SWTVERB') == 255,
                  'SWTVERB is #FF (%s)' % run.var('boot', 'SWTVERB')),
            Check('H5/screen6',
                  run.var('boot', 'SCRRDY') == 255 and
                  run.var('boot', 'SCRMOD') == 6,
                  'entered SCREEN 6 normally after keypress'),
            Check('H5/file-loaded', run.var('boot', 'TOTLINES') == 5,
                  'loaded 5 fixture lines (TOTLINES = %s)'
                  % run.var('boot', 'TOTLINES')),
        ]


class H6DatMissing(Case):
    name = 'H6-dat-missing'
    desc = 'missing S6ED.DAT aborts cleanly to DOS in text mode'
    origin = 'Fase 2 multi-segment container loader requires S6ED.DAT on disk'
    autoexec = 'S6ED'
    absolute = True
    with_dat = False

    def timeline(self, ctx, variant=None):
        t = Timeline(start=2.0)
        t.snap('exit', vram='text', at='TERM.TERMDON')
        t.t = 45.0
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        want = b'S6ED.DAT not found.'
        text = run.blob('exit', 'text')
        printed = text is not None and want in text
        return [
            Check('H6/not-found-printed', printed,
                  'text VRAM holds %r' % want if printed else
                  'error message %r not found in text-mode name table' % want),
            Check('H6/no-screen6',
                  run.var('exit', 'SCRRDY') == 0 and
                  run.var('exit', 'SCRMOD') == 0,
                  'SCRRDY %s / SCRMOD %s: exited in text mode'
                  % (run.var('exit', 'SCRRDY'), run.var('exit', 'SCRMOD'))),
        ]


class H7AboutDialog(Case):
    name = 'H7-about-dialog'
    desc = 'F1 opens About S6ED dialog, Enter closes it and restores VRAM byte-identical'
    origin = ('Fase 3a window engine: off-screen VRAM buffer at Y=512..1023 '
              'saves and restores screen background via hardware HMMM')

    def fixture(self, ctx, variant=None):
        return crlf(numbered(10))

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.snap('boot', vram=True)
        # 1. Open with F5 then A, close with RETURN
        t.press('F5')
        t.press('A')
        t.snap('dialog1', vram=True, at='WINPOLL')
        t.press('RETURN')
        t.snap('after_ret', vram=True)
        # 2. Open with F5 then A, close with SPACE
        t.press('F5')
        t.press('A')
        t.snap('dialog2', vram=True, at='WINPOLL')
        t.press('SPACE')
        t.snap('after_spc', vram=True)
        # 3. Open with F5 then A, close with ESC
        t.press('F5')
        t.press('A')
        t.snap('dialog3', vram=True, at='WINPOLL')
        t.press('ESC')
        t.snap('after_esc', vram=True)
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        v_boot = run.blob('boot', 'vram')
        v_d1 = run.blob('dialog1', 'vram')
        v_ret = run.blob('after_ret', 'vram')
        v_spc = run.blob('after_spc', 'vram')
        v_esc = run.blob('after_esc', 'vram')

        checks = []
        checks.append(Check('H7/dialog-displayed',
                            v_d1 != v_boot,
                            'VRAM modified while dialog is open'))

        hi_pixels = sum(1 for b in v_d1 for s in (0, 2, 4, 6) if ((b >> s) & 3) == 3)
        checks.append(Check('H7/color-highlight',
                            hi_pixels > 900,
                            'Color 3 (amber) highlights present (%d px)' % hi_pixels))

        cursor = [(run.var('boot', 'CURX') or 0, run.var('boot', 'CURY') or 0)]
        d_ret = vram.diff(v_boot, v_ret, ignore_cells=cursor)
        checks.append(Check('H7/restore-return', not d_ret,
                            'restored byte-for-byte on RETURN'
                            if not d_ret else
                            '%d stray pixels after RETURN' % len(d_ret)))

        d_spc = vram.diff(v_boot, v_spc, ignore_cells=cursor)
        checks.append(Check('H7/restore-space', not d_spc,
                            'restored byte-for-byte on SPACE'
                            if not d_spc else
                            '%d stray pixels after SPACE' % len(d_spc)))

        d_esc = vram.diff(v_boot, v_esc, ignore_cells=cursor)
        checks.append(Check('H7/restore-escape', not d_esc,
                            'restored byte-for-byte on ESCAPE'
                            if not d_esc else
                            '%d stray pixels after ESCAPE' % len(d_esc)))

        checks.append(Check('H7/winactv-active',
                            run.var('dialog1', 'WINACTV') == 1,
                            'WINACTV=1 while modal dialog is open'))

        checks.append(Check('H7/winactv-idle',
                            run.var('after_ret', 'WINACTV') == 0,
                            'WINACTV=0 after modal dialog is closed'))

        font = font_of(ctx)

        # Title: "About S6ED" at (118, 54) in bold (variant 1) on UI background
        bad_title = []
        for pos, ch in enumerate("About S6ED"):
            x0 = 118 + pos * vram.CELLW
            got = vram.ink_mask(v_d1, x0, 54, ground=vram.COL_UI, first_line=vram.TEXT_FIRST_LINE)
            want = vram.glyph_mask(font, ch, variant=1)
            if got != want:
                bad_title.append("char %d (%r)" % (pos, ch))
        checks.append(Check('H7/title-text', not bad_title,
                            'title "About S6ED" rendered in bold'
                            if not bad_title else
                            'title mismatches at: %s' % ', '.join(bad_title)))

        # Body: "S6ED" at (160, 68) in bold+italic (variant 3) on BG background
        bad_body = []
        for pos, ch in enumerate("S6ED"):
            x0 = 160 + pos * vram.CELLW
            got = vram.ink_mask(v_d1, x0, 68, ground=vram.COL_BG, first_line=vram.TEXT_FIRST_LINE)
            want = vram.glyph_mask(font, ch, variant=3)
            if got != want:
                bad_body.append("char %d (%r)" % (pos, ch))
        checks.append(Check('H7/body-text', not bad_body,
                            'body "S6ED" rendered in bold+italic'
                            if not bad_body else
                            'body mismatches at: %s' % ', '.join(bad_body)))

        # Button: "[  OK  ]" at (232, 138) in bold (variant 1) on UI background
        bad_btn = []
        for pos, ch in enumerate("[  OK  ]"):
            x0 = 232 + pos * vram.CELLW
            got = vram.ink_mask(v_d1, x0, 138, ground=vram.COL_UI, first_line=vram.TEXT_FIRST_LINE)
            want = vram.glyph_mask(font, ch, variant=1)
            if got != want:
                bad_btn.append("char %d (%r)" % (pos, ch))
        checks.append(Check('H7/button-text', not bad_btn,
                            'button "[  OK  ]" rendered in bold'
                            if not bad_btn else
                            'button mismatches at: %s' % ', '.join(bad_btn)))

        return checks


# --- H8-H17  S6ED.DAT CONTAINER VALIDATION (FASE C1) --------------------


class _DatCorrupt(Case):
    """A tampered S6ED.DAT must abort with the corrupt message, not a hang.

    The container served to the editor is the freshly built one with exactly
    one field broken, so each case trips the validation it names.  Header
    damage is caught by CHKDAT in text mode, before SCRINIT; descriptor and
    payload damage passes CHKDAT and is caught by DATLOAD after entering
    SCREEN 6.  Both paths end in ERRMSG -> TERM back in SCREEN 0, which is
    what the TERM.TERMDON snap verifies.
    """
    absolute = True               # never reaches MAINLOOP
    with_dat = False              # the crafted container replaces the real one
    autoexec = 'S6ED'
    cfg = None

    def dat_mutate(self, ctx, dat):
        """dat: bytearray of the built S6ED.DAT.  Break it, return bytes."""
        raise NotImplementedError

    def disk_files(self, ctx, variant=None):
        files = super().disk_files(ctx, variant)
        with open(os.path.join(ctx.code_dir, 'S6ED.DAT'), 'rb') as fh:
            dat = bytearray(fh.read())
        files['S6ED.DAT'] = bytes(self.dat_mutate(ctx, dat))
        return files

    def timeline(self, ctx, variant=None):
        t = Timeline(start=2.0)
        t.snap('exit', vram='text', at='TERM.TERMDON')
        t.t = 45.0
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        want = b'S6ED.DAT corrupt.'
        text = run.blob('exit', 'text')
        printed = text is not None and want in text
        tag = self.name.split('-')[0].upper()
        return [
            Check('%s/corrupt-printed' % tag, printed,
                  'text VRAM holds %r' % want if printed else
                  'error message %r not found in text-mode name table' % want),
            Check('%s/no-screen6' % tag,
                  run.var('exit', 'SCRRDY') == 0 and
                  run.var('exit', 'SCRMOD') == 0,
                  'SCRRDY %s / SCRMOD %s: aborted back in text mode'
                  % (run.var('exit', 'SCRRDY'), run.var('exit', 'SCRMOD'))),
        ]


class H8DatBadMagic(_DatCorrupt):
    name = 'H8-dat-bad-magic'
    desc = 'container with a bad magic ID is rejected by the header check'
    origin = 'Fase C1: the loader trusted the file layout blindly'

    def dat_mutate(self, ctx, dat):
        dat[0:4] = b'S6XX'
        return dat


class H39DatForeign(_DatCorrupt):
    name = 'H39-dat-foreign'
    desc = "S62ED's container renamed to S6ED.DAT is rejected"
    origin = ('2026-10-06: DATHCHK accepted any "S?ED" magic and S62ED shipped '
              'S6ED\'s, so S6ED would load code phased for another editor. '
              'S62ED.DAT is the sibling to test with: its header and block '
              'layout are S6ED\'s, so only the magic can tell them apart')

    def dat_mutate(self, ctx, dat):
        with open(os.path.join(ctx.code_dir, 'S62ED.DAT'), 'rb') as fh:
            return fh.read()


class H9DatBadVersion(_DatCorrupt):
    name = 'H9-dat-bad-version'
    desc = 'container with an unknown format version is rejected'
    origin = 'Fase C1: the version field must match, not just be present'

    def dat_mutate(self, ctx, dat):
        dat[4:6] = (2).to_bytes(2, 'little')
        return dat


class H10DatNoBlocks(_DatCorrupt):
    name = 'H10-dat-no-blocks'
    desc = 'container with NUMBLKS = 0 is rejected'
    origin = 'Fase C1: block count must be in [1..8]'

    def dat_mutate(self, ctx, dat):
        dat[7] = 0
        return dat


class H11DatTruncHdr(_DatCorrupt):
    name = 'H11-dat-trunc-header'
    desc = 'container truncated inside the 16-byte header is rejected'
    origin = 'Fase C1: a short header read is corruption, not an empty file'

    def dat_mutate(self, ctx, dat):
        return dat[:8]


class H12DatTruncTbl(_DatCorrupt):
    name = 'H12-dat-trunc-table'
    desc = 'container truncated inside the descriptor table is rejected'
    origin = 'Fase C1: the whole table must fit inside the file'

    def dat_mutate(self, ctx, dat):
        return dat[:20]             # header + half a descriptor


class H13DatLenZero(_DatCorrupt):
    name = 'H13-dat-len-zero'
    desc = 'block descriptor with LENGTH = 0 is rejected'
    origin = 'Fase C1: LENGTH = 0 aborts instead of a vacuous load'

    def dat_mutate(self, ctx, dat):
        dat[20:22] = (0).to_bytes(2, 'little')
        return dat


class H14DatLenOver(_DatCorrupt):
    name = 'H14-dat-len-over'
    desc = 'descriptor with LENGTH = 16385 aborts clean, page 3 untouched'
    origin = ('Fase C1 critical defect: LENGTH was only tested against zero, '
              'so a larger one wrote past #C000 into the DOS area and the stack')

    def dat_mutate(self, ctx, dat):
        # The payload really is 16,385 bytes long: only the length clamp and
        # the page-2 window bound reject this file, not the size checks.
        dat[20:22] = (16385).to_bytes(2, 'little')
        return dat + bytes(16385 - (len(dat) - 24))


class H15DatBadBlkID(_DatCorrupt):
    name = 'H15-dat-bad-blkid'
    desc = 'block descriptor with an unknown BLKID is rejected'
    origin = 'Fase C1: BLKID was ignored, any block loaded into FTRSEG'

    def dat_mutate(self, ctx, dat):
        dat[16] = 99
        return dat


class H16DatTruncPay(_DatCorrupt):
    name = 'H16-dat-trunc-payload'
    desc = 'container truncated inside the payload is rejected'
    origin = 'Fase C1: DATAOFF + LENGTH must not run past end of file'

    def dat_mutate(self, ctx, dat):
        return dat[:-10]            # the last 10 payload bytes are missing


class H17DatPadded(Case):
    name = 'H17-dat-padded-seek'
    desc = 'payload moved behind padding loads correctly via DSEEK'
    origin = ('Fase C1: the loader seeks to DATAOFF per block, so on-disk '
              'order and gaps between table and payload no longer matter')
    cfg = ("; padded container still applies the CFG\r\n"
           "PROFILE = TED\r\n"
           "WRAP = TXT\r\n"
           "TABWIDTH = 4\r\n")
    with_dat = False
    PAD = 64

    def fixture(self, ctx, variant=None):
        return crlf(numbered(5))

    def disk_files(self, ctx, variant=None):
        files = super().disk_files(ctx, variant)
        with open(os.path.join(ctx.code_dir, 'S6ED.DAT'), 'rb') as fh:
            dat = bytearray(fh.read())
        dataoff = int.from_bytes(dat[22:24], 'little')
        dat[22:24] = (dataoff + self.PAD).to_bytes(2, 'little')
        files['S6ED.DAT'] = bytes(dat[:dataoff] + bytes(self.PAD) +
                                  dat[dataoff:])
        return files

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.snap('boot')
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        return [
            Check('H17/screen6',
                  run.var('boot', 'SCRRDY') == 255 and
                  run.var('boot', 'SCRMOD') == 6,
                  'entered SCREEN 6 with a padded container'),
            Check('H17/cfg-applied',
                  run.var('boot', 'KMAPID') == 1 and
                  run.var('boot', 'WRAPMODE') == 1 and
                  run.var('boot', 'TABWIDTH') == 4,
                  'KMAPID=%s WRAPMODE=%s TABWIDTH=%s from the moved payload'
                  % (run.var('boot', 'KMAPID'),
                     run.var('boot', 'WRAPMODE'),
                     run.var('boot', 'TABWIDTH'))),
        ]


# --- H18  WINDOW ENGINE ROBUSTNESS (FASE C2) -----------------------------


class H18WindowRobustness(Case):
    name = 'H18-window-robustness'
    desc = 'Window engine robustness: pre-queued key flush, clock inhibition and WINACTV lifecycle'
    origin = ('Fase C2: KILBUF flushes stray keys on open, WINACTV inhibits clock blits '
              'during modals and restores cleanly on close')

    def fixture(self, ctx, variant=None):
        return crlf(numbered(10))

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.snap('before_modal', vram=True)
        t.press('F1')
        t.snap('modal_open', vram=True, at='WINPOLL')
        # Close with ESC
        t.press('ESC')
        t.snap('after_close', vram=True)
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        v_before = run.blob('before_modal', 'vram')
        v_modal = run.blob('modal_open', 'vram')
        v_close = run.blob('after_close', 'vram')

        checks = []
        # If KILBUF failed, the pre-queued SPACE would have dismissed the dialog immediately
        checks.append(Check('H18/key-purged',
                            v_modal != v_before and run.var('modal_open', 'WINACTV') == 1,
                            'pre-queued key purged, modal window remained active'))

        checks.append(Check('H18/winactv-idle',
                            run.var('after_close', 'WINACTV') == 0,
                            'WINACTV reset to 0 after window close'))

        # Background restored byte-for-byte
        cursor = [(run.var('before_modal', 'CURX') or 0, run.var('before_modal', 'CURY') or 0)]
        d_close = vram.diff(v_before, v_close, ignore_cells=cursor)
        checks.append(Check('H18/restore-clean', not d_close,
                            'VRAM restored cleanly after modal close'
                            if not d_close else
                            '%d stray pixels after close' % len(d_close)))
        return checks


# --- H19-H20  QUIT CONFIRMATION DIALOG (FASE 3B) -----------------------


class H19QuitDialog(Case):
    name = 'H19-quit-dialog'
    desc = ('ESC opens the Quit dialog with selectable YES/NO: NO selected by '
            'default, LEFT moves to YES, ESC cancels and Y quits to DOS')
    origin = ('Fase 3b: ACTQUIT used to jump straight to TERM; first '
              'multi-option modal dialog of the window engine')

    YESPX = (194, 122)      # YES button body sample point (clear of glyphs)
    NOPX = (264, 122)       # NO button body sample point

    def fixture(self, ctx, variant=None):
        return crlf(numbered(10))

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.snap('boot', vram=True)
        # 1. ESC opens the dialog, NO selected by default
        t.press('ESC')
        t.snap('dlg_no', vram=True, at='WINPOLL')
        # 2. LEFT moves the selection to YES
        t.press('LEFT')
        t.snap('dlg_yes', vram=True, at='WINPOLL')
        # 3. ESC cancels: dialog closes, editing resumes
        t.press('ESC')
        t.snap('after_esc', vram=True)
        # 4. ESC reopens the dialog and Y confirms: exit to DOS.  The exit
        #    breakpoint fires once, so it is armed BEFORE the key that quits.
        t.press('ESC')
        t.snap('exit', at='TERM.TERMDON')
        t.press('Y')
        t.wait(1.0)
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        v_boot = run.blob('boot', 'vram')
        v_no = run.blob('dlg_no', 'vram')
        v_yes = run.blob('dlg_yes', 'vram')
        v_esc = run.blob('after_esc', 'vram')
        fl = vram.TEXT_FIRST_LINE

        def body(buf, pt):
            if buf is None:
                return None
            return vram.pixel(buf, pt[0], pt[1], first_line=fl)

        checks = []
        checks.append(Check('H19/dialog-displayed',
                            v_no is not None and v_no != v_boot,
                            'VRAM modified while dialog is open'))

        checks.append(Check(
            'H19/default-no',
            body(v_no, self.YESPX) == vram.COL_UI and
            body(v_no, self.NOPX) == vram.COL_HI,
            'NO selected on open (YES body=%s, NO body=%s)'
            % (body(v_no, self.YESPX), body(v_no, self.NOPX))))

        checks.append(Check(
            'H19/nav-left',
            body(v_yes, self.YESPX) == vram.COL_HI and
            body(v_yes, self.NOPX) == vram.COL_UI,
            'LEFT selects YES (YES body=%s, NO body=%s)'
            % (body(v_yes, self.YESPX), body(v_yes, self.NOPX))))

        cursor = [(run.var('boot', 'CURX') or 0, run.var('boot', 'CURY') or 0)]
        d_esc = vram.diff(v_boot, v_esc, ignore_cells=cursor)
        checks.append(Check('H19/cancel-esc',
                            not d_esc and run.var('after_esc', 'WINRES') == 0,
                            'restored byte-for-byte on ESC, WINRES=0'
                            if not d_esc else
                            '%d stray pixels after ESC' % len(d_esc)))

        # Clean buffer: the warning band must stay background
        if v_no is None:
            stray = -1
        else:
            stray = sum(sum(r) for r in
                        vram.ink_mask(v_no, 162, 106, w=188, h=8,
                                      ground=vram.COL_BG, first_line=fl))
        checks.append(Check('H19/no-warning',
                            stray == 0,
                            'no unsaved-changes line on a clean buffer'
                            if stray == 0 else
                            'warning band not clean (%s)' % stray))

        checks.append(Check('H19/quit-y',
                            run.var('exit', 'SCRMOD') == 0,
                            'Y confirms and exits to DOS (Screen 0)'
                            if run.var('exit', 'SCRMOD') == 0 else
                            'SCRMOD at exit = %s' % run.var('exit', 'SCRMOD')))
        checks.append(Check('H19/winres-quit',
                            run.var('exit', 'WINRES') == 1,
                            'WINRES=1 after Y'
                            if run.var('exit', 'WINRES') == 1 else
                            'WINRES at exit = %s' % run.var('exit', 'WINRES')))
        return checks


class H20QuitDirty(Case):
    name = 'H20-quit-dirty'
    desc = 'Quit dialog shows the unsaved-changes warning when the buffer is modified'
    origin = 'Fase 3b: conditional warning line driven by MODIFIED'

    def fixture(self, ctx, variant=None):
        return crlf(numbered(10))

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.text('x')
        t.press('ESC')
        t.snap('dlg', vram=True, at='WINPOLL')
        t.press('N')
        t.snap('after_n', vram=True)
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        v_dlg = run.blob('dlg', 'vram')
        checks = []
        checks.append(Check('H20/modified',
                            run.var('dlg', 'MODIFIED') != 0,
                            'buffer marked modified after typing'
                            if run.var('dlg', 'MODIFIED') else
                            'MODIFIED is clear after typing'))

        font = font_of(ctx)
        bad = []
        for pos, ch in enumerate("Unsaved changes!"):
            x0 = 204 + pos * vram.CELLW
            got = vram.ink_mask(v_dlg, x0, 106, ground=vram.COL_BG,
                                first_line=vram.TEXT_FIRST_LINE)
            want = vram.glyph_mask(font, ch, variant=1)
            if got != want:
                bad.append("char %d (%r)" % (pos, ch))
        checks.append(Check('H20/warning-text', not bad,
                            '"Unsaved changes!" rendered in bold'
                            if not bad else
                            'warning mismatches at: %s' % ', '.join(bad)))

        checks.append(Check('H20/cancel-n',
                            run.var('after_n', 'WINRES') == 0 and
                            run.var('after_n', 'SCRMOD') == 6,
                            'N cancels, editor resumes'
                            if run.var('after_n', 'SCRMOD') == 6 else
                            'SCRMOD after N = %s' % run.var('after_n', 'SCRMOD')))
        return checks


# --- H21  WINDOW DROP SHADOW (FASE C3) ---------------------------------


class H21Shadow(Case):
    name = 'H21-window-shadow'
    desc = ('Quit dialog casts a 4 px shadow, CLR_BG by default and the colour '
            'SHADOW= names otherwise; corners show the saved background; '
            'close restores everything')
    origin = ('Fase C3: the save/show rect grew to (WINW+4)x(WINH+4) and the '
              'corner strips are copied from the saved background so the '
              'extended blit carries no stale composition data.  The SHADOW= '
              'variant is 2026-09-22: the bars were painted in CLR_BG, the '
              'document background, so on a black document the shadow was '
              'invisible and only showed by erasing the text it covered -- '
              'which is exactly what this case used to assert and nothing '
              'else.  Screen 6 has four colours on screen and all four are '
              'spoken for, so the shadow can only borrow one; the key says '
              'which, and BG (the default) is what "no shadow" looks like.')
    variants = ('bg', 'ui')

    # Quit dialog at (156,74), 200x64, shadow 4 px:
    #   right bar   x 356..359, y 78..141
    #   bottom bar  x 160..359, y 138..141
    #   corners     x 356..359 y 74..77 / x 156..159 y 138..141 (background)
    RIGHTBAR = (356, 78, 4, 64)
    BOTBAR = (160, 138, 200, 4)
    CORNERS = ([(x, y) for x in range(356, 360) for y in range(74, 78)] +
               [(x, y) for x in range(156, 160) for y in range(138, 142)])

    def fixture(self, ctx, variant=None):
        # 70-char lines leave ink under both shadow bars (80 px right,
        # 230 px bottom with the S6ED font's 'X' glyph)
        return crlf(['X' * 70] * 20)

    def config(self, ctx, variant=None):
        return self.cfg + ('SHADOW=UI\n' if variant == 'ui' else '')

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.snap('boot', vram=True)
        t.press('ESC')
        t.snap('dlg', vram=True, at='WINPOLL')
        t.press('ESC')
        t.snap('closed', vram=True)
        return t

    def verify(self, ctx, runs):
        checks = []
        for variant, run in sorted(runs.items()):
            checks += self.verify_one(variant, run)
        return checks

    def verify_one(self, variant, run):
        v_boot = run.blob('boot', 'vram')
        v_dlg = run.blob('dlg', 'vram')
        v_closed = run.blob('closed', 'vram')
        fl = vram.TEXT_FIRST_LINE
        tag = 'H21/%s' % variant

        def off(buf, rect, ground):
            """Pixels of a box that are NOT `ground`."""
            if buf is None:
                return None
            x0, y0, w, h = rect
            return sum(sum(r) for r in
                       vram.ink_mask(buf, x0, y0, w=w, h=h,
                                     ground=ground, first_line=fl))

        checks = []
        # The bars must come out solid in the colour the config asked for.
        # With BG that also means the text under them is gone, which is the
        # only thing the shadow did before SHADOW= existed.
        want = vram.COL_UI if variant == 'ui' else vram.COL_BG
        for label, rect in (('right', self.RIGHTBAR),
                            ('bottom', self.BOTBAR)):
            boot_ink = off(v_boot, rect, vram.COL_BG)
            solid = off(v_dlg, rect, want)
            checks.append(Check(
                '%s/shadow-%s' % (tag, label),
                boot_ink and solid == 0,
                '%s bar is solid colour %d over %s inked pixels'
                % (label, want, boot_ink) if boot_ink else
                'fixture left no ink under the %s bar — test proves nothing'
                % label))

        if v_boot is None or v_dlg is None:
            stray = [(-1, -1)]
        else:
            stray = [(x, y) for (x, y) in self.CORNERS
                     if vram.pixel(v_boot, x, y, fl) != vram.pixel(v_dlg, x, y, fl)]
        checks.append(Check(tag + '/corners-clean', not stray,
                            'shadow corners show the saved background'
                            if not stray else
                            '%d stale pixels in shadow corners' % len(stray)))

        cursor = [(run.var('boot', 'CURX') or 0, run.var('boot', 'CURY') or 0)]
        d = vram.diff(v_boot, v_closed, ignore_cells=cursor)
        checks.append(Check(tag + '/restore', not d,
                            'VRAM (shadow margin included) restored on close'
                            if not d else
                            '%d stray pixels after close' % len(d)))
        return checks


# --- H22  DROP-DOWN FILE MENU -----------------------------------------


class H22FileMenu(Case):
    name = 'H22-file-menu'
    desc = ('SELECT opens File dropdown menu at (48,8); DOWN/UP navigates '
            'items skipping separator; ESC/SELECT cancels and restores screen; '
            'accelerators and actions execute cleanly')
    origin = ('Dropdown menu subsystem: first top menu (File) with XOR title toggle, '
              'custom item rendering in composition buffer, and action dispatch')

    ITEM0_PX = (53, 13)    # Item 0 (New) selection bar body padding (DX=52..187, RelY=3..10 -> Y=11..18)
    ITEM1_PX = (53, 21)    # Item 1 (Open) bar body padding (RelY=11..18 -> Y=19..26)
    SEP_PX = (53, 45)      # Separator line body (RelY=37 -> Y=45)

    def fixture(self, ctx, variant=None):
        return crlf(numbered(10))

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.snap('boot', vram=True)
        t.snap('boot_r0', vram='menu')

        # 1. SELECT opens the File dropdown menu
        t.press('SELECT')
        t.snap('menu_open', vram=True, at='WINPOLL')
        t.snap('menu_r0', vram='menu', at='WINPOLL')

        # 2. DOWN navigates: 0 -> 1 -> 2 -> 3 -> 5 (skips separator 4!)
        t.press('DOWN')
        t.snap('item1', at='WINPOLL')
        t.press('DOWN')
        t.press('DOWN')
        t.snap('item3', at='WINPOLL')
        t.press('DOWN')
        t.snap('item5', at='WINPOLL')

        # 3. UP navigates backwards: 5 -> 3 (skips separator 4!)
        t.press('UP')
        t.snap('item3_up', at='WINPOLL')

        # 4. ESC cancels: menu closes, row 0 restored, editing resumes
        t.press('ESC')
        t.snap('after_esc', vram=True)
        t.snap('after_esc_r0', vram='menu')

        # 5. Reopen with SELECT and cancel with SELECT
        t.press('SELECT')
        t.snap('menu_reopen', at='WINPOLL')
        t.press('SELECT')
        t.snap('after_sel_cancel', vram=True)

        # 6. Reopen with F1 and cancel with ESC
        t.press('F1')
        t.snap('menu_f1', at='WINPOLL')
        t.press('ESC')
        t.snap('after_f1_cancel', vram=True)

        # 7. Reopen with SELECT and trigger New via 'N' accelerator
        t.text('EDITED')
        t.snap('before_new')
        t.press('SELECT')
        t.snap('menu_for_n', at='WINPOLL')
        t.press('N')
        # The document is dirty, so New asks first (F0); YES discards it.
        t.snap('ask_new', at='WINPOLL')
        t.press('Y')
        t.snap('after_new')
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        v_boot = run.blob('boot', 'vram')
        v_open = run.blob('menu_open', 'vram')
        v_esc = run.blob('after_esc', 'vram')
        v_sel_esc = run.blob('after_sel_cancel', 'vram')
        fl = vram.TEXT_FIRST_LINE

        r0_boot = run.blob('boot_r0', 'menu')
        r0_open = run.blob('menu_r0', 'menu')
        r0_esc = run.blob('after_esc_r0', 'menu')

        def body(buf, pt):
            if buf is None:
                return None
            return vram.pixel(buf, pt[0], pt[1], first_line=fl)

        checks = []

        # 1. Menu displayed and vars initialized
        checks.append(Check('H22/menu-displayed',
                            v_open is not None and v_open != v_boot,
                            'VRAM modified while menu is open'))

        checks.append(Check(
            'H22/default-new',
            run.var('menu_open', 'WINACTV') == 1 and
            run.var('menu_open', 'MNUID') == 0 and
            run.var('menu_open', 'MNUSEL') == 0,
            'File menu open (WINACTV=%s, MNUID=%s, MNUSEL=%s)'
            % (run.var('menu_open', 'WINACTV'),
               run.var('menu_open', 'MNUID'),
               run.var('menu_open', 'MNUSEL'))))

        # 2. Row 0 title "File" XOR inversion
        if r0_boot is not None and r0_open is not None:
            xor_ok = True
            for y in range(8):
                for x in range(48, 72):
                    p_boot = vram.pixel(r0_boot, x, y, first_line=0)
                    p_open = vram.pixel(r0_open, x, y, first_line=0)
                    if p_open != (p_boot ^ 1):
                        xor_ok = False
                        break
                if not xor_ok:
                    break
        else:
            xor_ok = False
        checks.append(Check('H22/title-xor', xor_ok,
                            'row 0 "File" title inverted with XOR (48..71, 0..7)'
                            if xor_ok else
                            'title XOR mismatch in row 0'))

        # 3. Item styles in composition/display
        item_styles_ok = (body(v_open, self.ITEM0_PX) == vram.COL_UI and
                          body(v_open, self.ITEM1_PX) == vram.COL_BG and
                          body(v_open, self.SEP_PX) == vram.COL_UI)
        checks.append(Check(
            'H22/item-styles',
            item_styles_ok,
            'item 0 highlighted, item 1 unselected, separator present'
            if item_styles_ok else
            'item styles mismatch: item0=%s, item1=%s, sep=%s'
            % (body(v_open, self.ITEM0_PX),
               body(v_open, self.ITEM1_PX),
               body(v_open, self.SEP_PX))))

        # 4. Navigation
        checks.append(Check(
            'H22/nav-down',
            run.var('item1', 'MNUSEL') == 1 and
            run.var('item3', 'MNUSEL') == 3,
            'DOWN advances selection 0 -> 1 -> 3 (item1=%s, item3=%s)'
            % (run.var('item1', 'MNUSEL'), run.var('item3', 'MNUSEL'))))

        checks.append(Check(
            'H22/nav-skip-sep',
            run.var('item5', 'MNUSEL') == 5 and
            run.var('item3_up', 'MNUSEL') == 3,
            'DOWN skips separator to 5, UP skips separator to 3 (item5=%s, item3_up=%s)'
            % (run.var('item5', 'MNUSEL'), run.var('item3_up', 'MNUSEL'))))

        # 5. Cancellation via ESC
        cursor = [(run.var('boot', 'CURX') or 0, run.var('boot', 'CURY') or 0)]
        d_esc = vram.diff(v_boot, v_esc, ignore_cells=cursor)
        r0_match = True
        if r0_boot and r0_esc:
            for y in range(8):
                for x in range(48, 72):
                    if vram.pixel(r0_esc, x, y, first_line=0) != vram.pixel(r0_boot, x, y, first_line=0):
                        r0_match = False
                        break
                if not r0_match:
                    break
        else:
            r0_match = False
        checks.append(Check(
            'H22/cancel-esc',
            not d_esc and r0_match and run.var('after_esc', 'WINACTV') == 0,
            'ESC cleanly restores text VRAM and row 0 title, WINACTV=0'
            if not d_esc and r0_match and run.var('after_esc', 'WINACTV') == 0 else
            'restore failed: %d text diffs, title match=%s, WINACTV=%s'
            % (len(d_esc), r0_match, run.var('after_esc', 'WINACTV'))))

        # 6. Cancellation via SELECT
        d_sel = vram.diff(v_boot, v_sel_esc, ignore_cells=cursor)
        checks.append(Check(
            'H22/cancel-select',
            not d_sel and run.var('after_sel_cancel', 'WINACTV') == 0,
            'SELECT key toggles/cancels cleanly, WINACTV=0'
            if not d_sel and run.var('after_sel_cancel', 'WINACTV') == 0 else
            'cancel select failed: %d diffs, WINACTV=%s'
            % (len(d_sel), run.var('after_sel_cancel', 'WINACTV'))))

        # 7. Open with F1 key
        checks.append(Check(
            'H22/f1-open',
            run.var('menu_f1', 'WINACTV') == 1 and
            run.var('menu_f1', 'MNUID') == 0 and
            run.var('after_f1_cancel', 'WINACTV') == 0,
            'F1 key opens File menu and ESC cancels cleanly'
            if (run.var('menu_f1', 'WINACTV') == 1 and
                run.var('menu_f1', 'MNUID') == 0 and
                run.var('after_f1_cancel', 'WINACTV') == 0) else
            'F1 open failed: WINACTV=%s, MNUID=%s, after_cancel=%s'
            % (run.var('menu_f1', 'WINACTV'),
               run.var('menu_f1', 'MNUID'),
               run.var('after_f1_cancel', 'WINACTV'))))

        # 8. Action New via 'N' accelerator
        checks.append(Check(
            'H22/action-new',
            run.var('before_new', 'MODIFIED') == 0xFF and
            run.var('ask_new', 'WINACTV') == 1 and
            run.var('after_new', 'MODIFIED') == 0 and
            run.var('after_new', 'TOTLINES') == 1,
            'N accelerator executes New action (MODIFIED %s -> %s, TOTLINES %s)'
            % (run.var('before_new', 'MODIFIED'),
               run.var('after_new', 'MODIFIED'),
               run.var('after_new', 'TOTLINES'))))

        return checks


# --- H23  MENU HORIZONTAL NAVIGATION & FKEYS ---------------------------


class H23MenuNav(Case):
    name = 'H23-menu-nav'
    desc = ('Horizontal menu navigation across all 3 menus (RIGHT/LEFT wrapping), '
            'direct function key jumps (F1..F3), item navigation with separator '
            'skipping in Edit menu, and clean screen/title restoration on cancel')
    origin = ('3-menu horizontal navigation engine with table-driven dimensions, '
              'dynamic background save/restore, and title XOR highlighting')

    def fixture(self, ctx, variant=None):
        return crlf(numbered(10))

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.snap('boot', vram=True)
        t.snap('boot_r0', vram='menu')

        # 1. F1 opens File menu (MNUID=0)
        t.press('F1')
        t.snap('open_file', at='WINPOLL')

        # 2. RIGHT navigates across all menus:
        # File (0) -> Edit (1) -> Help (2) -> wrap File (0)
        t.press('RIGHT')
        t.snap('nav_edit', vram='menu', at='WINPOLL')
        t.press('RIGHT')
        t.snap('nav_help', at='WINPOLL')
        t.press('RIGHT')
        t.snap('nav_wrap_file', at='WINPOLL')

        # 3. LEFT wraps backwards:
        # File (0) -> wrap Help (2) -> Edit (1)
        t.press('LEFT')
        t.snap('nav_wrap_help', at='WINPOLL')
        t.press('LEFT')
        t.snap('nav_left_edit', at='WINPOLL')

        # 4. Direct function keys jump across menus:
        t.press('F2')
        t.snap('f2_jump_edit', at='WINPOLL')
        t.press('F3')
        t.snap('f3_jump_help', at='WINPOLL')
        t.press('F1')
        t.snap('f1_jump_file', at='WINPOLL')

        # 5. Navigate into Edit menu items and test separator skipping:
        # Items in Edit: 0:Cut, 1:Copy, 2:Paste, 3:Del Line, 4:Sep, 5:Select All, 6:Clear Sel
        t.press('F2')
        t.snap('edit_menu', at='WINPOLL')
        t.press('DOWN')
        t.snap('edit_item1', at='WINPOLL')
        t.press('DOWN')
        t.press('DOWN')
        t.snap('edit_item3', at='WINPOLL')
        t.press('DOWN')
        t.snap('edit_item5', at='WINPOLL')
        t.press('UP')
        t.snap('edit_item3_up', at='WINPOLL')

        # 6. Action Settings modal via Help menu (Item 0)
        t.press('F3')
        t.snap('help_menu_sett', at='WINPOLL')
        t.press('RETURN')
        t.snap('after_sett_open', at='WINPOLL')
        t.press('ESC')
        t.snap('after_sett_close')

        # 6b. An EDIT menu action.  Nothing had ever pressed one, which is how
        # five of the six shipped calling the action ID instead of the routine
        # (ACCUT is EQU 46, so CALL ACCUT was CALL #002E, into the DOS zero
        # page).  Select All is the cheapest of them to observe.
        t.wait(1.0)
        t.press('F2')
        t.wait(1.0)
        t.press('A')
        t.snap('after_selall')
        # Drop the selection again: step 7 compares the screen against boot,
        # and an inverted document is an honest difference.
        t.wait(1.0)
        t.press('LEFT')

        # 7. Open File menu and ESC cancels cleanly
        t.wait(1.0)
        t.press('F1')
        t.press('ESC')
        t.snap('after_cancel', vram=True)
        t.snap('after_cancel_r0', vram='menu')
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        v_boot = run.blob('boot', 'vram')
        v_cancel = run.blob('after_cancel', 'vram')
        r0_boot = run.blob('boot_r0', 'menu')
        r0_edit = run.blob('nav_edit', 'menu')
        r0_cancel = run.blob('after_cancel_r0', 'menu')

        checks = []

        # 1. F1 opens File menu
        checks.append(Check(
            'H23/f1-open',
            run.var('open_file', 'WINACTV') == 1 and
            run.var('open_file', 'MNUID') == 0 and
            run.var('open_file', 'MNUSEL') == 0,
            'F1 opens File menu (WINACTV=%s, MNUID=%s, MNUSEL=%s)'
            % (run.var('open_file', 'WINACTV'),
               run.var('open_file', 'MNUID'),
               run.var('open_file', 'MNUSEL'))))

        # 2. Horizontal RIGHT navigation + wrap
        right_ok = (
            run.var('nav_edit', 'WINACTV') == 1 and run.var('nav_edit', 'MNUID') == 1 and
            run.var('nav_help', 'WINACTV') == 1 and run.var('nav_help', 'MNUID') == 2 and
            run.var('nav_wrap_file', 'WINACTV') == 1 and run.var('nav_wrap_file', 'MNUID') == 0
        )
        checks.append(Check(
            'H23/nav-right-wrap',
            right_ok,
            'RIGHT cycles 0->1->2->0 (Edit=%s, Help=%s, WrapFile=%s)'
            % (run.var('nav_edit', 'MNUID'),
               run.var('nav_help', 'MNUID'),
               run.var('nav_wrap_file', 'MNUID'))))

        # 3. Row 0 title highlighting on switch
        xor_title_ok = True
        if r0_boot is not None and r0_edit is not None:
            for y in range(8):
                # File title restored
                for x in range(48, 72):
                    if vram.pixel(r0_edit, x, y, first_line=0) != vram.pixel(r0_boot, x, y, first_line=0):
                        xor_title_ok = False
                        break
                # Edit title inverted
                for x in range(84, 108):
                    if vram.pixel(r0_edit, x, y, first_line=0) != (vram.pixel(r0_boot, x, y, first_line=0) ^ 1):
                        xor_title_ok = False
                        break
                if not xor_title_ok:
                    break
        else:
            xor_title_ok = False
        checks.append(Check(
            'H23/title-switch-xor',
            xor_title_ok,
            'Switching to Edit menu restores File title and inverts Edit title (84..107)'
            if xor_title_ok else 'Title switch XOR mismatch'))

        # 4. Horizontal LEFT navigation + wrap
        left_ok = (
            run.var('nav_wrap_help', 'WINACTV') == 1 and run.var('nav_wrap_help', 'MNUID') == 2 and
            run.var('nav_left_edit', 'WINACTV') == 1 and run.var('nav_left_edit', 'MNUID') == 1
        )
        checks.append(Check(
            'H23/nav-left-wrap',
            left_ok,
            'LEFT wraps 0->2->1 (WrapHelp=%s, Edit=%s)'
            % (run.var('nav_wrap_help', 'MNUID'),
               run.var('nav_left_edit', 'MNUID'))))

        # 5. Direct F1..F3 key jumps
        fkeys_ok = (
            run.var('f2_jump_edit', 'MNUID') == 1 and
            run.var('f3_jump_help', 'MNUID') == 2 and
            run.var('f1_jump_file', 'MNUID') == 0
        )
        checks.append(Check(
            'H23/direct-fkeys',
            fkeys_ok,
            'F1..F3 keys jump directly to corresponding menus (F2=%s, F3=%s, F1=%s)'
            % (run.var('f2_jump_edit', 'MNUID'),
               run.var('f3_jump_help', 'MNUID'),
               run.var('f1_jump_file', 'MNUID'))))

        # 6. Item navigation and separator skip in Edit menu
        edit_nav_ok = (
            run.var('edit_item1', 'MNUSEL') == 1 and
            run.var('edit_item3', 'MNUSEL') == 3 and
            run.var('edit_item5', 'MNUSEL') == 5 and
            run.var('edit_item3_up', 'MNUSEL') == 3
        )
        checks.append(Check(
            'H23/edit-skip-sep',
            edit_nav_ok,
            'DOWN advances 1->3, skips separator to 5; UP skips back to 3 (item1=%s, item3=%s, item5=%s, item3_up=%s)'
            % (run.var('edit_item1', 'MNUSEL'),
               run.var('edit_item3', 'MNUSEL'),
               run.var('edit_item5', 'MNUSEL'),
               run.var('edit_item3_up', 'MNUSEL'))))

        # 7. Action Settings modal dialog execution via Help menu (Item 0)
        sett_ok = (
            run.var('help_menu_sett', 'MNUID') == 2 and
            run.var('help_menu_sett', 'MNUSEL') == 0 and
            run.var('after_sett_open', 'WINACTV') == 1 and
            run.var('after_sett_open', 'WINX') == 120 and
            run.var('after_sett_open', 'WINW') == 272 and
            run.var('after_sett_open', 'SETTFOC') == 0 and
            run.var('after_sett_close', 'WINACTV') == 0
        )
        checks.append(Check(
            'H23/action-settings',
            sett_ok,
            'Help item 0 opens Settings dialog and ESC closes it'
            if sett_ok else
            'Settings dialog failed: MNUID=%s, MNUSEL=%s, open=%s, WINX=%s, WINW=%s, SETTFOC=%s, close=%s'
            % (run.var('help_menu_sett', 'MNUID'),
               run.var('help_menu_sett', 'MNUSEL'),
               run.var('after_sett_open', 'WINACTV'),
               run.var('after_sett_open', 'WINX'),
               run.var('after_sett_open', 'WINW'),
               run.var('after_sett_open', 'SETTFOC'),
               run.var('after_sett_close', 'WINACTV'))))

        # 7b. An EDIT menu action
        checks.append(Check(
            'H23/edit-action',
            run.var('after_selall', 'SELACT') == 1,
            'Edit > Select All reaches the routine and not the action ID '
            '(SELACT=%s)' % run.var('after_selall', 'SELACT')))

        # 8. Clean cancellation and restoration
        cursor = [(run.var('boot', 'CURX') or 0, run.var('boot', 'CURY') or 0)]
        d_cancel = vram.diff(v_boot, v_cancel, ignore_cells=cursor)
        r0_clean = True
        if r0_boot and r0_cancel:
            for y in range(8):
                for x in range(256):
                    if vram.pixel(r0_cancel, x, y, first_line=0) != vram.pixel(r0_boot, x, y, first_line=0):
                        r0_clean = False
                        break
                if not r0_clean:
                    break
        else:
            r0_clean = False
        checks.append(Check(
            'H23/cancel-clean',
            not d_cancel and r0_clean and run.var('after_cancel', 'WINACTV') == 0,
            'ESC cleanly closes menu and restores entire text area and row 0 chrome'
            if (not d_cancel and r0_clean and run.var('after_cancel', 'WINACTV') == 0) else
            'cancel restore failed: %d text diffs, r0_clean=%s, WINACTV=%s'
            % (len(d_cancel), r0_clean, run.var('after_cancel', 'WINACTV'))))

        return checks


# --- B2  EXTERNAL FONT ASSET IN VRAM ----------------------------------


class B2Font(Case):
    name = 'B2-font'
    desc = 'the four VRAM font tables match the expansion of RES/FONTS.BIN'
    origin = ('VRAM font map moved to #8000/#A000/#C000/#E000 and font loaded '
              'from S6ED.FNT: 16,384 bytes across all 32 scanline rows of 4 variants')

    def fixture(self, ctx, variant=None):
        return crlf(numbered(5))

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.snap('boot', vram='font')
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        font_res = font_of(ctx)
        buf = run.blob('boot', 'font')
        checks = [
            Check('B2/fntok', run.var('boot', 'FNTOK') == 0xFF,
                  'FNTOK = %s (expected 0xFF)' % run.var('boot', 'FNTOK')),
            Check('B2/rom-not-used', run.var('boot', 'FNTROMD') == 0,
                  'FNTROMD = %s (expected 0)' % run.var('boot', 'FNTROMD')),
        ]
        if buf is None or len(buf) < 32768:
            checks.append(Check('B2/font-dump', False, 'no 32KB font VRAM dump'))
            return checks

        mismatches = []
        for var in range(4):
            for row in range(8):
                for line in range(8):
                    line_idx = (var * 8 + row) * 8 + line
                    off = line_idx * 128
                    got = buf[off:off + 64]
                    want = vram.expected_font_line(font_res, var, row, line)
                    if got != want:
                        mismatches.append('var %d row %d line %d (line %d)'
                                          % (var, row, line, line_idx))

        checks.append(Check('B2/vram-tables', not mismatches,
                            '16,384 font bytes verified, 0 mismatches'
                            if not mismatches else
                            '%d line mismatches: first at %s'
                            % (len(mismatches), mismatches[0])))
        return checks


# --- B3  FALLBACK TO BIOS ROM CHARSET ---------------------------------


class B3Rom(Case):
    name = 'B3-rom'
    desc = 'fallback to MSX BIOS ROM charset when S6ED.FNT is missing'
    origin = ('no S6ED.FNT or wrong size: ROM charset feeds all four tables and '
              '[ROM] is shown in the status bar')
    with_font = False                   # Omit S6ED.FNT from fixture disk

    def fixture(self, ctx, variant=None):
        return crlf(numbered(5))

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.snap('boot', vram='font')
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        buf = run.blob('boot', 'font')
        stat_raw = run.snaps.get('boot', {}).get('STATBUF', [])
        stat_str = ''.join(chr(c) for c in stat_raw) if stat_raw else ''
        checks = [
            Check('B3/fntok-zero', run.var('boot', 'FNTOK') == 0,
                  'FNTOK = %s (expected 0)' % run.var('boot', 'FNTOK')),
            Check('B3/rom-staged', run.var('boot', 'FNTROMD') == 0xFF,
                  'FNTROMD = %s (expected 0xFF)' % run.var('boot', 'FNTROMD')),
            Check('B3/status-bar-rom', '[ROM]' in stat_str,
                  '[ROM] shown in status bar' if '[ROM]' in stat_str else
                  'status: %r' % stat_str[:40]),
        ]
        if buf is None or len(buf) < 32768:
            checks.append(Check('B3/font-dump', False, 'no font VRAM dump'))
            return checks

        # All four tables in VRAM must be identical to table 0 (Normal)
        diff_tables = []
        tbl0 = [buf[l * 128:l * 128 + 64] for l in range(64)]
        for var in range(1, 4):
            tbl = [buf[(var * 64 + l) * 128:(var * 64 + l) * 128 + 64]
                   for l in range(64)]
            if tbl != tbl0:
                diff_tables.append('variant %d differs from normal' % var)

        checks.append(Check('B3/tables-identical', not diff_tables,
                            'all 4 tables identical to ROM normal face'
                            if not diff_tables else '; '.join(diff_tables)))
        non_zero = sum(1 for line in tbl0 for b in line if b != 0)
        checks.append(Check('B3/glyphs-present', non_zero > 1000,
                            '%d non-zero bytes in ROM font table' % non_zero))
        return checks


# --- F1  VERTICAL SCROLL LIMITS & RENDER PURITY -----------------------


class F1Scroll(Case):
    name = 'F1-scroll'
    desc = 'vertical scroll up/down across bounds and render purity'
    origin = ('YMMM scroll blit and bounds: rows move cleanly, stops at top/bottom '
              'and matches full REDRAW')
    LINES = 60

    def fixture(self, ctx, variant=None):
        return crlf(numbered(self.LINES))

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.snap('boot', vram=True)
        t.press('DOWN', repeat=23)        # row 23
        t.press('DOWN', repeat=10)        # scroll down 10
        t.snap('scrolled_down', vram=True)
        t.press('UP', repeat=23)          # row 0
        t.press('UP', repeat=10)          # scroll up 10
        t.snap('scrolled_up', vram=True)
        t.press('UP', repeat=5)           # top bound
        t.snap('top_limit', vram=True)
        t.press('DOWN', mods=['GRAPH'])   # PgDn
        t.press('UP', mods=['GRAPH'])     # PgUp -> clean REDRAW
        t.snap('redrawn', vram=True)
        t.press('DOWN', repeat=65)        # bottom bound
        t.snap('bottom_limit', vram=True)
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        checks = [
            Check('F1/scrolled-down-topline',
                  run.var('scrolled_down', 'TOPLINE') == 10,
                  'TOPLINE = %s after 10 scroll downs (expected 10)'
                  % run.var('scrolled_down', 'TOPLINE')),
            Check('F1/scrolled-down-docline',
                  run.var('scrolled_down', 'DOCLINE') == 33,
                  'DOCLINE = %s (expected 33)'
                  % run.var('scrolled_down', 'DOCLINE')),
            Check('F1/scrolled-up-topline',
                  run.var('scrolled_up', 'TOPLINE') == 0,
                  'TOPLINE = %s after 10 scroll ups (expected 0)'
                  % run.var('scrolled_up', 'TOPLINE')),
            Check('F1/top-limit',
                  run.var('top_limit', 'TOPLINE') == 0 and
                  run.var('top_limit', 'DOCLINE') == 0,
                  'TOPLINE %s / DOCLINE %s at top bound'
                  % (run.var('top_limit', 'TOPLINE'),
                     run.var('top_limit', 'DOCLINE'))),
            Check('F1/bottom-limit-docline',
                  run.var('bottom_limit', 'DOCLINE') == self.LINES - 1,
                  'DOCLINE = %s at bottom bound (expected %d)'
                  % (run.var('bottom_limit', 'DOCLINE'), self.LINES - 1)),
            Check('F1/bottom-limit-topline',
                  run.var('bottom_limit', 'TOPLINE') == self.LINES - 24,
                  'TOPLINE = %s at bottom bound (expected %d)'
                  % (run.var('bottom_limit', 'TOPLINE'), self.LINES - 24)),
        ]
        cursor = [(run.var('top_limit', 'CURX') or 0,
                   run.var('top_limit', 'CURY') or 0),
                  (run.var('redrawn', 'CURX') or 0,
                   run.var('redrawn', 'CURY') or 0)]
        d = vram.diff(run.blob('top_limit', 'vram'),
                      run.blob('redrawn', 'vram'), ignore_cells=cursor)
        checks.append(Check('F1/render-pure', not d,
                            'scrolled screen identical to full REDRAW'
                            if not d else
                            '%d differing pixels, first at (%d,%d)'
                            % (len(d), d[0][0], d[0][1])))
        return checks


# --- F2  KEY REPEAT COALESCING VIA KEYRUN -----------------------------


class F2Keyrun(Case):
    name = 'F2-keyrun'
    desc = 'held cursor key collapses queued repeats into one multi-row blit'
    origin = ('KEYRUN drains BIOS keyboard buffer repeats: held DOWN key moves '
              'by multiple rows in one YMMM blit rather than queuing separate moves')
    LINES = 60

    def fixture(self, ctx, variant=None):
        return crlf(numbered(self.LINES))

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.snap('boot')
        t.press('DOWN', repeat=23)        # reach bottom of viewport (CURY=23)
        t.snap('at_bottom')
        # Hold DOWN key (Row 8, Bit 6 = 0x40) for 1.2s: BIOS queues multiple DOWNs
        t.at('keymatrixdown 8 0x40')
        t.t += 1.2
        t.at('keymatrixup 8 0x40')
        t.t += 0.5
        t.snap('burst', vram=True)
        # Ctrl+UP returns to top with clean REDRAW
        t.press('UP', mods=['CTRL'])
        t.snap('top', vram=True)
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        top = run.var('burst', 'TOPLINE') or 0
        doc = run.var('burst', 'DOCLINE') or 0
        cury = run.var('burst', 'CURY') or 0
        checks = [
            Check('F2/burst-collapsed', top >= 4,
                  'TOPLINE jumped to %s (expected >= 4 rows in single burst)' % top),
            Check('F2/docline-advanced', doc == 23 + top,
                  'DOCLINE %s matches 23 + TOPLINE (%d)' % (doc, 23 + top)),
            Check('F2/cury-clamped', cury == 23,
                  'CURY clamped at 23 (got %s)' % cury),
            Check('F2/return-top',
                  run.var('top', 'TOPLINE') == 0 and run.var('top', 'DOCLINE') == 0,
                  'TOPLINE %s / DOCLINE %s after Ctrl+UP'
                  % (run.var('top', 'TOPLINE'), run.var('top', 'DOCLINE'))),
        ]
        font = font_of(ctx)
        lines = vram.render_text(run.blob('burst', 'vram'), font=font)
        if lines:
            expected = numbered(self.LINES)[top:top + 24]
            mismatch = next((i for i in range(min(len(lines), len(expected)))
                             if lines[i] != expected[i]), None)
            checks.append(Check('F2/viewport-text', mismatch is None,
                                'all 24 rows match document lines %d..%d'
                                % (top + 1, top + 24) if mismatch is None else
                                'row %d mismatch: got %r, want %r'
                                % (mismatch, lines[mismatch], expected[mismatch])))
        else:
            checks.append(Check('F2/viewport-text', False, 'no OCR output'))
        return checks


# --- D1  INSERTION AT START, MIDDLE AND BOUNDARY -----------------------


class D1Insert(Case):
    name = 'D1-insert'
    desc = 'insertion at start (col 0), mid-line, and col 79 boundary'
    origin = ('EDINSCHR shifts tail text/attributes right and updates line length: '
              'typing at col 0, middle and column 79 boundary retains all characters')

    def fixture(self, ctx, variant=None):
        return crlf(['12345678'])

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.text('A')                       # col 0 -> 'A12345678'
        t.press('RIGHT', repeat=4)        # cursor at col 5 (between '4' and '5')
        t.text('B')                       # -> 'A1234B5678' (len 10)
        t.press('RIGHT', mods=['CTRL'])   # EOL (col 10)
        t.text('C' * 69)                  # len 79, curx 79
        t.text('D')                       # col 79 -> len 80, curx 80
        t.press('S', mods=['CTRL'])
        t.wait(3.0)
        t.snap('saved')
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        got = run.session.extract(run.dsk, 'DOC.TXT')
        want_line = 'A1234B5678' + ('C' * 69) + 'D'
        want = crlf([want_line])
        first_line = got.split(b'\r\n')[0] if got else b''
        checks = [
            Check('D1/content', got == want,
                  'document matches byte for byte' if got == want else
                  'got %r' % (got[:60] if got else None)),
            Check('D1/length', len(first_line) == 80,
                  'line length 80' if len(first_line) == 80 else
                  'line length %d' % len(first_line)),
            Check('D1/curx', run.var('saved', 'CURX') == 80,
                  'CURX = %s (expected 80)' % run.var('saved', 'CURX')),
        ]
        return checks


# --- D2  ENTER LINE SPLITTING -----------------------------------------


class D2Enter(Case):
    name = 'D2-enter'
    desc = 'line splitting on Enter at start, middle, and EOL'
    origin = ('EDNWLIN splits line into head/tail records and updates line directory: '
              'Enter at col 0, mid-line and EOL produces exact multiline split')

    def fixture(self, ctx, variant=None):
        return crlf(['HEADTAIL'])

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.press('RETURN')                 # Enter at col 0 -> line 0 '', line 1 'HEADTAIL'
        t.press('RIGHT', repeat=4)        # col 4 (between HEAD and TAIL)
        t.press('RETURN')                 # -> line 1 'HEAD', line 2 'TAIL'
        t.press('RIGHT', mods=['CTRL'])   # col 4 of 'TAIL'
        t.press('RETURN')                 # -> line 3 ''
        t.press('RETURN')                 # -> line 4 ''
        t.press('S', mods=['CTRL'])
        t.wait(3.0)
        t.snap('saved')
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        got = run.session.extract(run.dsk, 'DOC.TXT')
        want = crlf(['', 'HEAD', 'TAIL', '', ''])
        checks = [
            Check('D2/content', got == want,
                  'document matches byte for byte' if got == want else
                  'got %r' % (got if got else None)),
            Check('D2/totlines', run.var('saved', 'TOTLINES') == 5,
                  'TOTLINES = %s (expected 5)' % run.var('saved', 'TOTLINES')),
        ]
        return checks


# --- D3  BACKSPACE AND LINE JOIN --------------------------------------


class D3Backspace(Case):
    name = 'D3-backspace'
    desc = 'backspace in mid-line, at col 0 line join (WRAP_DEV), and doc start'
    origin = ('EDDELBK in-line deletion and EDJNDEV joining current line into previous line')

    def fixture(self, ctx, variant=None):
        return crlf(['AAA', 'BBB', 'CCC'])

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.press('BS')                     # line 0, col 0: no-op
        t.press('RIGHT', repeat=2)        # col 2 (after 'AA')
        t.press('BS')                     # line 0 becomes 'AA', cursor at col 1
        t.press('DOWN')
        t.press('LEFT', mods=['CTRL'])    # line 1, col 0
        t.press('BS')                     # joins line 1 ('BBB') into line 0 -> 'AABBB'
        t.press('S', mods=['CTRL'])
        t.wait(3.0)
        t.snap('saved')
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        got = run.session.extract(run.dsk, 'DOC.TXT')
        want = crlf(['AABBB', 'CCC'])
        checks = [
            Check('D3/content', got == want,
                  'document matches byte for byte' if got == want else
                  'got %r' % (got if got else None)),
            Check('D3/totlines', run.var('saved', 'TOTLINES') == 2,
                  'TOTLINES = %s (expected 2)' % run.var('saved', 'TOTLINES')),
            Check('D3/curx', run.var('saved', 'CURX') == 2,
                  'CURX = %s at seam (expected 2)' % run.var('saved', 'CURX')),
        ]
        return checks


# --- D4  DELETE AND LINE PULL -----------------------------------------


class D4Delete(Case):
    name = 'D4-delete'
    desc = 'delete in mid-line, at EOL line pull (WRAP_DEV), and EOF'
    origin = ('EDDELCHR in-line deletion and EDDELDV pulling next line up at EOL')

    def fixture(self, ctx, variant=None):
        return crlf(['123', '456', '789'])

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.press('RIGHT')                  # col 1 (on '2')
        t.press('DEL')                    # line 0 becomes '13', cursor on '3'
        t.press('RIGHT', mods=['CTRL'])   # col 2 (EOL after '3')
        t.press('DEL')                    # pulls line 1 ('456') into line 0 -> '13456'
        t.press('DOWN')
        t.press('RIGHT', mods=['CTRL'])   # line 1 ('789'), col 3 (EOF)
        t.press('DEL')                    # EOF: no-op
        t.press('S', mods=['CTRL'])
        t.wait(3.0)
        t.snap('saved')
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        got = run.session.extract(run.dsk, 'DOC.TXT')
        want = crlf(['13456', '789'])
        checks = [
            Check('D4/content', got == want,
                  'document matches byte for byte' if got == want else
                  'got %r' % (got if got else None)),
            Check('D4/totlines', run.var('saved', 'TOTLINES') == 2,
                  'TOTLINES = %s (expected 2)' % run.var('saved', 'TOTLINES')),
        ]
        return checks


# --- D5  WORD DELETE LEFT AND WHOLE LINE DELETE -----------------------


class D5WordLineDel(Case):
    name = 'D5-wordline-del'
    desc = 'word delete left (GRAPH+BS) and whole line delete (Ctrl+Y)'
    origin = ('ACTDWLFT deletes backward word/spaces and ACTDLS recycles line record')

    def fixture(self, ctx, variant=None):
        return crlf(['ALPHA BETA GAMMA', 'DELETE ME', 'DELTA EPSILON'])

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.press('RIGHT', repeat=10)       # after 'BETA' (col 10)
        t.press('BS', mods=['GRAPH'])     # deletes 'BETA' -> 'ALPHA GAMMA'
        t.press('DOWN')                   # line 1 ('DELETE ME')
        t.press('Y', mods=['CTRL'])       # deletes line 1
        t.press('S', mods=['CTRL'])
        t.wait(3.0)
        t.snap('saved')
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        got = run.session.extract(run.dsk, 'DOC.TXT')
        want = crlf(['ALPHA  GAMMA', 'DELTA EPSILON'])
        checks = [
            Check('D5/content', got == want,
                  'document matches byte for byte' if got == want else
                  'got %r' % (got if got else None)),
            Check('D5/totlines', run.var('saved', 'TOTLINES') == 2,
                  'TOTLINES = %s (expected 2)' % run.var('saved', 'TOTLINES')),
        ]
        return checks


# --- D6  CASCADE PARAGRAPH REFLOW (WRAP_TXT) --------------------------


class D6Reflow(Case):
    name = 'D6-reflow'
    desc = 'cascade paragraph reflow across lines in WRAP_TXT mode'
    origin = ('REFLOW pulls complete words upwards to fill up to 80 columns, '
              'deleting consumed intermediate lines, stopping at empty line boundary')
    cfg = ("; WRAP_TXT configuration\r\n"
           "WRAP = TXT\r\n"
           "PROFILE = STD\r\n")

    LINES = [
        'First short line of text',
        'Second short line of text',
        'Third short line of text',
        'Fourth short line of text',
        'Fifth short line of text',
        'Sixth short line of text',
        '',
        'Guard line after paragraph',
    ]

    def fixture(self, ctx, variant=None):
        return crlf(self.LINES)

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.press('RIGHT', mods=['CTRL'])   # EOL of line 0 (col 24)
        t.press('DEL')                    # In WRAP_TXT at EOL: triggers REFLOW!
        t.press('S', mods=['CTRL'])
        t.wait(3.0)
        t.snap('saved')
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        got = run.session.extract(run.dsk, 'DOC.TXT')
        want_p1 = ('First short line of text Second short line of text '
                   'Third short line of text')
        want = crlf([want_p1, 'Fourth short line of text',
                     'Fifth short line of text', 'Sixth short line of text',
                     '', 'Guard line after paragraph'])
        checks = [
            Check('D6/content', got == want,
                  'document matches byte for byte' if got == want else
                  'got %r' % (got[:80] if got else None)),
            Check('D6/totlines', run.var('saved', 'TOTLINES') == 6,
                  'TOTLINES = %s (expected 6)' % run.var('saved', 'TOTLINES')),
        ]
        return checks


# --- D7  SOFT TABS & EXPANSION ----------------------------------------


class D7Tabs(Case):
    name = 'D7-tabs'
    desc = 'soft tabs: dynamic tab stops and raw tab expansion on load'
    origin = ('ACTTAB calculates B = TABWIDTH - (CURX % TABWIDTH) and inserts spaces; '
              'FILELOAD expands raw #09 on load up to 80 columns based on TABWIDTH')
    cfg = DEFAULT_CFG

    FIXTURE = b'A\tB\r\nC\r\n'

    def fixture(self, ctx, variant=None):
        return self.FIXTURE

    def timeline(self, ctx, variant=None):
        t = Timeline()
        # Line 0 is 'A   B'
        # Move to line 1 (which has 'C')
        t.press('DOWN')
        t.press('RIGHT')  # col 1 (after 'C')
        t.press('TAB')    # At col 1: 4 - (1 % 4) = 3 spaces -> col 4
        t.text('X')       # col 4 -> col 5
        t.press('TAB')    # At col 5: 4 - (5 % 4) = 3 spaces -> col 8
        t.snap('tabbed')
        t.press('S', mods=['CTRL'])
        t.wait(3.0)
        t.snap('saved')
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        got = run.session.extract(run.dsk, 'DOC.TXT')
        want = crlf(['A   B', 'C   X   '])
        checks = [
            Check('D7/content', got == want,
                  'document matches byte for byte' if got == want else
                  'got %r, want %r' % (got, want)),
            Check('D7/curx', run.var('tabbed', 'CURX') == 8,
                  'CURX = %s (expected 8)' % run.var('tabbed', 'CURX')),
            Check('D7/totlines', run.var('saved', 'TOTLINES') == 2,
                  'TOTLINES = %s (expected 2)' % run.var('saved', 'TOTLINES')),
        ]
        return checks


# --- D8  ACCENTS & DEAD KEYS ------------------------------------------


class D8Accents(Case):
    name = 'D8-accents'
    desc = 'Spanish characters via GRAPH matrix combos and dead-key state machine'
    origin = ('CHKACNT reads the keyboard matrix for GRAPH combos '
              '(á é í ó ú ñ Ñ ü ¡ ¿) bypassing the regional BIOS, and TRNDEAD '
              'translates the acute and diaeresis dead keys.  It also covers '
              'the double: the BIOS keyboard ISR queues its own GRAPH code in '
              'the window between the CHKACNT poll and the CHSNS poll of one '
              'MAINLOOP pass, TRNGRPH turned it into the same accent, and the '
              'character was typed twice')
    # The clock is off on purpose: CHKCLK blits the colon once a second and
    # the minute box once a minute, both timed off the host RTC, which moves
    # MAINLOOP's phase from run to run and with it whether the race below is
    # entered at all.
    cfg = DEFAULT_CFG.replace('CLOCK=1', 'CLOCK=0')
    autoexec = 'S6ED DOC.TXT'

    # The two delivery paths race inside one MAINLOOP pass, so the double is
    # not reproduced by pressing a key once and hoping: whether a key-down
    # lands in the window depends on where MAINLOOP is when the BIOS queues
    # its code, i.e. on the phase between the keystroke and the interrupt.
    # With the clock off that phase is fixed, so the run is deterministic --
    # and deterministic is not the same as robust.  A SINGLE gap ties the case
    # to one phase and any unrelated change to timing slides the build out of
    # the window: recalibrated to 0.05, 0.040 and 0.053 in turn, and on
    # 2026-09-22 twice in one afternoon, and on 2026-09-23 when the undo
    # groups grew CORE by ~0.6 KB.
    #
    # BE HONEST ABOUT WHAT THIS IS: the passes use four different gaps so that
    # more than one phase is sampled, and the set below is the one MEASURED to
    # reproduce the defect on the current build.  Measured 2026-09-23: alone,
    # 0.031, 0.037, 0.039, 0.041 and 0.047 catch it and 0.033, 0.043, 0.049
    # and 0.051 do not -- and the old set (0.033, 0.037, 0.043, 0.047) did NOT
    # catch it although two of its members do alone.  The passes run back to
    # back, each shifts the phase of the next, so a gap measured alone says
    # nothing about it inside a set: MEASURE THE SET.  There is no model that predicts
    # which gaps work; the first spread tried (0.030/0.050/0.070/0.090) looked
    # wide and was not, because all four are congruent mod the 20 ms PAL frame
    # and therefore walk the same phase.  Spreading in milliseconds is not
    # spreading in phase.
    #
    # RECALIBRATION, when it comes: sweep GRAPH_GAPS against `runtests.py
    # --selftest -k d8-double`, keep a set containing at least one gap that
    # catches on its own, and then run the set itself, since members that
    # catch alone can cancel out together.  The fixed build is byte for byte correct at every
    # gap tried, which is what makes the spread free.
    #
    # THE REAL FIX is to stop sampling and force the race: inject the key-down
    # from a breakpoint at MAINLOOP.GOTACNT, inside the window itself, so the
    # case is deterministic by construction instead of by luck.  That is
    # harness work and is not done.
    GRAPH_ROW = 'AEIOUNW1/'
    GRAPH_GAPS = (0.029, 0.031, 0.037)
    GRAPH_PASSES = len(GRAPH_GAPS)

    def timeline(self, ctx, variant=None):
        t = Timeline()
        # Line 0: unshifted GRAPH combinations (á é í ó ú ñ ü ¡ ¿), four times
        for gap in self.GRAPH_GAPS:
            for key in self.GRAPH_ROW:
                t.press(key, mods=['GRAPH'], tail=gap)
        t.press('RETURN')
        # Line 1: shifted GRAPH combination (Ñ)
        t.press('N', mods=['GRAPH', 'SHIFT'])
        t.press('RETURN')
        # Line 2: Dead keys (acute and diaeresis)
        t.press('ACCENT')
        t.press('A')
        t.press('ACCENT')
        t.press('O')
        t.press('ACCENT', mods=['SHIFT'])
        t.press('U')
        t.snap('typed')
        t.press('S', mods=['CTRL'])
        t.wait(3.0)
        t.snap('saved')
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        got = run.session.extract(run.dsk, 'DOC.TXT')
        line0 = self.GRAPH_PASSES * bytes([0xA0, 0x82, 0xA1, 0xA2, 0xA3, 0xA4,
                                           0x81, 0xAD, 0xA8])
        line1 = bytes([0xA5])
        line2 = bytes([0xA0, 0xA2, 0x81])
        want = line0 + b'\r\n' + line1 + b'\r\n' + line2 + b'\r\n'
        checks = [
            Check('D8/content', got == want,
                  'document matches byte for byte' if got == want else
                  'got %r, want %r' % (got, want)),
            Check('D8/totlines', run.var('saved', 'TOTLINES') == 3,
                  'TOTLINES = %s (expected 3)' % run.var('saved', 'TOTLINES')),
        ]
        return checks


# --- D9  JAPANESE MSX2+ KANA SUPPRESSION -----------------------------


class D9Kana(Case):
    name = 'D9-kana'
    desc = 'suppress KANA mode and force physical LED off in Boosted_MSX2+_JP'
    origin = ('On Japanese MSX machines, MAINLOOP and CHKACNT continuously reset '
              'KANAST and KANAMOD, and KANARST sets PSG R15 bit 7 to extinguish the KANA LED')
    machine = MACH_JP
    cfg = DEFAULT_CFG
    autoexec = 'S6ED DOC.TXT'

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.snap('boot')
        t.press('CODE')   # KANA key on Japanese keyboard (row 6 bit 4)
        t.snap('after_kana')
        t.text('JP-TEST')
        t.press('S', mods=['CTRL'])
        t.wait(3.0)
        t.snap('saved')
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        got = run.session.extract(run.dsk, 'DOC.TXT')
        want = b'JP-TEST\r\n'
        b_kana = run.var('boot', 'KANAST')
        b_kmod = run.var('boot', 'KANAMOD')
        b_psg = run.var('boot', 'PSG15')
        a_kana = run.var('after_kana', 'KANAST')
        a_kmod = run.var('after_kana', 'KANAMOD')
        a_psg = run.var('after_kana', 'PSG15')
        checks = [
            Check('D9/kanast', b_kana == 0 and a_kana == 0,
                  'KANAST: boot=%s, after_kana=%s (expected 0)' % (b_kana, a_kana)),
            Check('D9/kanamod', (b_kmod & 1) == 0 and (a_kmod & 1) == 0,
                  'KANAMOD bit 0: boot=%s, after_kana=%s (expected 0)' % (b_kmod & 1, a_kmod & 1)),
            Check('D9/led-off', (b_psg & 0x80) == 0x80 and (a_psg & 0x80) == 0x80,
                  'PSG R15 bit 7: boot=0x%02X, after_kana=0x%02X (expected bit 7=1)' % (b_psg, a_psg)),
            Check('D9/content', got == want,
                  'document matches byte for byte' if got == want else
                  'got %r, want %r' % (got, want)),
        ]
        return checks


# --- D10 MARKUP ENGINE ------------------------------------------------


class D10Markup(Case):
    name = 'D10-markup'
    desc = 'markdown and lite markup: mode cycling, delimiter insertion, and selection wrapping'
    origin = ('ACTCYCMK cycles MKUPMD (OFF->MD->LITE->OFF), INSDELIM inserts delimiter pairs '
              'with centered cursor, and WRAPSEL wraps single-line selection in delimiters')
    cfg = ("; MARKUP test configuration\r\n"
           "MARKUP = OFF\r\n"
           "WRAP = DEV\r\n"
           "PROFILE = STD\r\n")
    autoexec = 'S6ED DOC.TXT'

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.snap('m0')
        t.press('T', mods=['CTRL'])    # OFF -> MD (1)
        t.snap('m1')
        t.press('B', mods=['CTRL'])    # INSDELIM: inserts '****', cursor in middle
        t.text('BOLD')                 # text is '**BOLD**', cursor at col 6 (before closing '**')
        t.press('RIGHT', repeat=2)     # move past closing '**' to EOL (col 8)
        t.press('RETURN')              # line 1
        t.press('I', mods=['CTRL'])    # INSDELIM: inserts '**', cursor in middle
        t.text('ITAL')                 # text is '*ITAL*', cursor at col 5 (before closing '*')
        t.press('RIGHT')               # move past closing '*' to EOL (col 6)
        t.press('RETURN')              # line 2
        t.text('TARGET')               # len 6
        t.press('LEFT', mods=['SHIFT'], repeat=6)  # select 'TARGET'
        t.press('B', mods=['CTRL'])    # WRAPSEL: wraps with '**' -> '**TARGET**' (len 10)
        t.press('RIGHT', mods=['CTRL'])            # move to EOL of line 2 (col 10)
        t.press('T', mods=['CTRL'])    # MD -> LITE (2)
        t.snap('m2')
        t.press('RETURN')              # line 3
        t.text('LITETEST')             # len 8
        t.press('LEFT', mods=['SHIFT'], repeat=8)  # select 'LITETEST'
        t.press('B', mods=['CTRL'])    # WRAPSEL: in LITE wraps with '*' -> '*LITETEST*' (len 10)
        t.press('T', mods=['CTRL'])    # LITE -> OFF (0)
        t.snap('m3')
        t.press('S', mods=['CTRL'])
        t.wait(3.0)
        t.snap('saved')
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        got = run.session.extract(run.dsk, 'DOC.TXT')
        want = crlf(['**BOLD**', '*ITAL*', '**TARGET**', '*LITETEST*'])
        m0 = run.var('m0', 'MKUPMD')
        m1 = run.var('m1', 'MKUPMD')
        m2 = run.var('m2', 'MKUPMD')
        m3 = run.var('m3', 'MKUPMD')
        checks = [
            Check('D10/mode-cycle', m0 == 0 and m1 == 1 and m2 == 2 and m3 == 0,
                  'MKUPMD: %d -> %d -> %d -> %d' % (m0, m1, m2, m3)),
            Check('D10/content', got == want,
                  'document matches byte for byte' if got == want else
                  'got %r, want %r' % (got, want)),
            Check('D10/totlines', run.var('saved', 'TOTLINES') == 4,
                  'TOTLINES = %s (expected 4)' % run.var('saved', 'TOTLINES')),
        ]
        return checks


# --- D11 THE RIGHT MARGIN ---------------------------------------------


class D11Margin(Case):
    name = 'D11-margin'
    desc = 'an edit at the right margin of a FULL line is an append, not an insert'
    origin = ('On every line but a full one the cursor can park one past the '
              'last character, and GETMAXC says so.  A full line has no such '
              "column, so GETMAXC clamps to TEXTCOLS - 1 and \"at the end\" "
              'and "on the last character" become the same position -- after '
              'which every edit taken at the clamped column landed one place '
              'too early.  Measured on a full line ending in HELLO: typing X '
              'wrapped it as "HELLxO", and a space at the margin carried the '
              '"O" down to the new line instead of breaking after it.  Both '
              'targets, because EDPSHWR and SPLITL are in CORE.')
    # WRAP=TXT is the whole point; AUTOALIGN off so the cursor column after a
    # break is unambiguous.
    cfg = ("PROFILE=STD\nWRAP=TXT\nMARKUP=OFF\nCLOCK=0\n"
           "TABWIDTH=4\nEOL=AUTO\nAUTOALIGN=OFF\n")
    COLS = 80                       # S6ED's TEXTCOLS
    TAIL = 'HELLO'
    LINE = 'A' * (COLS - len(TAIL) - 1) + ' ' + TAIL
    LINES = [LINE, 'SECOND LINE']
    variants = ('push', 'space')

    def fixture(self, ctx, variant=None):
        return crlf(self.LINES)

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.press('RIGHT', mods=['CTRL'])         # ACEOL: clamps to COLS - 1
        t.snap('ateol')
        t.press('X' if variant == 'push' else 'SPACE')
        t.press('S', mods=['CTRL'])
        t.wait(3.0)
        t.snap('done')
        return t

    def verify(self, ctx, runs):
        checks = []
        for variant, run in sorted(runs.items()):
            pre = 'D11/%s' % variant
            checks.append(Check('%s/clamped' % pre,
                                run.var('ateol', 'CURX') == self.COLS - 1,
                                'ACEOL leaves CURX = %s on a full line'
                                % run.var('ateol', 'CURX')))
            got = run.session.extract(run.dsk, 'DOC.TXT')
            lines = (got or b'').decode('ascii', 'replace').split('\r\n')
            while lines and lines[-1] == '':
                lines.pop()
            if variant == 'push':
                # The trailing word moves down and the new character goes
                # AFTER it, with the cursor one past what was typed.  The
                # head keeps the separating space -- that is existing
                # behaviour and not what this case is about.
                # keymatrixdown without SHIFT types lowercase.
                want = [self.LINE[:self.COLS - len(self.TAIL)],
                        self.TAIL + 'x',
                        'SECOND LINE']
                curx = len(self.TAIL) + 1
            else:
                # A space at the margin is just a line break: the head keeps
                # every one of its characters and the new line is empty.
                want = [self.LINE, '', 'SECOND LINE']
                curx = 0
            checks.append(Check('%s/content' % pre, lines == want,
                                'document breaks correctly' if lines == want
                                else 'got %r' % (lines[:2],)))
            checks.append(Check('%s/curx' % pre,
                                run.var('done', 'CURX') == curx,
                                'CURX = %s (expected %d)'
                                % (run.var('done', 'CURX'), curx)))
            checks.append(Check('%s/totlines' % pre,
                                run.var('done', 'TOTLINES') == 3,
                                'TOTLINES = %s (expected 3)'
                                % run.var('done', 'TOTLINES')))
        return checks


# --- D12  LONG LINES (VARIABLE-LENGTH STORAGE, MAXCOLS = 255) --------


class D12LongLine(Case):
    name = 'D12-longline'
    desc = 'lines up to 255 characters without truncation or wrap in WRAP_DEV'
    origin = ('Phase B variable-length line architecture: MAXCOLS = 255, '
              'WORKBUF in Page 3 unbanked RAM (#C000), dynamic capacity per line')
    LINE1 = '0123456789' * 14                 # 140 characters
    LINE2 = 'SECOND LINE 12345'
    LINES = [LINE1, LINE2]

    def fixture(self, ctx, variant=None):
        return crlf(self.LINES)

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.wait(1.0)
        t.press('RIGHT', mods=['CTRL'])         # EOL (col 140)
        t.snap('ateol')
        t.text('XYZ')                           # append 3 chars -> len 143, curx 143
        t.snap('appended')
        t.press('LEFT', repeat=3)               # cursor back at col 140
        t.press('DEL', repeat=3)                # delete 'XYZ' -> len 140, curx 140
        t.snap('deleted')
        t.press('S', mods=['CTRL'])
        t.wait(3.0)
        t.snap('saved')
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        checks = []
        checks.append(Check('D12/ateol-curx', run.var('ateol', 'CURX') == 140,
                            'CURX = %s at EOL (expected 140)'
                            % run.var('ateol', 'CURX')))
        checks.append(Check('D12/appended-curx', run.var('appended', 'CURX') == 143,
                            'CURX = %s after append (expected 143)'
                            % run.var('appended', 'CURX')))
        checks.append(Check('D12/deleted-curx', run.var('deleted', 'CURX') == 140,
                            'CURX = %s after delete (expected 140)'
                            % run.var('deleted', 'CURX')))
        got = run.session.extract(run.dsk, 'DOC.TXT')
        want = crlf(self.LINES)
        checks.append(Check('D12/content', got == want,
                            'document matches byte for byte with 140-char line'
                            if got == want else 'got %r' % (got[:60] if got else None)))
        return checks


# --- E1  MULTI-LINE CUT -----------------------------------------------


class E1Cut(Case):
    name = 'E1-cut'
    desc = 'multi-line cut removes lines, preserves remainder, zero visual residue'
    origin = ('ACTCUT copies active selection to CLIPBUF and executes ACTDLS: '
              'multi-line deletion must splice remaining lines, adjust TOTLINES, '
              'and leave zero XOR residue on screen')
    LINES = ['LINE ZERO 000', 'LINE ONE 111', 'LINE TWO 222',
             'LINE THREE 333', 'LINE FOUR 444', 'LINE FIVE 555']

    def fixture(self, ctx, variant=None):
        return crlf(self.LINES)

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.press('DOWN', mods=['SHIFT'], repeat=3)  # select lines 0..2 to line 3 col 0
        t.snap('selected')
        t.press('X', mods=['CTRL'])                 # ACTCUT
        t.press('S', mods=['CTRL'])
        t.wait(3.0)
        t.snap('cut', vram=True)
        # Full redraw: in a 3-line document, PG_DOWN hits bottom, PG_UP hits top (line 0)
        t.press('DOWN', mods=['GRAPH'])
        t.press('UP', mods=['GRAPH'])
        t.snap('redrawn', vram=True)
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        got = run.session.extract(run.dsk, 'DOC.TXT')
        want = crlf(['LINE THREE 333', 'LINE FOUR 444', 'LINE FIVE 555'])
        checks = [
            Check('E1/content', got == want,
                  'document matches byte for byte' if got == want else
                  'got %r' % got),
            Check('E1/totlines', run.var('cut', 'TOTLINES') == 3,
                  'TOTLINES = %s (expected 3)' % run.var('cut', 'TOTLINES')),
            Check('E1/clipboard', run.var('cut', 'CLIPLEN') > 0,
                  'CLIPLEN = %s (> 0)' % run.var('cut', 'CLIPLEN')),
        ]
        cut_snap, redrawn = run.snaps.get('cut', {}), run.snaps.get('redrawn', {})
        same_state = all(cut_snap.get(k) == redrawn.get(k) for k in
                         ('TOPLINE', 'DOCLINE', 'CURX', 'CURY', 'TOTLINES'))
        if same_state:
            cursor = [(cut_snap.get('CURX', 0), cut_snap.get('CURY', 0))]
            d = vram.diff(run.blob('cut', 'vram'), run.blob('redrawn', 'vram'),
                          ignore_cells=cursor)
            checks.append(Check('E1/render-pure', not d,
                                'screen identical to a full REDRAW' if not d else
                                '%d stray pixels' % len(d)))
        else:
            checks.append(Check('E1/render-pure', False, 'state mismatch before diff'))
        return checks


# --- E2  MULTI-LINE PASTE ---------------------------------------------


class E2Paste(Case):
    name = 'E2-paste'
    desc = 'multi-line paste splits line and inserts CRLF blocks correctly'
    origin = ('ACTPAST inserts runs and handles CR/LF breaks: pasting a '
              'multi-line clipboard in the middle of a line must split the '
              'host line and insert all lines without dropping characters')
    LINES = ['FIRST LINE', 'SECOND LINE', 'TARGET--LINE', 'LAST LINE']

    def fixture(self, ctx, variant=None):
        return crlf(self.LINES)

    def timeline(self, ctx, variant=None):
        t = Timeline()
        # Copy first two lines
        t.press('DOWN', mods=['SHIFT'], repeat=2) # select lines 0 and 1
        t.press('C', mods=['CTRL'])               # ACTCOPY (copies 2 lines with CRLF)
        # Cursor is at line 2 col 0. Plain RIGHT deselects and moves to col 6
        t.press('RIGHT', repeat=6)
        t.snap('before-paste')
        t.press('V', mods=['CTRL'])               # ACTPAST
        t.press('S', mods=['CTRL'])
        t.wait(3.0)
        t.snap('saved')
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        got = run.session.extract(run.dsk, 'DOC.TXT')
        want = crlf([
            'FIRST LINE',
            'SECOND LINE',
            'TARGETFIRST LINE',
            'SECOND LINE',
            '--LINE',
            'LAST LINE',
        ])
        checks = [
            Check('E2/content', got == want,
                  'document matches byte for byte' if got == want else
                  'got %r' % got),
            Check('E2/totlines', run.var('saved', 'TOTLINES') == 6,
                  'TOTLINES = %s (expected 6)' % run.var('saved', 'TOTLINES')),
        ]
        return checks


# --- E3  SELECTION CROSSING SCROLL EDGE --------------------------------


class E3SelScroll(Case):
    name = 'E3-sel-scroll'
    desc = 'extending selection across viewport edge scrolls cleanly without residue'
    origin = ('SELDIFF optimizes row diffs, but when the selection extends past '
              'the viewport edge (CURY == 23) hardware scroll occurs: ACTSLMD must '
              'call SELPRE before ACTMVD scrolls, or inverted pixels will be blitted '
              'and left as ghost artifacts')

    def fixture(self, ctx, variant=None):
        lines = []
        for i in range(80):
            if i % 2 == 0:
                lines.append('LINE %02d SHORT' % i)
            else:
                lines.append(('LINE %02d LONG ' % i) + ('X' * 55))
        return crlf(lines)

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.press('DOWN', repeat=20)                 # line 20, col 0
        t.press('DOWN', mods=['SHIFT'], repeat=5)  # select across row 23 to line 25
        t.snap('scrolled_sel')
        t.press('RIGHT')                           # deselects (CHKUNSEL) and moves col 0 -> 1
        t.press('LEFT')                            # moves col 1 -> 0
        t.snap('deselected', vram=True)
        t.press('DOWN', mods=['GRAPH'])            # ACTPGDN: DOCLINE 25 + 24 = 49 (no bottom clamp)
        t.press('UP', mods=['GRAPH'])              # ACTPGUP: DOCLINE 49 - 24 = 25 (pure return)
        t.snap('redrawn', vram=True)
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        sel = run.snaps.get('scrolled_sel', {})
        checks = [
            Check('E3/selection-active', sel.get('SELACT') == 1,
                  'SELACT = %s' % sel.get('SELACT')),
            Check('E3/viewport-scrolled', sel.get('TOPLINE', 0) > 0,
                  'TOPLINE = %s (> 0)' % sel.get('TOPLINE')),
            Check('E3/docline-advanced', sel.get('DOCLINE') == 25,
                  'DOCLINE = %s (expected 25)' % sel.get('DOCLINE')),
        ]
        desel, redrawn = run.snaps.get('deselected', {}), run.snaps.get('redrawn', {})
        same_state = all(desel.get(k) == redrawn.get(k) for k in
                         ('TOPLINE', 'DOCLINE', 'CURX', 'CURY', 'TOTLINES'))
        if same_state:
            cursor = [(desel.get('CURX', 0), desel.get('CURY', 0))]
            d = vram.diff(run.blob('deselected', 'vram'),
                          run.blob('redrawn', 'vram'), ignore_cells=cursor)
            checks.append(Check('E3/render-pure', not d,
                                'screen identical to a full REDRAW' if not d else
                                '%d stray pixels' % len(d)))
        else:
            checks.append(Check('E3/render-pure', False, 'state mismatch before diff'))
        return checks


# --- E4  SELECT ALL AND DELETE ----------------------------------------


class E4SelAllDel(Case):
    name = 'E4-selall-del'
    desc = 'Ctrl+A selects entire document and DEL leaves an empty single line'
    origin = ('ACTSELAL anchors at (0,0) and selects to end of document: '
              'deleting the full selection via ACTDLS must reduce TOTLINES to 1, '
              'empty line 0, and repaint a clean screen')
    LINES = ['FIRST LINE 111', 'SECOND LINE 222', 'THIRD LINE 333',
             'FOURTH LINE 444', 'FIFTH LINE 555']

    def fixture(self, ctx, variant=None):
        return crlf(self.LINES)

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.press('A', mods=['CTRL'])         # ACTSELAL
        t.snap('all_sel')
        t.press('DEL')                      # ACTDELFW -> ACTDLS
        t.press('S', mods=['CTRL'])
        t.wait(3.0)
        t.snap('deleted', vram=True)
        t.press('DOWN', mods=['GRAPH'])
        t.press('UP', mods=['GRAPH'])
        t.snap('redrawn', vram=True)
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        sel = run.snaps.get('all_sel', {})
        checks = [
            Check('E4/sel-active', sel.get('SELACT') == 1,
                  'SELACT = %s' % sel.get('SELACT')),
            Check('E4/totlines', run.var('deleted', 'TOTLINES') == 1,
                  'TOTLINES = %s (expected 1)' % run.var('deleted', 'TOTLINES')),
            Check('E4/curx', run.var('deleted', 'CURX') == 0,
                  'CURX = %s (expected 0)' % run.var('deleted', 'CURX')),
            Check('E4/docline', run.var('deleted', 'DOCLINE') == 0,
                  'DOCLINE = %s (expected 0)' % run.var('deleted', 'DOCLINE')),
        ]
        got = run.session.extract(run.dsk, 'DOC.TXT')
        empty_ok = got in (b'\r\n', b'', b'\n')
        checks.append(Check('E4/content', empty_ok,
                            'document empty on disk' if empty_ok else
                            'got %r' % got))
        del_snap, redrawn = run.snaps.get('deleted', {}), run.snaps.get('redrawn', {})
        same_state = all(del_snap.get(k) == redrawn.get(k) for k in
                         ('TOPLINE', 'DOCLINE', 'CURX', 'CURY', 'TOTLINES'))
        if same_state:
            cursor = [(del_snap.get('CURX', 0), del_snap.get('CURY', 0))]
            d = vram.diff(run.blob('deleted', 'vram'), run.blob('redrawn', 'vram'),
                          ignore_cells=cursor)
            checks.append(Check('E4/render-pure', not d,
                                'screen identical to a full REDRAW' if not d else
                                '%d stray pixels' % len(d)))
        else:
            checks.append(Check('E4/render-pure', False, 'state mismatch before diff'))
        return checks


# --- E5  REPLACE ON TYPING --------------------------------------------


class E5Replace(Case):
    name = 'E5-replace'
    desc = 'typing printable character over active selection replaces it'
    origin = ('.DOPRINT checks SELACT: if active, ACTDLS must delete the '
              'selection before the character is inserted/overwritten')
    LINES = ['HELLO WORLD', 'SECOND LINE']

    def fixture(self, ctx, variant=None):
        return crlf(self.LINES)

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.press('RIGHT', repeat=6)                 # col 6 ("WORLD")
        t.press('RIGHT', mods=['SHIFT'], repeat=5) # select cols 6..11
        t.snap('selected')
        t.text('EARTH')                            # replaces "WORLD" with "EARTH"
        t.press('S', mods=['CTRL'])
        t.wait(3.0)
        t.snap('saved')
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        sel = run.snaps.get('selected', {})
        selstrl = sel.get('SELSTRL', [0, 0, 0, 0, 0, 0])
        checks = [
            Check('E5/sel-active', sel.get('SELACT') == 1,
                  'SELACT = %s' % sel.get('SELACT')),
            Check('E5/sel-range',
                  selstrl[2] == 6 and selstrl[5] == 11,
                  'range cols %s..%s' % (selstrl[2], selstrl[5])),
            Check('E5/totlines', run.var('saved', 'TOTLINES') == 2,
                  'TOTLINES = %s (expected 2)' % run.var('saved', 'TOTLINES')),
            Check('E5/curx', run.var('saved', 'CURX') == 11,
                  'CURX = %s (expected 11)' % run.var('saved', 'CURX')),
        ]
        got = run.session.extract(run.dsk, 'DOC.TXT')
        want = crlf(['HELLO EARTH', 'SECOND LINE'])
        checks.append(Check('E5/content', got == want,
                            'document matches byte for byte' if got == want else
                            'got %r' % got))
        return checks


# --- E6  SELECTION BY WORD AND BY PAGE --------------------------------


class E6SelWordPage(Case):
    name = 'E6-sel-word-page'
    desc = 'Shift+Graph+Right selects words, Shift+Graph+Down selects pages'
    origin = ('ACSLWRT (Shift+Graph+Right) extends selection to next word '
              'boundaries, ACSLPGD (Shift+Graph+Down) extends selection by 24 rows')
    LINES = ['ALPHA BETA GAMMA DELTA'] + ['LINE %02d' % i for i in range(1, 35)]

    def fixture(self, ctx, variant=None):
        return crlf(self.LINES)

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.press('RIGHT', mods=['SHIFT', 'GRAPH'], repeat=2)
        t.snap('word_sel')
        t.press('DOWN', mods=['SHIFT', 'GRAPH'], repeat=1)
        t.snap('page_sel')
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        w = run.snaps.get('word_sel', {})
        p = run.snaps.get('page_sel', {})
        w_rec = w.get('SELSTRL', [0, 0, 0, 0, 0, 0])
        p_endl = p.get('SELSTRL', [0, 0, 0, 0, 0, 0])[3] + 256 * p.get('SELSTRL', [0, 0, 0, 0, 0, 0])[4]
        checks = [
            Check('E6/word-active', w.get('SELACT') == 1,
                  'SELACT = %s' % w.get('SELACT')),
            Check('E6/word-curx', w.get('CURX') == 11,
                  'CURX = %s (expected 11 at GAMMA)' % w.get('CURX')),
            Check('E6/word-selendx', w_rec[5] == 11,
                  'SELENDX = %s (expected 11)' % w_rec[5]),
            Check('E6/word-strx', w_rec[2] == 0,
                  'SELSTRX = %s (expected 0)' % w_rec[2]),
            Check('E6/page-active', p.get('SELACT') == 1,
                  'SELACT = %s' % p.get('SELACT')),
            Check('E6/page-docline', p.get('DOCLINE') == 24,
                  'DOCLINE = %s (expected 24)' % p.get('DOCLINE')),
            Check('E6/page-selendl', p_endl == 24,
                  'SELENDL = %s (expected 24)' % p_endl),
        ]
        return checks


# --- E7  CLIPBOARD CAPACITY LIMIT (CLIPMAX = 2048) -------------------


class E7ClipLimit(Case):
    name = 'E7-clip-limit'
    desc = 'copying beyond CLIPMAX (2048 bytes) clamps without buffer overrun'
    origin = ('CLIPBUF capacity is CLIPMAX (2048 bytes) in page 0 RAM: '
              'ACTCOPY must clamp copied bytes and CRLF breaks to prevent '
              'overrunning into adjacent variables (FILENAME, FILEHAND)')
    # 35 lines of 75 characters = 2,625 characters (> 2048)
    LINES = ['%02d-%s' % (i, 'X' * 70) for i in range(35)]

    def fixture(self, ctx, variant=None):
        return crlf(self.LINES)

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.press('A', mods=['CTRL'])         # select all 35 lines (~2625 B)
        t.press('C', mods=['CTRL'])         # ACTCOPY
        t.snap('copied')
        t.press('S', mods=['CTRL'])         # save: verifies FILENAME and I/O intact
        t.wait(3.0)
        t.snap('saved')
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        checks = [
            Check('E7/cliplen', run.var('copied', 'CLIPLEN') == 2048,
                  'CLIPLEN = %s (expected 2048)' % run.var('copied', 'CLIPLEN')),
        ]
        got = run.session.extract(run.dsk, 'DOC.TXT')
        want = crlf(self.LINES)
        checks.append(Check('E7/content-intact', got == want,
                            'document saved intact after copy' if got == want else
                            'save corrupted'))
        checks.append(Check('E7/alive', run.var('saved', 'TOTLINES') == 35,
                            'TOTLINES = %s (expected 35)' % run.var('saved', 'TOTLINES')))
        return checks


# --- I1  UNIX EOL AUTO-DETECTION & PRESERVATION -----------------------


class I1UnixAuto(Case):
    name = 'I1-eol-unix-auto'
    desc = 'auto-detect UNIX LF on load and preserve pure LF on save'
    origin = ('FILELOAD inspects the first line delimiter: standalone LF sets '
              'SAVEEOL = 1 (UNIX); FILESAVE writes LF only for every line')
    cfg = DEFAULT_CFG

    FIXTURE = b'FIRST UNIX LINE\nSECOND UNIX LINE\nTHIRD UNIX LINE\n'

    def fixture(self, ctx, variant=None):
        return self.FIXTURE

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.snap('loaded')
        t.press('DOWN')
        t.text('ADDED ')
        t.press('S', mods=['CTRL'])
        t.wait(3.0)
        t.snap('saved')
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        got = run.session.extract(run.dsk, 'DOC.TXT')
        want = b'FIRST UNIX LINE\nADDED SECOND UNIX LINE\nTHIRD UNIX LINE\n'
        saveeol_loaded = run.var('loaded', 'SAVEEOL')
        saveeol_saved = run.var('saved', 'SAVEEOL')
        checks = [
            Check('I1/saveeol', saveeol_loaded == 1 and saveeol_saved == 1,
                  'SAVEEOL: loaded=%s, saved=%s (expected 1)' % (saveeol_loaded, saveeol_saved)),
            Check('I1/no-cr', b'\r' not in got if got else False,
                  'saved file contains zero CR (0x0D) bytes' if (got and b'\r' not in got) else
                  'CR found in UNIX file'),
            Check('I1/content', got == want,
                  'document matches byte for byte' if got == want else
                  'got %r, want %r' % (got, want)),
            Check('I1/totlines', run.var('saved', 'TOTLINES') == 3,
                  'TOTLINES = %s (expected 3)' % run.var('saved', 'TOTLINES')),
        ]
        return checks


# --- I2  DOS EOL AUTO-DETECTION & PRESERVATION ------------------------


class I2DosAuto(Case):
    name = 'I2-eol-dos-auto'
    desc = 'auto-detect DOS CRLF on load and preserve CRLF on save'
    origin = ('FILELOAD inspects the first line delimiter: CRLF sets '
              'SAVEEOL = 0 (DOS); FILESAVE writes CR+LF for every line')
    cfg = DEFAULT_CFG

    FIXTURE = b'FIRST DOS LINE\r\nSECOND DOS LINE\r\n'

    def fixture(self, ctx, variant=None):
        return self.FIXTURE

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.snap('loaded')
        t.press('DOWN')
        t.text('INSERTED ')
        t.press('S', mods=['CTRL'])
        t.wait(3.0)
        t.snap('saved')
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        got = run.session.extract(run.dsk, 'DOC.TXT')
        want = b'FIRST DOS LINE\r\nINSERTED SECOND DOS LINE\r\n'
        saveeol_loaded = run.var('loaded', 'SAVEEOL')
        saveeol_saved = run.var('saved', 'SAVEEOL')
        checks = [
            Check('I2/saveeol', saveeol_loaded == 0 and saveeol_saved == 0,
                  'SAVEEOL: loaded=%s, saved=%s (expected 0)' % (saveeol_loaded, saveeol_saved)),
            Check('I2/content', got == want,
                  'document matches byte for byte' if got == want else
                  'got %r, want %r' % (got, want)),
            Check('I2/totlines', run.var('saved', 'TOTLINES') == 2,
                  'TOTLINES = %s (expected 2)' % run.var('saved', 'TOTLINES')),
        ]
        return checks


# --- I3  CONVERT DOS TO UNIX VIA CFG ----------------------------------


class I3ConvertDosToUnix(Case):
    name = 'I3-eol-convert-dos2unix'
    desc = 'load DOS CRLF document under EOL=UNIX and save converted with LF only'
    origin = ('CFG with EOL=UNIX disables AUTOLOD and forces SAVEEOL = 1; '
              'FILESAVE converts all line endings from CRLF to LF')
    cfg = ("; EOL=UNIX configuration\r\n"
           "EOL = UNIX\r\n"
           "PROFILE = STD\r\n")

    FIXTURE = b'ALPHA\r\nBETA\r\nGAMMA\r\n'

    def fixture(self, ctx, variant=None):
        return self.FIXTURE

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.snap('loaded')
        t.press('S', mods=['CTRL'])
        t.wait(3.0)
        t.snap('saved')
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        got = run.session.extract(run.dsk, 'DOC.TXT')
        want = b'ALPHA\nBETA\nGAMMA\n'
        checks = [
            Check('I3/saveeol', run.var('loaded', 'SAVEEOL') == 1,
                  'SAVEEOL = %s (expected 1)' % run.var('loaded', 'SAVEEOL')),
            Check('I3/no-cr', b'\r' not in got if got else False,
                  'converted document contains zero CR bytes' if (got and b'\r' not in got) else
                  'CR byte found after conversion'),
            Check('I3/content', got == want,
                  'document converted to UNIX byte for byte' if got == want else
                  'got %r, want %r' % (got, want)),
            Check('I3/totlines', run.var('saved', 'TOTLINES') == 3,
                  'TOTLINES = %s (expected 3)' % run.var('saved', 'TOTLINES')),
        ]
        return checks


# --- I4  CONVERT UNIX TO DOS VIA CFG ----------------------------------


class I4ConvertUnixToDos(Case):
    name = 'I4-eol-convert-unix2dos'
    desc = 'load UNIX LF document under EOL=DOS and save converted with CRLF'
    origin = ('CFG with EOL=DOS disables AUTOLOD and forces SAVEEOL = 0; '
              'FILESAVE converts all line endings from LF to CRLF')
    cfg = ("; EOL=DOS configuration\r\n"
           "EOL = DOS\r\n"
           "PROFILE = STD\r\n")

    FIXTURE = b'ALPHA\nBETA\nGAMMA\n'

    def fixture(self, ctx, variant=None):
        return self.FIXTURE

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.snap('loaded')
        t.press('S', mods=['CTRL'])
        t.wait(3.0)
        t.snap('saved')
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        got = run.session.extract(run.dsk, 'DOC.TXT')
        want = b'ALPHA\r\nBETA\r\nGAMMA\r\n'
        checks = [
            Check('I4/saveeol', run.var('loaded', 'SAVEEOL') == 0,
                  'SAVEEOL = %s (expected 0)' % run.var('loaded', 'SAVEEOL')),
            Check('I4/content', got == want,
                  'document converted to DOS byte for byte' if got == want else
                  'got %r, want %r' % (got, want)),
            Check('I4/totlines', run.var('saved', 'TOTLINES') == 3,
                  'TOTLINES = %s (expected 3)' % run.var('saved', 'TOTLINES')),
        ]
        return checks


# --- U1  SINGLE-LINE UNDO AND REDO ------------------------------------


class U1UndoMod(Case):
    name = 'U1-undo-mod'
    desc = 'typing burst coalescing, single-line Undo (Ctrl+Z) and Redo (Ctrl+Shift+Z)'
    origin = ('Phase U1 Undo subsystem: coalescing input deltas in ring buffer, '
              'bidirectional symmetrical payload swap, restoring text and cursor')

    def fixture(self, ctx, variant=None):
        return crlf(['HELLO WORLD', 'SECOND LINE'])

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.snap('boot')
        # Type burst on Line 0 at col 0
        t.text('PREFIX ')                 # Line 0 becomes 'PREFIX HELLO WORLD', CURX=7
        t.snap('typed')
        # Undo typing burst (Ctrl+Z)
        t.press('Z', mods=['CTRL'])       # Restores 'HELLO WORLD', CURX=0
        t.snap('undone')
        # Redo typing burst (Ctrl+Shift+Z)
        t.press('Z', mods=['SHIFT', 'CTRL']) # Restores 'PREFIX HELLO WORLD', CURX=7
        t.snap('redone')
        # Undo again to return to original state
        t.press('Z', mods=['CTRL'])       # Restores 'HELLO WORLD', CURX=0
        t.snap('undone2')
        # Save to disk
        t.press('S', mods=['CTRL'])
        t.wait(3.0)
        t.snap('saved')
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        got = run.session.extract(run.dsk, 'DOC.TXT')
        want = crlf(['HELLO WORLD', 'SECOND LINE'])
        checks = [
            # Check boot initial state
            Check('U1/boot-ptrs',
                  run.var('boot', 'UNDOPTR') == 0 and run.var('boot', 'REDOPTR') == 0,
                  'UNDOPTR=0, REDOPTR=0 at boot'),
            # Check typing burst coalescing
            Check('U1/typed-state',
                  run.var('typed', 'CURX') == 7 and run.var('typed', 'UNDOPTR') != 0 and run.var('typed', 'REDOPTR') == 0,
                  'CURX=7, UNDOPTR active, REDOPTR=0 after typing'),
            # Check undo restores cursor and chain pointers
            Check('U1/undone-state',
                  run.var('undone', 'CURX') == 0 and run.var('undone', 'UNDOPTR') == 0 and run.var('undone', 'REDOPTR') != 0,
                  'CURX=0, UNDOPTR=0, REDOPTR active after Undo'),
            # Check redo restores cursor and chain pointers
            Check('U1/redone-state',
                  run.var('redone', 'CURX') == 7 and run.var('redone', 'UNDOPTR') != 0 and run.var('redone', 'REDOPTR') == 0,
                  'CURX=7, UNDOPTR active, REDOPTR=0 after Redo'),
            # Check second undo restores cursor
            Check('U1/undone2-curx',
                  run.var('undone2', 'CURX') == 0,
                  'CURX=0 after second Undo'),
            # Check disk content matches original text byte for byte
            Check('U1/content',
                  got == want,
                  'document matches original byte for byte after undo' if got == want else
                  'got %r, want %r' % (got, want)),
            # Check TOTLINES unchanged
            Check('U1/totlines',
                  run.var('saved', 'TOTLINES') == 2,
                  'TOTLINES = %s (expected 2)' % run.var('saved', 'TOTLINES')),
        ]
        return checks


# --- U2  LINE DELETION UNDO AND REDO ----------------------------------


class U2UndoDel(Case):
    name = 'U2-undo-del'
    desc = 'line deletion (Ctrl+Y), structural Undo (Ctrl+Z) and Redo (Ctrl+Shift+Z)'
    origin = ('Phase U2 Undo subsystem: structural line deletion undo/redo via NEWREC '
              'and LINEINS, preserving directory integrity and document lines')

    def fixture(self, ctx, variant=None):
        return crlf(['LINE 1: ALPHA', 'LINE 2: BETA', 'LINE 3: GAMMA'])

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.snap('boot')
        # Move down to Line 1 ('LINE 2: BETA')
        t.press('DOWN')
        t.snap('down')
        # Delete Line 1 with Ctrl+Y
        t.press('Y', mods=['CTRL'])
        t.snap('deleted')
        # Undo line deletion (Ctrl+Z) -> restores Line 1
        t.press('Z', mods=['CTRL'])
        t.snap('undone')
        # Redo line deletion (Ctrl+Shift+Z) -> deletes Line 1 again
        t.press('Z', mods=['SHIFT', 'CTRL'])
        t.snap('redone')
        # Undo line deletion again -> restores Line 1
        t.press('Z', mods=['CTRL'])
        t.snap('undone2')
        # Save to disk
        t.press('S', mods=['CTRL'])
        t.wait(3.0)
        t.snap('saved')
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        got = run.session.extract(run.dsk, 'DOC.TXT')
        want = crlf(['LINE 1: ALPHA', 'LINE 2: BETA', 'LINE 3: GAMMA'])
        checks = [
            # Check boot initial state
            Check('U2/boot-totlines',
                  run.var('boot', 'TOTLINES') == 3,
                  'TOTLINES=3 at boot'),
            # Check down moved to line 1
            Check('U2/down-docline',
                  run.var('down', 'DOCLINE') == 1,
                  'DOCLINE=1 after DOWN'),
            # Check line deletion reduced TOTLINES to 2
            Check('U2/deleted-totlines',
                  run.var('deleted', 'TOTLINES') == 2,
                  'TOTLINES=2 after Ctrl+Y'),
            # Check undo restored TOTLINES to 3 and DOCLINE to 1
            Check('U2/undone-totlines',
                  run.var('undone', 'TOTLINES') == 3 and run.var('undone', 'DOCLINE') == 1,
                  'TOTLINES=3, DOCLINE=1 after Undo'),
            # Check redo reduced TOTLINES to 2
            Check('U2/redone-totlines',
                  run.var('redone', 'TOTLINES') == 2,
                  'TOTLINES=2 after Redo'),
            # Check second undo restored TOTLINES to 3 and DOCLINE to 1
            Check('U2/undone2-totlines',
                  run.var('undone2', 'TOTLINES') == 3 and run.var('undone2', 'DOCLINE') == 1,
                  'TOTLINES=3, DOCLINE=1 after second Undo'),
            # Check saved document matches original fixture byte for byte
            Check('U2/content',
                  got == want,
                  'document matches original byte for byte after undo' if got == want else
                  'got %r, want %r' % (got, want)),
        ]
        return checks


# --- U3  LINE SPLIT UNDO AND REDO (ENTER) -----------------------------


class U3UndoSplit(Case):
    name = 'U3-undo-split'
    desc = 'line split (Enter), structural Undo (Ctrl+Z) and Redo (Ctrl+Shift+Z)'
    origin = ('Phase U3 Undo subsystem: structural line split undo/redo, merging '
              'lines back on Undo via LINEDEL/LINEWRT and re-splitting on Redo')

    def fixture(self, ctx, variant=None):
        return crlf(['FIRST LINE', 'SECOND LINE'])

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.snap('boot')
        # Move right 5 columns ('FIRST| LINE')
        t.press('RIGHT', repeat=5)
        t.snap('moved')
        # Press Enter: splits line 0 at col 5
        t.press('RETURN')
        t.snap('split')
        # Undo line split (Ctrl+Z) -> merges line 0 and line 1 back together
        t.press('Z', mods=['CTRL'])
        t.snap('undone')
        # Redo line split (Ctrl+Shift+Z) -> re-splits line 0
        t.press('Z', mods=['SHIFT', 'CTRL'])
        t.snap('redone')
        # Undo line split again -> merges lines back together
        t.press('Z', mods=['CTRL'])
        t.snap('undone2')
        # Save to disk
        t.press('S', mods=['CTRL'])
        t.wait(3.0)
        t.snap('saved')
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        got = run.session.extract(run.dsk, 'DOC.TXT')
        want = crlf(['FIRST LINE', 'SECOND LINE'])
        checks = [
            # Check boot initial state
            Check('U3/boot-totlines',
                  run.var('boot', 'TOTLINES') == 2,
                  'TOTLINES=2 at boot'),
            # Check moved to col 5
            Check('U3/moved-curx',
                  run.var('moved', 'CURX') == 5,
                  'CURX=5 after RIGHT x 5'),
            # Check split increased TOTLINES to 3, DOCLINE to 1, CURX to 0
            Check('U3/split-totlines',
                  run.var('split', 'TOTLINES') == 3 and run.var('split', 'DOCLINE') == 1,
                  'TOTLINES=3, DOCLINE=1 after Enter'),
            # Check undo restored TOTLINES to 2, DOCLINE to 0, CURX to 5
            Check('U3/undone-totlines',
                  run.var('undone', 'TOTLINES') == 2 and run.var('undone', 'DOCLINE') == 0 and run.var('undone', 'CURX') == 5,
                  'TOTLINES=2, DOCLINE=0, CURX=5 after Undo'),
            # Check redo increased TOTLINES to 3, DOCLINE to 1
            Check('U3/redone-totlines',
                  run.var('redone', 'TOTLINES') == 3 and run.var('redone', 'DOCLINE') == 1,
                  'TOTLINES=3, DOCLINE=1 after Redo'),
            # Check second undo restored TOTLINES to 2, DOCLINE to 0, CURX to 5
            Check('U3/undone2-totlines',
                  run.var('undone2', 'TOTLINES') == 2 and run.var('undone2', 'DOCLINE') == 0,
                  'TOTLINES=2, DOCLINE=0 after second Undo'),
            # Check saved document matches original fixture byte for byte
            Check('U3/content',
                  got == want,
                  'document matches original byte for byte after undo' if got == want else
                  'got %r, want %r' % (got, want)),
        ]
        return checks


# --- U4  LINE JOIN UNDO AND REDO (BACKSPACE AT COL 0) -----------------


class U4UndoJoin(Case):
    name = 'U4-undo-join'
    desc = 'line join (Backspace col 0), structural Undo (Ctrl+Z) and Redo (Ctrl+Shift+Z)'
    origin = ('Phase U3 Undo subsystem: line join undo/redo in WRAP_DEV, separating '
              'lines on Undo via NEWREC/LINEINS and re-joining on Redo')

    def fixture(self, ctx, variant=None):
        return crlf(['HELLO ', 'WORLD'])

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.snap('boot')
        # Move down to Line 1 at col 0
        t.press('DOWN')
        t.snap('down')
        # Backspace at col 0: joins line 1 into line 0 ('HELLO WORLD')
        t.press('BS')
        t.snap('joined')
        # Undo line join (Ctrl+Z) -> re-separates line 0 and line 1
        t.press('Z', mods=['CTRL'])
        t.snap('undone')
        # Redo line join (Ctrl+Shift+Z) -> re-joins line 1 into line 0
        t.press('Z', mods=['SHIFT', 'CTRL'])
        t.snap('redone')
        # Undo line join again -> re-separates lines
        t.press('Z', mods=['CTRL'])
        t.snap('undone2')
        # Save to disk
        t.press('S', mods=['CTRL'])
        t.wait(3.0)
        t.snap('saved')
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        got = run.session.extract(run.dsk, 'DOC.TXT')
        want = crlf(['HELLO ', 'WORLD'])
        checks = [
            # Check boot initial state
            Check('U4/boot-totlines',
                  run.var('boot', 'TOTLINES') == 2,
                  'TOTLINES=2 at boot'),
            # Check down moved to line 1
            Check('U4/down-docline',
                  run.var('down', 'DOCLINE') == 1 and run.var('down', 'CURX') == 0,
                  'DOCLINE=1, CURX=0 after DOWN'),
            # Check join reduced TOTLINES to 1, DOCLINE to 0, CURX to 6
            Check('U4/joined-totlines',
                  run.var('joined', 'TOTLINES') == 1 and run.var('joined', 'DOCLINE') == 0 and run.var('joined', 'CURX') == 6,
                  'TOTLINES=1, DOCLINE=0, CURX=6 after BS'),
            # Check undo restored TOTLINES to 2, DOCLINE to 0
            Check('U4/undone-totlines',
                  run.var('undone', 'TOTLINES') == 2 and run.var('undone', 'DOCLINE') == 0,
                  'TOTLINES=2, DOCLINE=0 after Undo'),
            # Check redo reduced TOTLINES to 1
            Check('U4/redone-totlines',
                  run.var('redone', 'TOTLINES') == 1 and run.var('redone', 'DOCLINE') == 0,
                  'TOTLINES=1, DOCLINE=0 after Redo'),
            # Check second undo restored TOTLINES to 2
            Check('U4/undone2-totlines',
                  run.var('undone2', 'TOTLINES') == 2,
                  'TOTLINES=2 after second Undo'),
            # Check saved document matches original fixture byte for byte
            Check('U4/content',
                  got == want,
                  'document matches original byte for byte after undo' if got == want else
                  'got %r, want %r' % (got, want)),
        ]
        return checks


# --- U5  UNDO WITH ACTIVE SELECTION (NO INVERTED CHARACTERS) ----------


class U5UndoSel(Case):
    name = 'U5-undo-sel'
    desc = 'undo cancels active selection cleanly without leaving inverted characters'
    origin = ('when text is selected and Ctrl+Z is pressed, ACTUNDO did not cancel '
              'the selection; REDRAW repainted clean text but SELDRAWN remained 1, '
              'so subsequent cursor movement un-XORed clean text and left inverted characters')
    fixture_name = 'DOC.TXT'

    def fixture(self, ctx, variant=None):
        return crlf(['Line 0', 'Line 1: Hello MSX', 'Line 2: MSX2 Screen 6 Text Editor'])

    def timeline(self, ctx, variant=None):
        t = Timeline()
        # 1. Type ABC on Line 0 to establish an undo transaction
        t.press('A')
        t.press('B')
        t.press('C')
        t.snap('typed')
        # 2. Navigate to Line 2, column 10 ('Screen') and select 3 chars ('ree')
        t.press('DOWN', repeat=2)
        t.press('RIGHT', repeat=10)
        t.press('RIGHT', mods=['SHIFT'], repeat=3)
        t.snap('selected')
        # 3. Undo previous typing with Ctrl+Z: must cancel selection cleanly
        t.press('Z', mods=['CTRL'])
        t.snap('undone')
        # 4. Move cursor right: must NOT un-XOR clean text or leave stray pixels
        t.press('RIGHT')
        t.snap('after_arrow', vram=True)
        # 5. Full pure REDRAW via Graph+Down then Graph+Up to compare screen
        t.press('DOWN', mods=['GRAPH'])
        t.press('UP', mods=['GRAPH'])
        t.snap('pure_redraw', vram=True)
        # 6. Save to disk
        t.press('S', mods=['CTRL'])
        t.wait(3.0)
        t.snap('saved')
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        got = run.session.extract(run.dsk, 'DOC.TXT')
        want = crlf(['Line 0', 'Line 1: Hello MSX', 'Line 2: MSX2 Screen 6 Text Editor'])
        v1 = run.blob('after_arrow', 'vram')
        v2 = run.blob('pure_redraw', 'vram')
        cursor = [
            (run.var('after_arrow', 'CURX'), run.var('after_arrow', 'CURY')),
            (run.var('pure_redraw', 'CURX'), run.var('pure_redraw', 'CURY')),
        ]
        diff = vram.diff(v1, v2, ignore_cells=cursor)
        checks = [
            # Check selection was active before undo
            Check('U5/sel-active',
                  run.var('selected', 'SELACT') == 1 and run.var('selected', 'SELDRAWN') == 1,
                  'SELACT=1, SELDRAWN=1 when selected'),
            # Check selection was cleanly cancelled by undo
            Check('U5/sel-cancelled',
                  run.var('undone', 'SELACT') == 0 and run.var('undone', 'SELDRAWN') == 0,
                  'SELACT=0, SELDRAWN=0 after Undo'),
            # Check no inverted characters or stray pixels in VRAM
            Check('U5/clean-vram',
                  not diff,
                  'screen identical to a full REDRAW, no inverted characters' if not diff else
                  '%d stray inverted pixels in VRAM' % len(diff)),
            # Check document matches fixture byte for byte
            Check('U5/content',
                  got == want,
                  'document matches original byte for byte after undo' if got == want else
                  'got %r, want %r' % (got, want)),
        ]
        return checks



class H24GoToLine(Case):
    name = 'H24-goto-line'
    desc = ('Ctrl+G opens a field, digits and Backspace edit it, ENTER jumps '
            'and clamps, ESC leaves everything where it was')
    origin = ('the first window with an input field.  Its viewport maths is '
              'shared with S2ED, where the band is 22 rows and not 24, so a '
              'literal or a SCRROWS here is wrong on the other target -- the '
              'round-3 defect class.')
    LINES = ['%03d GO TO LINE FIXTURE' % i for i in range(100)]
    WINX, WINY, WINW, WINH = 156, 70, 200, 72
    ROWSVIS = 24
    # The field box, in absolute pixels: rel (76, 32), 44 x 12
    FLDX, FLDY, FLDW, FLDH = 156 + 76, 70 + 32, 44, 12

    def fixture(self, ctx, variant=None):
        return crlf(self.LINES)

    def digits(self, t, s):
        for ch in s:
            t.press(ch)

    def timeline(self, ctx, variant=None):
        """Every step opens with a wait, and that is not padding.

        A snapshot stops emulated time while Tcl reads its sixty variables,
        and a keystroke whose down AND up both land inside that window is
        never sampled by the keyboard ISR -- it simply does not happen.  The
        drift accumulates across a long case: measured here, the ninth
        dialog's RETURN was swallowed while a second one right after it
        worked perfectly.  The wait gives each step a clean frame to start on.
        """
        t = Timeline()
        t.snap('boot', vram=True)

        # 1. Ctrl+G opens the dialog with an empty field
        t.wait(1.0)
        t.press('G', mods=['CTRL'])
        t.snap('open', vram=True, at='WINPOLL')

        # 2. Two digits land in the field
        t.wait(1.0)
        self.digits(t, '42')
        t.snap('typed', vram=True, at='WINPOLL')

        # 3. ENTER jumps and centres
        t.wait(1.0)
        t.press('RETURN')
        t.snap('jumped', vram=True)

        # 4. ESC leaves everything alone
        t.wait(1.0)
        t.press('G', mods=['CTRL'])
        t.wait(1.0)
        self.digits(t, '88')
        t.press('ESC')
        t.snap('cancel', vram=True)

        # 5. Past the end clamps to the last line
        t.wait(1.0)
        t.press('G', mods=['CTRL'])
        t.wait(1.0)
        self.digits(t, '999')
        t.press('RETURN')
        t.snap('high')

        # 6. A line inside the viewport must not move it.  It has to be one
        #    that centring WOULD move, or the check cannot tell them apart.
        #    Line 90 is NOT such a line: centring it lands on the same TOPLINE
        #    the clamp already forced.  Line 85 is.
        t.wait(1.0)
        t.press('G', mods=['CTRL'])
        t.wait(1.0)
        self.digits(t, '85')
        t.press('RETURN')
        t.snap('nearby')

        # 7. Zero clamps to the first line
        t.wait(1.0)
        t.press('G', mods=['CTRL'])
        t.wait(1.0)
        t.press('0')
        t.press('RETURN')
        t.snap('low')

        # 8. SPACE is not an accept while the field has the focus:
        #    7, SPACE, 7 must read 77, not jump on the space
        t.wait(1.0)
        t.press('G', mods=['CTRL'])
        t.wait(1.0)
        t.press('7')
        t.press('SPACE')
        t.press('7')
        t.press('RETURN')
        t.snap('space')

        # 9. Backspace really removes: 5, 0, BS -> line 5, not 50
        t.wait(1.0)
        t.press('G', mods=['CTRL'])
        t.wait(1.0)
        self.digits(t, '50')
        t.press('BS')
        t.press('RETURN')
        t.snap('backspace')

        # 10. ENTER on an empty field cancels
        t.wait(1.0)
        t.press('G', mods=['CTRL'])
        t.wait(1.0)
        t.press('RETURN')
        t.snap('empty')

        # 11. The Edit menu reaches the same dialog
        t.wait(1.0)
        t.press('F2')
        t.wait(1.0)
        t.press('G')
        t.snap('menu', at='WINPOLL')
        t.wait(1.0)
        t.press('ESC')
        t.snap('done')
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        v_boot = run.blob('boot', 'vram')
        v_open = run.blob('open', 'vram')
        v_typed = run.blob('typed', 'vram')
        v_jump = run.blob('jumped', 'vram')
        v_cancel = run.blob('cancel', 'vram')
        if None in (v_boot, v_open, v_typed, v_jump, v_cancel):
            return [Check('H24/dump', False, 'missing VRAM dump')]
        half = self.ROWSVIS // 2
        last = len(self.LINES) - 1
        maxtop = len(self.LINES) - self.ROWSVIS

        geom = tuple(run.var('open', v)
                     for v in ('WINX', 'WINY', 'WINW', 'WINH'))
        checks = [
            Check('H24/open',
                  run.var('open', 'WINACTV') == 1 and
                  geom == (self.WINX, self.WINY, self.WINW, self.WINH) and
                  run.var('open', 'INPLEN') == 0,
                  'Ctrl+G opens the Go to Line window with an empty field '
                  '(WINACTV=%s, geometry %s, INPLEN=%s)'
                  % (run.var('open', 'WINACTV'), geom,
                     run.var('open', 'INPLEN'))),
            Check('H24/displayed', v_open != v_boot,
                  'the screen changes while the dialog is open'),
        ]

        # Typing repaints the field box and nothing else.
        fl = vram.TEXT_FIRST_LINE
        changed = [(x, y) for (x, y) in vram.diff(v_open, v_typed)
                   if not (self.FLDX <= x < self.FLDX + self.FLDW and
                           self.FLDY <= y < self.FLDY + self.FLDH)]
        inside = [(x, y) for (x, y) in vram.diff(v_open, v_typed)
                  if (self.FLDX <= x < self.FLDX + self.FLDW and
                      self.FLDY <= y < self.FLDY + self.FLDH)]
        checks.append(Check('H24/field',
                            inside and not changed and
                            run.var('typed', 'INPLEN') == 2,
                            'two digits repaint the field box and only it '
                            '(%d pixels, INPLEN=%s)'
                            % (len(inside), run.var('typed', 'INPLEN'))
                            if not changed else
                            'pixels changed outside the field: %s'
                            % changed[:6]))

        def where(label):
            return (run.var(label, 'DOCLINE'), run.var(label, 'TOPLINE'),
                    run.var(label, 'CURY'), run.var(label, 'CURX'))

        got = where('jumped')
        exp = (41, 41 - half, half, 0)
        checks.append(Check('H24/centred', got == exp,
                            'line 42 lands centred on the band '
                            '(DOCLINE,TOPLINE,CURY,CURX) = %s' % (got,)
                            if got == exp else '%s, expected %s' % (got, exp)))

        cursor = [(run.var('jumped', 'CURX') or 0,
                   run.var('jumped', 'CURY') or 0)]
        d = vram.diff(v_jump, v_cancel, ignore_cells=cursor)
        checks.append(Check('H24/cancel', not d and where('cancel') == exp,
                            'ESC changes nothing, on screen or in the document'
                            if not d else '%d pixels differ' % len(d)))

        for label, want in (('high', (last, maxtop, last - maxtop, 0)),
                            ('nearby', (84, maxtop, 84 - maxtop, 0)),
                            ('low', (0, 0, 0, 0)),
                            ('space', (76, 76 - half, half, 0)),
                            ('backspace', (4, 0, 4, 0)),
                            ('empty', (4, 0, 4, 0))):
            got = where(label)
            checks.append(Check('H24/%s' % label, got == want,
                                '%s -> %s' % (label, (got,))
                                if got == want else
                                '%s, expected %s' % (got, want)))

        mgeom = tuple(run.var('menu', v)
                      for v in ('WINX', 'WINY', 'WINW', 'WINH'))
        checks.append(Check('H24/menu',
                            mgeom == (self.WINX, self.WINY,
                                      self.WINW, self.WINH),
                            'Edit > Go to Line opens the same window (%s)'
                            % (mgeom,)))
        return checks


# --- H25  FIND & REPLACE ----------------------------------------------


class H25FindReplace(Case):
    name = 'H25-find-replace'
    desc = ('Ctrl+F opens Find & Replace dialog, searches forward, finds next/prev '
            'via Ctrl+L/Ctrl+R, replaces match, undoes replace via Ctrl+Z, '
            'and Replace All replaces across document with atomic Undo')
    origin = 'Resident Find & Replace engine: SEARCH.Z8A and DOFIND modal dialog'
    LINES = [
        'LINE 00 START OF DOC',
        'LINE 01 NORMAL TEXT',
        'LINE 02 FIRST TARGET HERE',
        'LINE 03 MIDDLE SECTION',
        'LINE 04 ANOTHER ROW',
        'LINE 05 SECOND TARGET HERE',
        'LINE 06 TAIL OF DOCUMENT',
    ]
    variants = ('replace', 'undo')
    LINES_REPLACED = [
        'LINE 00 START OF DOC',
        'LINE 01 NORMAL TEXT',
        'LINE 02 FIRST expanded HERE',
        'LINE 03 MIDDLE SECTION',
        'LINE 04 ANOTHER ROW',
        'LINE 05 SECOND expanded HERE',
        'LINE 06 TAIL OF DOCUMENT',
    ]
    WINX, WINY, WINW, WINH = 108, 56, 260, 74

    def fixture(self, ctx, variant=None):
        return crlf(self.LINES)

    def chars(self, t, s):
        for ch in s:
            t.press(ch)

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.snap('boot', vram=True)

        # 1. Ctrl+F opens the Find & Replace window
        t.wait(1.0)
        t.press('F', mods=['CTRL'])
        t.snap('open', vram=True, at='WINPOLL')

        # 2. Type search pattern "TARGET"
        t.wait(1.0)
        self.chars(t, 'TARGET')
        t.snap('typed', at='WINPOLL')

        # 3. Press ENTER on Find field -> immediate Find Next
        t.wait(1.0)
        t.press('RETURN')
        t.wait(1.0)
        t.snap('found1')

        # 4. Ctrl+L -> Find Next (should jump to Line 5)
        t.wait(1.0)
        t.press('L', mods=['CTRL'])
        t.wait(1.0)
        t.snap('found2')

        # 5. Ctrl+R -> Find Previous (should jump back to Line 2)
        t.wait(1.0)
        t.press('R', mods=['CTRL'])
        t.wait(1.0)
        t.snap('found_prev')

        # 6. Replace test: open dialog, TAB to Replace, type "REPL", TAB to [Repl], press RETURN
        t.wait(1.0)
        t.press('F', mods=['CTRL'])
        t.wait(1.0)
        t.press('TAB')
        t.wait(0.5)
        self.chars(t, 'EXPANDED')
        t.press('TAB')
        t.wait(0.5)
        t.snap('match_case', vram=True, at='WINPOLL')
        t.press('TAB')
        t.wait(0.2)
        t.press('TAB')
        t.wait(0.5)
        t.snap('repl_ready', at='WINPOLL')
        t.press('RETURN')
        t.wait(1.0)
        t.snap('after_repl')

        # 7. Undo the replacement
        t.wait(1.0)
        t.press('Z', mods=['CTRL'])
        t.wait(1.0)
        t.snap('after_undo')

        # 8. Replace All test: open dialog, TAB 5 times to reach [All], press RETURN
        t.wait(1.0)
        t.press('F', mods=['CTRL'])
        t.wait(1.0)
        t.press('TAB')
        t.press('TAB')
        t.press('TAB')
        t.press('TAB')
        t.press('TAB')
        t.wait(0.5)
        t.snap('all_ready', at='WINPOLL')
        t.press('RETURN')
        t.wait(1.0)
        t.snap('after_all')
        if variant == 'replace':
            # Save to disk to verify expanded lines
            t.wait(1.0)
            t.press('S', mods=['CTRL'])
            t.wait(2.0)
            t.snap('saved')
        else:
            # 9. Single Undo reverts all replacements
            t.wait(1.0)
            t.press('Z', mods=['CTRL'])
            t.wait(1.0)
            t.snap('after_undo_all')

            # 10. Save to verify disk lines
            t.wait(1.0)
            t.press('S', mods=['CTRL'])
            t.wait(2.0)
            t.snap('saved')
        return t

    def verify(self, ctx, runs):
        run = runs['replace']
        v_boot = run.blob('boot', 'vram')
        v_open = run.blob('open', 'vram')
        v_mc = run.blob('match_case', 'vram')
        checks = []

        geom = tuple(run.var('open', v)
                     for v in ('WINX', 'WINY', 'WINW', 'WINH'))
        checks.append(Check('H25/open',
                            run.var('open', 'WINACTV') == 1 and
                            geom == (self.WINX, self.WINY, self.WINW, self.WINH) and
                            v_open != v_boot,
                            'Ctrl+F opens Find & Replace dialog (geometry %s, WINACTV=1)'
                            % (geom,)))

        # Side borders (left x=108, right x=367) intact in COL_UI
        left_ok = all(vram.pixel(v_open, self.WINX, y, first_line=vram.TEXT_FIRST_LINE) == vram.COL_UI
                      for y in range(self.WINY + 1, self.WINY + self.WINH - 1))
        right_ok = all(vram.pixel(v_open, self.WINX + self.WINW - 1, y, first_line=vram.TEXT_FIRST_LINE) == vram.COL_UI
                       for y in range(self.WINY + 1, self.WINY + self.WINH - 1))
        checks.append(Check('H25/borders',
                            left_ok and right_ok,
                            'Vertical side borders intact in COL_UI (left=%s, right=%s)'
                            % (left_ok, right_ok)))

        # Active field 0 box (COL_UI) and solid block caret in COL_HI
        fld_bg_ok = all(vram.pixel(v_open, x, self.WINY + 18, first_line=vram.TEXT_FIRST_LINE) in (vram.COL_UI, vram.COL_HI)
                        for x in range(self.WINX + 64, self.WINX + 64 + 116))
        caret_ok = all(vram.pixel(v_open, self.WINX + 66, y, first_line=vram.TEXT_FIRST_LINE) == vram.COL_HI
                       for y in range(self.WINY + 16, self.WINY + 24))
        checks.append(Check('H25/field-focus',
                            fld_bg_ok and caret_ok,
                            'Active input field rendered with COL_UI box and solid COL_HI caret (box=%s, caret=%s)'
                            % (fld_bg_ok, caret_ok)))

        # Match case checkbox rendered with solid COL_HI block on focus
        mc_box_ok = all(vram.pixel(v_mc, x, y, first_line=vram.TEXT_FIRST_LINE) == vram.COL_HI
                        for x in range(self.WINX + 90, self.WINX + 90 + 6)
                        for y in range(self.WINY + 32, self.WINY + 32 + 8))
        checks.append(Check('H25/match-case-focus',
                            run.var('match_case', 'FNDFOC') == 2 and mc_box_ok,
                            'Match case checkbox rendered with solid COL_HI block on focus (FNDFOC=%s, box=%s)'
                            % (run.var('match_case', 'FNDFOC'), mc_box_ok)))

        checks.append(Check('H25/typed',
                            run.var('typed', 'SRCHLEN') == 6,
                            'SRCHLEN = %s (expected 6)'
                            % (run.var('typed', 'SRCHLEN'),)))

        pos1 = (run.var('found1', 'DOCLINE'), run.var('found1', 'CURX'))
        sel1 = (run.var('found1', 'SELACT'), run.var('found1', 'SELANCX'))
        checks.append(Check('H25/found1',
                            pos1 == (2, 20) and sel1 == (1, 14),
                            'First match found at line 2 col 14..20 (pos=%s, sel=%s)'
                            % (pos1, sel1)))

        pos2 = (run.var('found2', 'DOCLINE'), run.var('found2', 'CURX'))
        sel2 = (run.var('found2', 'SELACT'), run.var('found2', 'SELANCX'))
        checks.append(Check('H25/found2',
                            pos2 == (5, 21) and sel2 == (1, 15),
                            'Ctrl+L finds next match at line 5 col 15..21 (pos=%s, sel=%s)'
                            % (pos2, sel2)))

        pos_prev = (run.var('found_prev', 'DOCLINE'), run.var('found_prev', 'CURX'))
        sel_prev = (run.var('found_prev', 'SELACT'), run.var('found_prev', 'SELANCX'))
        checks.append(Check('H25/found-prev',
                            pos_prev == (2, 20) and sel_prev == (1, 14),
                            'Ctrl+R finds previous match at line 2 col 14..20 (pos=%s, sel=%s)'
                            % (pos_prev, sel_prev)))

        checks.append(Check('H25/replace-modified',
                            run.var('after_repl', 'MODIFIED') == 0xFF,
                            'Replace marks document modified (MODIFIED=%s)'
                            % (run.var('after_repl', 'MODIFIED'),)))

        checks.append(Check('H25/undo-repl',
                            run.var('after_undo', 'DOCLINE') == 2,
                            'Ctrl+Z returns to line 2 (DOCLINE=%s)'
                            % (run.var('after_undo', 'DOCLINE'),)))

        checks.append(Check('H25/replace-all',
                            run.var('after_all', 'RPLCNT') == 2,
                            'Replace All completed with RPLCNT = %s'
                            % (run.var('after_all', 'RPLCNT'),)))

        saved_repl = disk_lines(run)
        checks.append(Check('H25/replace-expand',
                            saved_repl == self.LINES_REPLACED,
                            'Replacement expands lines cleanly without corruption'
                            if saved_repl == self.LINES_REPLACED else
                            'document mismatch after Replace: %r' % (saved_repl,)))

        saved_undo = disk_lines(runs['undo'])
        checks.append(Check('H25/undo-all-content',
                            saved_undo == self.LINES,
                            'Single Ctrl+Z atomically reverts all replacements'
                            if saved_undo == self.LINES else
                            'document mismatch after Undo All: %r' % (saved_undo,)))

        return checks



# --- H26  FIND WITH THE MATCH ON THE CURRENT LINE ---------------------


class H26FindCurrentLine(Case):
    name = 'H26-find-current-line'
    desc = ('find lands right when the match is on the CURRENT line: forward, '
            'forward after wrap, backward, backward after wrap -- and the '
            'match stays XOR highlighted on screen')
    origin = ('2026-09-24, from the keyboard on BOTH targets: SRCHFWD and '
              'SRCHBWD reached .MATCH/.BMATCH straight from SCANLNF/SCANLNB '
              'on the current-line paths, and those leave HL pointing into '
              'WORKBUF -- DOCLINE became WORKBUF+1+C, the status bar read '
              '"Ln 20960/00031" and the cursor was painted on the status '
              'row.  H25 only ever matched on OTHER lines (.MATPOP), which '
              'is why the suite was green.')
    LINES = ['AAA MSX BBB MSX CCC']

    def fixture(self, ctx, variant=None):
        return crlf(self.LINES)

    def chars(self, t, s):
        for ch in s:
            t.press(ch)

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.snap('boot', vram=True)

        # 1. Ctrl+F, type MSX, ENTER: match on the CURRENT line (step 1)
        t.wait(1.0)
        t.press('F', mods=['CTRL'])
        t.wait(1.0)
        self.chars(t, 'MSX')
        t.wait(0.5)
        t.press('RETURN')
        t.wait(1.0)
        t.snap('found1', vram=True)

        # 2. Ctrl+L: second match, still the current line (step 1 again)
        t.wait(1.0)
        t.press('L', mods=['CTRL'])
        t.wait(1.0)
        t.snap('found2')

        # 3. Ctrl+L: wraps top and re-finds the first match (.LSTCHK)
        t.wait(1.0)
        t.press('L', mods=['CTRL'])
        t.wait(1.0)
        t.snap('found3')

        # 4. Ctrl+R: wraps bottom and re-finds the second match (.BLSTCHK)
        t.wait(1.0)
        t.press('R', mods=['CTRL'])
        t.wait(1.0)
        t.snap('found4')

        # 5. Ctrl+R: previous match on the current line (backward step 1)
        t.wait(1.0)
        t.press('R', mods=['CTRL'])
        t.wait(1.0)
        t.snap('found5')
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        checks = []
        want = {'found1': 4, 'found2': 12, 'found3': 4, 'found4': 12,
                'found5': 4}
        for label, col in want.items():
            got = tuple(run.var(label, v) for v in
                        ('DOCLINE', 'CURX', 'SELANCL', 'SELANCX', 'SELACT',
                         'TOPLINE', 'CURY'))
            ok = got == (0, col + 3, 0, col, 1, 0, 0)
            checks.append(Check('H26/%s' % label, ok,
                                'match selected at line 0 col %d..%d, '
                                'viewport and cursor in place' % (col, col + 3)
                                if ok else
                                '(DOCLINE, CURX, SELANCL, SELANCX, SELACT, '
                                'TOPLINE, CURY) = %s' % (got,)))

        # The match is highlighted: cells 4..6 XOR inverted against boot,
        # cells 8..10 untouched (cursor sits on cell 7, out of both rects).
        v_boot = run.blob('boot', 'vram')
        v_found = run.blob('found1', 'vram')
        hl_ok = clean_ok = False
        if v_boot is not None and v_found is not None:
            def px(buf, x, y):
                return vram.pixel(buf, x, y,
                                  first_line=vram.TEXT_FIRST_LINE)
            hl_ok = all(px(v_found, x, y) == (px(v_boot, x, y) ^ 1)
                        for y in range(8, 16) for x in range(40, 58))
            clean_ok = all(px(v_found, x, y) == px(v_boot, x, y)
                           for y in range(8, 16) for x in range(64, 82))
        checks.append(Check('H26/highlight',
                            hl_ok and clean_ok,
                            'match cells XOR highlighted, neighbours clean'
                            if hl_ok and clean_ok else
                            'highlight=%s, neighbours-clean=%s'
                            % (hl_ok, clean_ok)))
        return checks


# --- H27  VI EX COMMAND LINE CONSOLE ---------------------------------


class H27ViEx(Case):
    name = 'H27-vi-ex'
    desc = 'VI ex mode console (:): jump to line, save as, error handling, force quit'
    origin = '2026-09-24, VI command line console in status bar'
    cfg = """; generated by the S6ED test harness
PROFILE=VI
WRAP=DEV
MARKUP=OFF
CLOCK=0
TABWIDTH=4
EOL=AUTO
AUTOALIGN=OFF
THEME=DARK
"""
    LINES = ['LINE %04d TEST' % (i + 1) for i in range(50)]

    def fixture(self, ctx, variant=None):
        return crlf(self.LINES)

    def key_for(self, ch):
        if ch == ':':
            return (';', ['SHIFT'])
        if ch == '!':
            return ('1', ['SHIFT'])
        if ch == ' ':
            return ('SPACE', [])
        return (ch.upper(), [])

    def type_str(self, t, s):
        for ch in s:
            k, mods = self.key_for(ch)
            t.press(k, mods=mods)

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.snap('boot')

        # 1. Jump to line 42 via :42 + RETURN
        t.wait(1.0)
        self.type_str(t, ':42')
        t.press('RETURN')
        t.wait(1.0)
        t.snap('jumped')

        # 2. Save file as OUT.TXT via :w OUT.TXT + RETURN
        t.wait(1.0)
        self.type_str(t, ':w OUT.TXT')
        t.press('RETURN')
        t.wait(2.0)
        t.snap('saved_as')

        # 3. Modify document in Insert mode: i + X + ESC
        t.wait(1.0)
        self.type_str(t, 'i')
        self.type_str(t, 'X')
        t.press('ESC')
        t.wait(1.0)
        t.snap('modified')

        # 4. Try :q (must be rejected because modified)
        t.wait(1.0)
        self.type_str(t, ':q')
        t.press('RETURN')
        t.wait(1.0)
        t.snap('rejected')

        # 5. Force quit with :q!
        t.wait(1.0)
        self.type_str(t, ':q!')
        t.snap('exit', at='TERM.TERMDON')
        t.press('RETURN')
        t.wait(1.0)
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        checks = []

        # Boot state: KMAPID = 3 (VI), status bar right-aligned with [NORM]
        stat_raw = run.snaps.get('boot', {}).get('STATBUF', [])
        stat_str = ''.join(chr(c) for c in stat_raw) if stat_raw else ''
        checks.append(Check('H27/boot-vi',
                            run.var('boot', 'KMAPID') == 3 and ('[NORM]' in stat_str or '[N]' in stat_str),
                            'KMAPID=3 and mode in status bar'
                            if (run.var('boot', 'KMAPID') == 3 and ('[NORM]' in stat_str or '[N]' in stat_str)) else
                            'KMAPID=%s, stat=%r' % (run.var('boot', 'KMAPID'), stat_str)))

        # 1. :42 jump: DOCLINE = 41 (0-based line 42), CURX = 0
        doc42 = run.var('jumped', 'DOCLINE')
        checks.append(Check('H27/goto-line',
                            doc42 == 41 and run.var('jumped', 'CURX') == 0,
                            ':42 jumped to DOCLINE 41 (got %s)' % doc42))

        # 2. :w OUT.TXT: file saved on disk and [SAVED] shown
        got_out = run.session.extract(run.dsk, 'OUT.TXT')
        stat_sav = run.snaps.get('saved_as', {}).get('STATBUF', [])
        stat_sav_str = ''.join(chr(c) for c in stat_sav) if stat_sav else ''
        checks.append(Check('H27/save-as',
                            got_out is not None and len(got_out) > 0 and '[SAVED]' in stat_sav_str,
                            ':w OUT.TXT saved file on disk and displayed [SAVED]'))

        # 3. Modified check
        checks.append(Check('H27/modified',
                            run.var('modified', 'MODIFIED') == 0xFF,
                            'document modified after typing'))

        # 4. Rejected :q check: MODIFIED still 0xFF, error in STATMSG
        stat_rej = run.snaps.get('rejected', {}).get('STATBUF', [])
        stat_rej_str = ''.join(chr(c) for c in stat_rej) if stat_rej else ''
        checks.append(Check('H27/quit-rejected',
                            run.var('rejected', 'MODIFIED') == 0xFF and
                            'No write' in stat_rej_str,
                            ':q rejected with message on dirty buffer'
                            if 'No write' in stat_rej_str else
                            'stat=%r' % stat_rej_str))

        # 5. Force quit :q! cleanly reached exit
        checks.append(Check('H27/quit-force',
                            'exit' in run.snaps,
                            ':q! exited cleanly'))
        return checks


# --- H29  PROGRAM HOME DIRECTORY -------------------------------------


class H29HomePath(HomePathCase):
    name = 'H29-home-path'
    desc = ('S6ED run through PATH from another directory finds S6ED.DAT and '
            'S6ED.FNT next to itself and layers the local CFG over the general')
    origin = ('DAT, FNT and CFG were opened by bare name, i.e. in the current '
              'directory: S6ED in A:\\TOOLS on the PATH, run from C:\\DEV, '
              'aborted at boot with "S6ED.DAT not found" and fell back to the '
              'ROM font.  Every test disk had everything in the root, so '
              'nothing ever noticed')

    def verify(self, ctx, runs):
        return self.home_checks(ctx, runs, 'H29', Check)


# --- B5  THE SHIPPED DISK --------------------------------------------


class B5ShippedDisk(ShippedDiskCase):
    name = 'B5-shipped-disk'
    desc = 'S6ED.DSK as make dsk ships it: \\TOOLS on the PATH, run from \\DEV'
    origin = ('the disks carried everything in the root, which is why DAT, FNT '
              'and CFG being opened in the current directory went unnoticed')
    dsk_target = 'dsk'
    dsk_name = 'S6ED.DSK'
    doc_host = 'TEST.TXT'

    def verify(self, ctx, runs):
        return self.shipped_checks(ctx, runs, 'B5', Check)


# --- H30  FILE > NEW ASKS BEFORE DISCARDING ---------------------------


class H30NewDocument(Case):
    name = 'H30-new-document'
    desc = ('Ctrl+N and File > New: a clean document is replaced at once, a '
            'modified one only after YES in the New Document dialog')
    origin = ('File > New reset the buffer without asking even with unsaved '
              'changes, and Ctrl+N was bound in no keymap')
    variants = ('clean', 'dirty-no', 'dirty-yes', 'menu')
    LINES = 5
    TAG = 'H30'

    def fixture(self, ctx, variant=None):
        return crlf(numbered(self.LINES))

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.snap('boot')
        if variant != 'clean' and variant != 'menu':
            t.text('X')                       # MODIFIED = 1
            t.wait(0.5)
            t.snap('typed')
        if variant == 'menu':
            t.press('F1')                     # File menu, New preselected
            t.press('RETURN')
        else:
            t.press('N', mods=['CTRL'])
        if variant in ('dirty-no', 'dirty-yes'):
            t.snap('asked', at='WINPOLL')
            t.press('N' if variant == 'dirty-no' else 'Y')
        t.wait(1.0)
        t.snap('after')
        return t

    def verify(self, ctx, runs):
        checks = []
        for variant, run in sorted(runs.items()):
            v = '%s/%s' % (self.TAG, variant)
            lines = run.var('after', 'TOTLINES')
            name = asciiz(run, 'after', 'FILENAME')
            mod = run.var('after', 'MODIFIED')
            if variant == 'dirty-no':
                checks.append(Check('%s/asked' % v,
                                    run.var('asked', 'WINACTV') == 1,
                                    'dialog open (WINACTV %s)'
                                    % run.var('asked', 'WINACTV')))
                checks.append(Check('%s/kept' % v,
                                    lines == self.LINES and mod == 0xFF and
                                    name == 'DOC.TXT',
                                    'NO keeps the document: TOTLINES %s, '
                                    'MODIFIED %s, FILENAME %r'
                                    % (lines, mod, name)))
                continue
            if variant == 'dirty-yes':
                checks.append(Check('%s/asked' % v,
                                    run.var('asked', 'WINACTV') == 1,
                                    'dialog open (WINACTV %s)'
                                    % run.var('asked', 'WINACTV')))
            checks.append(Check('%s/fresh' % v,
                                lines == 1 and mod == 0 and name == '' and
                                run.var('after', 'WINACTV') == 0,
                                'new empty document: TOTLINES %s, MODIFIED '
                                '%s, FILENAME %r, WINACTV %s'
                                % (lines, mod, name,
                                   run.var('after', 'WINACTV'))))
        return checks


# --- H31  :e KEEPS THE DOCUMENT WHEN IT CANNOT LOAD --------------------


class H31EditOpen(Case):
    name = 'H31-edit-open'
    desc = (':e OTHER loads it; :e on a missing file opens an empty document '
            'under that name; :e on an oversized file keeps the current one; '
            ':e! reloads with MODIFIED cleared')
    origin = ('FILELOAD reset the buffer before opening the file, and :e '
              'copied the new name into FILENAME before loading: a refused '
              ':e left the old document under the new name, so Ctrl+S would '
              'overwrite the file that had just been refused')
    cfg = H27ViEx.cfg
    variants = ('ok', 'noexist', 'toolarge', 'force')
    LINES = 5
    OTHER = crlf(['OTHER %d' % i for i in range(1, 4)])
    BIG = crlf([('LINE %05d ' % i) + ('X' * 68) for i in range(1, 151)])

    def fixture(self, ctx, variant=None):
        return crlf(numbered(self.LINES))

    def disk_files(self, ctx, variant=None):
        files = Case.disk_files(self, ctx, variant)
        files['OTHER.TXT'] = self.OTHER
        files['BIG.TXT'] = self.BIG
        return files

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.snap('boot')
        t.wait(1.0)
        if variant == 'force':
            H27ViEx.type_str(self, t, 'dd')   # MODIFIED = 1
            t.wait(0.5)
            t.snap('dirty')
        cmd = {'ok': ':e OTHER.TXT', 'noexist': ':e NEW.TXT',
               'toolarge': ':e BIG.TXT', 'force': ':e! OTHER.TXT'}[variant]
        H27ViEx.type_str(self, t, cmd)
        t.press('RETURN')
        t.wait(2.0)
        t.snap('after')
        return t

    def key_for(self, ch):
        return H27ViEx.key_for(self, ch)

    def verify(self, ctx, runs):
        checks = []
        for variant, run in sorted(runs.items()):
            v = 'H31/%s' % variant
            lines = run.var('after', 'TOTLINES')
            name = asciiz(run, 'after', 'FILENAME')
            mod = run.var('after', 'MODIFIED')
            msg = asciiz(run, 'after', 'STATMSG')
            err = run.var('after', 'LOADERR')
            want = {
                'ok': (3, 'OTHER.TXT', 0, 0),
                'force': (3, 'OTHER.TXT', 0, 0),
                'noexist': (1, 'NEW.TXT', 0, 0),
                'toolarge': (self.LINES, 'DOC.TXT', None, 1),
            }[variant]
            got = (lines, name, mod if want[2] is not None else None, err)
            checks.append(Check('%s/state' % v, got == want,
                                'TOTLINES, FILENAME, MODIFIED, LOADERR = %s '
                                '(want %s)' % (got, want)))
            if variant == 'force':
                checks.append(Check('%s/was-dirty' % v,
                                    run.var('dirty', 'MODIFIED') == 0xFF,
                                    'dd set MODIFIED before :e! (%s)'
                                    % run.var('dirty', 'MODIFIED')))
            if variant == 'noexist':
                checks.append(Check('%s/message' % v, msg == '[NEW FILE]',
                                    'status message %r' % msg))
        return checks


# --- H32  SAVE WITH NO NAME SAYS SO -----------------------------------


class H32SaveNoName(Case):
    name = 'H32-save-noname'
    desc = 'Ctrl+S on a document with no name reports it instead of doing nothing'
    origin = ('FILESAVE with an empty FILENAME returned SCF in silence, so '
              'Ctrl+S after File > New looked like a save that never happened')

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.snap('boot')
        t.text('ABC')
        t.wait(0.5)
        t.press('S', mods=['CTRL'])
        t.wait(1.0)
        t.snap('after')
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        msg = asciiz(run, 'after', 'STATMSG')
        stat = ''.join(chr(c) for c in
                       run.snaps.get('after', {}).get('STATBUF', []))
        return [
            Check('H32/no-name', asciiz(run, 'boot', 'FILENAME') == '',
                  'started with no file name (%r)'
                  % asciiz(run, 'boot', 'FILENAME')),
            Check('H32/message', msg == '[NO FILE NAME]' and
                  '[NO FILE NAME]' in stat,
                  'STATMSG %r, status bar shows it: %s'
                  % (msg, '[NO FILE NAME]' in stat)),
            Check('H32/still-modified', run.var('after', 'MODIFIED') == 0xFF,
                  'MODIFIED %s: nothing was saved' % run.var('after', 'MODIFIED')),
        ]


# --- H33  A FULL PATH AS THE FILE NAME ---------------------------------


class H33LongPath(LongPathCase):
    name = 'H33-long-path'
    desc = ('a 48-character path on the command line is loaded, saved back '
            'to the same place, and the menu bar shows only NOTES.TXT')
    origin = ('FILENAME was 40 bytes and CHKFILE copied the argument into it '
              'unbounded; the menu bar printed the whole string, so a path '
              'would have overrun it')

    def boot_vram(self):
        return 'menu'

    def verify(self, ctx, runs):
        run = one(runs)
        checks = self.path_checks(ctx, run, 'H33', Check, asciiz)
        buf = run.blob('boot', 'menu')
        font = font_of(ctx)
        if buf is None or font is None:
            return checks + [Check('H33/menu-name', False, 'no row 0 dump')]
        x0 = 458 - 6 * len(self.NAME)          # right-aligned before separator and clock
        bad = [i for i, ch in enumerate(self.NAME)
               if vram.ink_mask(buf, x0 + 6 * i, 0, w=6, h=8,
                                ground=vram.COL_UI) !=
               vram.glyph_mask(font, ch, width=6)]
        stray = sum(sum(r) for r in vram.ink_mask(buf, 236, 0, w=x0 - 236,
                                                  h=8, ground=vram.COL_UI))
        checks.append(Check('H33/menu-name', not bad and stray == 0,
                            'row 0 shows %s right-aligned and nothing of the '
                            'path to its left (%d glyphs off, %d stray px)'
                            % (self.NAME, len(bad), stray)))
        return checks


# --- H34  THE FILE BROWSER (OPEN) ------------------------------------


BRWESZ = 19                     # CONST_CORE: bytes per browser entry
BRW_BYTES = [('BRWCNT', 1), ('BRWSEL', 1), ('BRWTOP', 1), ('BRWFOC', 1),
             ('BRWMORE', 1), ('BRWMODE', 1), ('BRWIDX', 32), ('BRWENT', 19 * 32),
             ('BRWINF', 71), ('BRWPATH', 64), ('BRWMASK', 13), ('BRWOUT', 64),
             ('INPBUF', 40)]


def brw_listing(run, label):
    """The browser's listing at a snapshot, as it is printed, in order."""
    sn = run.snaps.get(label, {})
    idx, ent, cnt = sn.get('BRWIDX'), sn.get('BRWENT'), sn.get('BRWCNT')
    if idx is None or ent is None or cnt is None:
        return None
    cnt = cnt[0]
    out = []
    for n in idx[:min(cnt, 32)]:
        if n >= 32:
            out.append('?')             # not in the captured range
            continue
        raw = bytes(ent[n * BRWESZ:n * BRWESZ + 11]).decode('ascii', 'replace')
        flags = ent[n * BRWESZ + 11]
        if flags & 0x20:
            out.append('..\\')
        elif flags & 0x40:
            out.append(raw[0] + ':')
        else:
            name = raw[:8].rstrip()
            if raw[8:].strip():
                name += '.' + raw[8:].rstrip()
            out.append(name + ('\\' if flags & 0x80 else ''))
    return out


class H34BrowseOpen(Case):
    name = 'H34-browse-open'
    desc = ('File > Open, Ctrl+O and :e: the browser lists, navigates into '
            'and out of directories, filters by mask, and opens a file by '
            'selection or by a typed relative path')
    origin = ('F2 of the file browser spec: File > Open, Ctrl+O and :e with '
              'no name did nothing, and there was no way to reach a file in '
              'another directory from inside the editor')
    variants = ('nav', 'mask', 'typed', 'dirty', 'vi', 'menu', 'cursor')
    NOTES = crlf(['N1', 'N2', 'N3'])

    def config(self, ctx, variant=None):
        if variant == 'vi':
            return DEFAULT_CFG.replace('PROFILE=STD', 'PROFILE=VI')
        return DEFAULT_CFG

    def fixture(self, ctx, variant=None):
        return crlf(numbered(5))

    def disk_files(self, ctx, variant=None):
        files = Case.disk_files(self, ctx, variant)
        files['SUB\\NOTES.TXT'] = {'data': self.NOTES,
                                   'date': '2026-09-29T09:05'}
        files['AAA\\ONE.TXT'] = crlf(['ONE'])
        files['HID.TXT'] = {'data': b'hidden\r\n', 'attr': '+h'}
        return files

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.snap('boot')
        b = BRW_BYTES
        if variant == 'dirty':
            t.text('X')
            t.wait(0.5)
            t.press('O', mods=['CTRL'])
            t.snap('asked', at='WINPOLL')
            t.press('N')
            t.wait(1.0)
            t.snap('kept', bytes_=b)
            return t
        if variant == 'vi':
            H27ViEx.type_str(self, t, ':e')
            t.press('RETURN')
        elif variant == 'menu':
            t.press('F1')
            t.press('DOWN')
            t.press('RETURN')
        else:
            t.press('O', mods=['CTRL'])
        t.wait(0.5)
        t.snap('open', at='WINPOLL', vram='screen', bytes_=b)
        if variant in ('vi', 'menu'):
            t.press('ESC')
            t.wait(1.0)
            t.snap('closed', bytes_=b)
            return t
        if variant == 'cursor':
            t.press('TAB')
            t.wait(0.5)
            t.snap('fld', at='WINPOLL', bytes_=b)
            t.press('DOWN')
            t.wait(0.5)
            t.snap('ok', at='WINPOLL', bytes_=b)
            t.press('RIGHT')
            t.wait(0.5)
            t.snap('canc', at='WINPOLL', bytes_=b)
            t.press('LEFT')
            t.wait(0.5)
            t.snap('ok2', at='WINPOLL', bytes_=b)
            t.press('UP')
            t.wait(0.5)
            t.snap('fld2', at='WINPOLL', bytes_=b)
            t.press('UP')
            t.wait(0.5)
            t.snap('list', at='WINPOLL', bytes_=b)
            t.press('ESC')
            t.wait(1.0)
            t.snap('closed', bytes_=b)
            return t
        if variant == 'mask':
            t.press('TAB')
            t.text('*.TXT')
            t.press('RETURN')
            t.wait(0.5)
            t.snap('masked', at='WINPOLL', bytes_=b)
            t.press('ESC')
            t.wait(1.0)
            t.snap('closed', bytes_=b)
            return t
        if variant == 'typed':
            t.press('TAB')
            t.text('sub\\notes.txt')
            t.press('RETURN')
            t.wait(2.0)
            t.snap('loaded', bytes_=b)
            return t
        # nav
        t.press('RIGHT')                  # SUB\
        t.press('RETURN')
        t.wait(0.5)
        t.snap('insub', at='WINPOLL', bytes_=b)
        t.press('RIGHT')                  # NOTES.TXT
        t.wait(1.0)
        t.snap('onnotes', at='WINPOLL', bytes_=b)
        t.press('BS')                     # back up: SUB\ selected again
        t.wait(0.5)
        t.snap('backup', at='WINPOLL', bytes_=b)
        t.press('RETURN')
        t.press('RIGHT')
        t.press('RETURN')                 # open NOTES.TXT
        t.wait(2.0)
        t.snap('loaded', bytes_=b)
        return t

    def key_for(self, ch):
        return H27ViEx.key_for(self, ch)

    def root_listing(self, run):
        """What the root must list: from the session's own disk."""
        import sys
        sys.path.insert(0, os.path.dirname(run.session.ctx.dskfat))
        import dskfat
        fs = dskfat.Fat12(run.dsk)
        dirs, files = [], []
        for off in fs.entries(0):
            name = dskfat.from83(fs.img[off:off + 11])
            (dirs if fs.img[off + 11] & 0x10 else files).append(
                (bytes(fs.img[off:off + 11]), name))
        return ([n + '\\' for _, n in sorted(dirs)] +
                [n for _, n in sorted(files)])

    def verify(self, ctx, runs):
        checks = []
        for variant, run in sorted(runs.items()):
            v = 'H34/%s' % variant
            if variant == 'dirty':
                checks.append(Check('%s/asked' % v,
                                    run.var('asked', 'WINACTV') == 1,
                                    'Discard changes? shown (WINACTV %s)'
                                    % run.var('asked', 'WINACTV')))
                checks.append(Check('%s/kept' % v,
                                    run.var('kept', 'TOTLINES') == 5 and
                                    run.var('kept', 'MODIFIED') == 0xFF and
                                    run.var('kept', 'WINACTV') == 0,
                                    'NO keeps the document (TOTLINES %s, '
                                    'MODIFIED %s)'
                                    % (run.var('kept', 'TOTLINES'),
                                       run.var('kept', 'MODIFIED'))))
                continue
            if variant == 'cursor':
                b1 = lambda label, name: (run.var(label, name) or [None])[0]
                checks.append(Check('%s/fld-down' % v,
                                    b1('fld', 'BRWFOC') == 1 and
                                    b1('ok', 'BRWFOC') == 2,
                                    'TAB to field (BRWFOC %s), DOWN to OK (%s)'
                                    % (b1('fld', 'BRWFOC'), b1('ok', 'BRWFOC'))))
                checks.append(Check('%s/btn-arrows' % v,
                                    b1('canc', 'BRWFOC') == 3 and
                                    b1('ok2', 'BRWFOC') == 2,
                                    'RIGHT to Cancel (BRWFOC %s), LEFT to OK (%s)'
                                    % (b1('canc', 'BRWFOC'), b1('ok2', 'BRWFOC'))))
                checks.append(Check('%s/fld-up' % v,
                                    b1('fld2', 'BRWFOC') == 1 and
                                    b1('list', 'BRWFOC') == 0 and
                                    run.var('closed', 'WINACTV') == 0,
                                    'UP to field (BRWFOC %s), UP to list (%s), ESC closed (%s)'
                                    % (b1('fld2', 'BRWFOC'), b1('list', 'BRWFOC'),
                                       run.var('closed', 'WINACTV'))))
                continue
            got = brw_listing(run, 'open')
            want = self.root_listing(run)
            files = [x for x in (got or []) if not x.endswith(':')]
            drives = [x for x in (got or []) if x.endswith(':')]
            checks.append(Check('%s/listing' % v,
                                run.var('open', 'WINACTV') == 1 and
                                files == want and drives[:1] == ['A:'],
                                'directories then files, sorted, then the '
                                'drives: %s' % got))
            if variant == 'nav':
                buf = run.blob('open', 'screen')
                font = font_of(ctx)
                sel_px = (vram.pixel(buf, 126, 30, first_line=0)
                          if buf else None)
                sel_ink = (vram.pixel(buf, 47, 26, first_line=0)
                           if buf else None)
                pos = want.index('HID.TXT')
                x0 = 40 + 6 + 84 * (pos % 5)
                y0 = 10 + 16 + 8 * (pos // 5)
                italic = bool(buf and font and all(
                    vram.ink_mask(buf, x0 + 6 * i, y0, w=6, h=8,
                                  ground=vram.COL_UI, first_line=0) ==
                    vram.glyph_mask(font, ch, variant=2, width=6)
                    for i, ch in enumerate('HID.TXT')))
                checks.append(Check('%s/drawn' % v,
                                    sel_px == vram.COL_HI and
                                    sel_ink == vram.COL_UI and italic,
                                    'selection bar in COL_HI (%s), text in '
                                    'COL_UI (%s), hidden HID.TXT drawn italic (%s)'
                                    % (sel_px, sel_ink, italic)))
                path = asciiz(run, 'insub', 'BRWPATH')
                checks.append(Check('%s/into' % v,
                                    path == 'A:\\SUB\\' and
                                    brw_listing(run, 'insub')[:2] ==
                                    ['..\\', 'NOTES.TXT'],
                                    'RETURN on SUB\\ browses %r: %s'
                                    % (path, brw_listing(run, 'insub'))))
                info = asciiz(run, 'onnotes', 'BRWINF') or ''
                checks.append(Check('%s/info' % v,
                                    info.startswith('NOTES.TXT') and
                                    info[14:24].strip() == str(len(self.NOTES))
                                    and info[26:41] == '09-29-26  9:05a'
                                    and info[43:47] == '---A',
                                    'information line %r' % info))
                checks.append(Check('%s/field' % v,
                                    asciiz(run, 'onnotes', 'INPBUF') ==
                                    'NOTES.TXT',
                                    'selecting a file names it in the field '
                                    '(%r)' % asciiz(run, 'onnotes', 'INPBUF')))
                up = brw_listing(run, 'backup') or []
                sel = (run.var('backup', 'BRWSEL') or [None])[0]
                checks.append(Check('%s/back-up' % v,
                                    asciiz(run, 'backup', 'BRWPATH') == 'A:\\'
                                    and sel is not None and sel < len(up) and
                                    up[sel] == 'SUB\\',
                                    'BS goes up with SUB\\ selected (sel %s '
                                    'of %s)' % (sel, up[:3])))
            if variant in ('nav', 'typed'):
                checks.append(Check('%s/opened' % v,
                                    asciiz(run, 'loaded', 'FILENAME') ==
                                    'A:\\SUB\\NOTES.TXT' and
                                    run.var('loaded', 'TOTLINES') == 3 and
                                    run.var('loaded', 'WINACTV') == 0,
                                    'FILENAME %r, TOTLINES %s'
                                    % (asciiz(run, 'loaded', 'FILENAME'),
                                       run.var('loaded', 'TOTLINES'))))
            if variant == 'mask':
                got = brw_listing(run, 'masked') or []
                names = [x for x in got if not x.endswith(':')]
                checks.append(Check('%s/masked' % v,
                                    asciiz(run, 'masked', 'BRWMASK') ==
                                    '*.TXT' and
                                    names == ['AAA\\', 'SUB\\', 'DOC.TXT',
                                              'HID.TXT'],
                                    'mask *.TXT keeps every directory and '
                                    'only matching files: %s' % got))
            if variant in ('mask', 'vi', 'menu'):
                checks.append(Check('%s/cancel' % v,
                                    run.var('closed', 'WINACTV') == 0 and
                                    asciiz(run, 'closed', 'FILENAME') ==
                                    'DOC.TXT' and
                                    run.var('closed', 'TOTLINES') == 5,
                                    'ESC closes and keeps the document '
                                    '(FILENAME %r)'
                                    % asciiz(run, 'closed', 'FILENAME')))
        return checks


class H35BrowseMany(Case):
    name = 'H35-browse-many'
    desc = ('170 files in one directory: the browser starts where the '
            'document lives, keeps BRWMAX entries and says so, and scrolls '
            'the grid a row at a time to keep the selection on screen')
    origin = ('F2 of the file browser spec: the listing is bounded by page 3 '
              '(BRWMAX = 160 on S6ED), and 14 rows of 5 show 70 of them')
    FILES = 170

    def disk_files(self, ctx, variant=None):
        files = Case.disk_files(self, ctx, variant)
        for i in range(self.FILES):
            files['BIG\\F%03d.TXT' % i] = crlf(['FILE %d' % i])
        files['AUTOEXEC.BAT'] = '%s A:\\BIG\\F000.TXT\r\n' % ctx.prefix
        return files

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.snap('boot')
        t.press('O', mods=['CTRL'])
        # Measured: ~5 s of emulated time to list 170 files on the NMS 8250
        # floppy, 23 ms per _FNEXT. Keys pressed while the Disk ROM reads
        # with interrupts off are never seen, so the timeline waits.
        t.wait(8.0)
        t.snap('open', at='WINPOLL', bytes_=BRW_BYTES)
        t.press('DOWN', repeat=20)
        t.wait(0.5)
        t.snap('down', at='WINPOLL', vram='screen', bytes_=BRW_BYTES)
        t.press('UP', repeat=20)
        t.wait(2.0)
        t.snap('up', at='WINPOLL', bytes_=BRW_BYTES)
        # 45 more keys: with the 40 above the BIOS keyboard buffer wraps at
        # least twice, which is where WINPOLL used to drop one.
        t.press('RIGHT', repeat=45)
        t.wait(1.0)
        t.snap('right', at='WINPOLL', bytes_=BRW_BYTES)
        t.press('ESC')
        t.wait(0.5)
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        b1 = lambda label, name: (run.var(label, name) or [None])[0]
        got = brw_listing(run, 'open') or []
        info = asciiz(run, 'open', 'BRWINF') or ''
        buf = run.blob('down', 'screen')
        # DOWN x 20 from position 0 is position 100, grid row 20: the top
        # row becomes 20 - 13 = 7 and the selection sits on screen row 13.
        bar = vram.pixel(buf, 126, 10 + 16 + 8 * 13 + 4, first_line=0) \
            if buf else None
        font = font_of(ctx)

        def slot_shows(row, col, text, ground):
            if not buf or not font:
                return False
            x0, y0 = 40 + 6 + 84 * col, 10 + 16 + 8 * row
            return all(vram.ink_mask(buf, x0 + 6 * i, y0, w=6, h=8,
                                     ground=ground, first_line=0) ==
                       vram.glyph_mask(font, ch, width=6)
                       for i, ch in enumerate(text))
        # Top 7: screen row 0 starts at position 35 (F034.TXT, since
        # position 0 is ..\); screen row 13, column 4 is position 104.
        moved = (slot_shows(0, 0, 'F034.TXT', vram.COL_UI) and
                 slot_shows(13, 4, 'F103.TXT', vram.COL_UI) and
                 slot_shows(13, 0, 'F099.TXT', vram.COL_HI))
        return [
            Check('H35/scroll-paint', moved,
                  'after 13 one-row scrolls the grid shows F034 at the top, '
                  'F103 bottom right and F099 under the bar'),
            Check('H35/start-dir',
                  asciiz(run, 'open', 'BRWPATH') == 'A:\\BIG\\' and
                  got[:3] == ['..\\', 'F000.TXT', 'F001.TXT'],
                  'the browser opens where the document is: %r %s'
                  % (asciiz(run, 'open', 'BRWPATH'), got[:3])),
            Check('H35/capacity',
                  b1('open', 'BRWCNT') == 160 and b1('open', 'BRWMORE') == 1
                  and info.rstrip().endswith('160+/160'),
                  'BRWCNT %s, BRWMORE %s, count %r'
                  % (b1('open', 'BRWCNT'), b1('open', 'BRWMORE'),
                     info.rstrip()[-10:])),
            Check('H35/scroll-down',
                  b1('down', 'BRWSEL') == 100 and b1('down', 'BRWTOP') == 7
                  and bar == vram.COL_HI,
                  'BRWSEL %s, BRWTOP %s, bar on screen row 13: %s'
                  % (b1('down', 'BRWSEL'), b1('down', 'BRWTOP'), bar)),
            Check('H35/every-key', b1('right', 'BRWSEL') == 45,
                  '45 RIGHT from position 0 end on %s: a dialog must not '
                  'drop the key that wraps the BIOS keyboard buffer'
                  % b1('right', 'BRWSEL')),
            Check('H35/scroll-up',
                  b1('up', 'BRWSEL') == 0 and b1('up', 'BRWTOP') == 0,
                  'back at the top: BRWSEL %s, BRWTOP %s'
                  % (b1('up', 'BRWSEL'), b1('up', 'BRWTOP'))),
        ]


# --- H36  SAVE AS & OVERWRITE (PHASE F4) -------------------------------


class H36BrowseSaveAs(Case):
    name = 'H36-browse-saveas'
    desc = ('File > Save As, Ctrl+Shift+S: saves to new file, saves into '
            'subdirectory, asks overwrite confirmation with reopen on NO, '
            'overwrites on YES, and routes Ctrl+S on untitled document')
    origin = ('F4 of the file browser spec: Save As on both targets with '
              'overwrite confirmation and reopen on No')
    variants = ('new', 'sub', 'overwrite-no', 'overwrite-yes', 'untitled', 'menu')
    TAG = 'H36'
    FIXTURE = crlf(['LINE 1', 'LINE 2', 'LINE 3'])
    EXISTING = b'ORIGINAL\r\n'
    BRW_BYTES = BRW_BYTES

    def fixture(self, ctx, variant=None):
        return self.FIXTURE

    def disk_files(self, ctx, variant=None):
        files = Case.disk_files(self, ctx, variant)
        files['EXIST.TXT'] = self.EXISTING
        files['SUB\\DUMMY.TXT'] = b'dummy\r\n'
        return files

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.snap('boot')
        b = self.BRW_BYTES
        if variant == 'untitled':
            t.press('N', mods=['CTRL'])
            t.wait(0.5)
            t.text('X')
            t.wait(0.5)
            t.press('S', mods=['CTRL', 'SHIFT'])
            t.wait(0.5)
            t.snap('open', at='WINPOLL', bytes_=b)
            t.press('ESC')
            t.wait(1.0)
            t.snap('closed', bytes_=b)
            return t
        if variant == 'menu':
            t.press('F1')
            t.press('DOWN')
            t.press('DOWN')
            t.press('DOWN')
            t.press('RETURN')
            t.wait(0.5)
            t.snap('open', at='WINPOLL', bytes_=b)
            t.press('ESC')
            t.wait(1.0)
            t.snap('closed', bytes_=b)
            return t
        t.press('S', mods=['CTRL', 'SHIFT'])
        t.wait(0.5)
        t.snap('open', at='WINPOLL', bytes_=b)
        t.press('BS', repeat=12)
        if variant == 'new':
            t.text('SAVED1.TXT')
            t.press('RETURN')
            t.wait(2.0)
            t.snap('done', bytes_=b)
            return t
        if variant == 'sub':
            t.text('SUB\\SAVED2.TXT')
            t.press('RETURN')
            t.wait(2.0)
            t.snap('done', bytes_=b)
            return t
        t.text('EXIST.TXT')
        t.press('RETURN')
        t.wait(0.5)
        t.snap('asked', at='WINPOLL', bytes_=b)
        if variant == 'overwrite-no':
            t.press('N')
            t.wait(0.5)
            t.snap('reopen', at='WINPOLL', bytes_=b)
            t.press('BS', repeat=12)
            t.text('EXIS2.TXT')
            t.press('RETURN')
            t.wait(2.0)
            t.snap('done', bytes_=b)
            return t
        t.press('Y')
        t.wait(2.0)
        t.snap('done', bytes_=b)
        return t

    def verify(self, ctx, runs):
        checks = []
        def b1(run, label, name):
            val = run.var(label, name)
            if isinstance(val, (list, tuple)):
                return val[0] if val else None
            return val

        for variant, run in sorted(runs.items()):
            v = '%s/%s' % (self.TAG, variant)
            if variant in ('untitled', 'menu'):
                checks.append(Check('%s/open' % v,
                                    b1(run, 'open', 'BRWMODE') == 1 and
                                    run.var('open', 'WINACTV') == 1 and
                                    run.var('closed', 'WINACTV') == 0,
                                    'Save As browser opened (BRWMODE %s) and closed cleanly'
                                    % b1(run, 'open', 'BRWMODE')))
                continue
            if variant == 'new':
                got = run.session.extract(run.dsk, 'SAVED1.TXT')
                fn = asciiz(run, 'done', 'FILENAME') or ''
                checks.append(Check('%s/saved' % v,
                                    run.var('done', 'WINACTV') == 0 and
                                    fn.endswith('SAVED1.TXT') and
                                    got == self.FIXTURE,
                                    'saved to SAVED1.TXT on disk: %s' % (got == self.FIXTURE)))
                continue
            if variant == 'sub':
                got = run.session.extract_path(run.dsk, 'SUB\\SAVED2.TXT')
                fn = asciiz(run, 'done', 'FILENAME') or ''
                checks.append(Check('%s/saved' % v,
                                    run.var('done', 'WINACTV') == 0 and
                                    fn.endswith('SUB\\SAVED2.TXT') and
                                    got == self.FIXTURE,
                                    'saved into SUB\\SAVED2.TXT on disk: %s' % (got == self.FIXTURE)))
                continue
            if variant == 'overwrite-no':
                orig = run.session.extract(run.dsk, 'EXIST.TXT')
                newf = run.session.extract(run.dsk, 'EXIS2.TXT')
                inp = asciiz(run, 'reopen', 'INPBUF')
                checks.append(Check('%s/asked' % v,
                                    run.var('asked', 'WINACTV') == 1,
                                    'Overwrite prompt shown (WINACTV %s)' % run.var('asked', 'WINACTV')))
                checks.append(Check('%s/reopened' % v,
                                    run.var('reopen', 'WINACTV') == 1 and
                                    b1(run, 'reopen', 'BRWMODE') == 1 and
                                    inp == 'EXIST.TXT',
                                    'browser reopened with field intact: %r' % inp))
                checks.append(Check('%s/preserved' % v,
                                    orig == self.EXISTING and newf == self.FIXTURE,
                                    'EXIST.TXT unchanged on NO, EXIS2.TXT saved'))
                continue
            if variant == 'overwrite-yes':
                got = run.session.extract(run.dsk, 'EXIST.TXT')
                checks.append(Check('%s/overwritten' % v,
                                    run.var('asked', 'WINACTV') == 1 and
                                    got == self.FIXTURE,
                                    'EXIST.TXT overwritten on YES: %s' % (got == self.FIXTURE)))
        return checks


# --- H37  SETTINGS MODAL DIALOG (SCREEN 6) ----------------------------


class H37Settings(Case):
    name = 'H37-settings'
    desc = ('Settings modal dialog: open via Help > Settings (Item 0), 2D navigation '
            '(UP/DOWN across rows, RIGHT/LEFT/SPACE to cycle values), toggle buttons, '
            'ESC cancels cleanly without modifying state, OK commits to live variables '
            'and serializes to loaded .CFG on disk')
    origin = ('Universal Settings screen (Phase 2026-10-02): replaces View and Options '
              'menus with unified modal dialog and on-disk CFG serialization.')
    variants = ('cancel', 'save')

    FIXTURE = '1234567890\n' * 5

    def fixture(self, ctx, variant=None):
        return crlf(self.FIXTURE)

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.snap('boot', vram=True)

        # Open Help menu (F3), Item 0 is Settings...
        t.press('F3')
        t.snap('menu', at='WINPOLL')
        t.press('RETURN')
        t.snap('open', at='WINPOLL')

        if variant == 'cancel':
            # Cycle Profile forward (STD -> TED)
            t.press('RIGHT')
            t.snap('cycled', at='WINPOLL')
            # ESC cancels without saving
            t.press('ESC')
            t.snap('closed')
            return t

        if variant == 'save':
            # 1. DOWN x 3 -> Clock (Row 3)
            t.press('DOWN')
            t.press('DOWN')
            t.press('DOWN')
            t.snap('foc_clk', at='WINPOLL')
            # SPACE toggles Clock (OFF -> ON)
            t.press('SPACE')
            t.snap('clk_toggled', at='WINPOLL')

            # 2. DOWN x 4 -> Theme (Row 7)
            t.press('DOWN')
            t.press('DOWN')
            t.press('DOWN')
            t.press('DOWN')
            t.snap('foc_thm', at='WINPOLL')
            # RIGHT cycles Theme (0 -> 1: AMBER)
            t.press('RIGHT')
            t.snap('thm_cycled', at='WINPOLL')

            # 3. DOWN -> Shadow (Row 8)
            t.press('DOWN')
            t.snap('foc_shd', at='WINPOLL')
            # SPACE toggles Shadow
            t.press('SPACE')
            t.snap('shd_toggled', at='WINPOLL')

            # 4. DOWN to [ OK ] button (Row 9)
            t.press('DOWN')
            t.snap('foc_ok', at='WINPOLL')
            # RETURN commits and saves to disk
            t.press('RETURN')
            t.wait(2.0)
            t.snap('saved')
            return t

        return t

    def verify(self, ctx, runs):
        checks = []
        for variant, run in sorted(runs.items()):
            v = '%s/%s' % (self.name, variant)

            if variant == 'cancel':
                checks.append(Check('%s/geometry' % v,
                                    run.var('open', 'WINACTV') == 1 and
                                    run.var('open', 'WINX') == 120 and
                                    run.var('open', 'WINY') == 48 and
                                    run.var('open', 'WINW') == 272 and
                                    run.var('open', 'WINH') == 116,
                                    'Settings dialog opened with correct geometry (120,48,272,116)'))
                checks.append(Check('%s/cycled' % v,
                                    run.var('open', 'SETTFOC') == 0 and
                                    run.var('open', 'STTPRF') == 0 and
                                    run.var('cycled', 'STTPRF') == 1,
                                    'RIGHT cycles STTPRF from 0 (STD) to 1 (TED)'))
                checks.append(Check('%s/discarded' % v,
                                    run.var('closed', 'WINACTV') == 0 and
                                    run.var('closed', 'KMAPID') == 0,
                                    'ESC discards changes: WINACTV=0, live KMAPID remains 0'))

            if variant == 'save':
                checks.append(Check('%s/clk-toggle' % v,
                                    run.var('foc_clk', 'SETTFOC') == 3 and
                                    run.var('open', 'STTCLK') == 1 and
                                    run.var('clk_toggled', 'STTCLK') == 0,
                                    'SPACE toggles Clock from ON (1) to OFF (0)'))
                checks.append(Check('%s/thm-cycle' % v,
                                    run.var('foc_thm', 'SETTFOC') == 7 and
                                    run.var('open', 'STTTHM') == 0 and
                                    run.var('thm_cycled', 'STTTHM') == 1,
                                    'RIGHT cycles Theme from 0 to 1 (AMBER)'))
                checks.append(Check('%s/shd-toggle' % v,
                                    run.var('foc_shd', 'SETTFOC') == 8 and
                                    run.var('shd_toggled', 'STTSHD') != run.var('open', 'STTSHD'),
                                    'SPACE toggles Shadow setting'))
                checks.append(Check('%s/live-commit' % v,
                                    run.var('foc_ok', 'SETTFOC') == 9 and
                                    run.var('saved', 'WINACTV') == 0 and
                                    run.var('saved', 'SHOWCLK') == 0 and
                                    run.var('saved', 'THEMEID') == 1 and
                                    run.var('saved', 'PALDIRT') != 0,
                                    'OK commits: SHOWCLK=0, THEMEID=1, PALDIRT set, WINACTV=0'))
                # Verify serialized CFG on disk
                cfg_bytes = (run.session.extract_path(run.dsk, 'DEV\\S6ED.CFG') or
                             run.session.extract(run.dsk, 'S6ED.CFG'))
                cfg_text = cfg_bytes.decode('ascii', errors='replace') if cfg_bytes else ''
                checks.append(Check('%s/cfg-on-disk' % v,
                                    'CLOCK=0' in cfg_text and 'THEME=AMBER' in cfg_text and 'SHADOW=' in cfg_text,
                                    'Saved .CFG contains CLOCK=0, THEME=AMBER, SHADOW=: %s'
                                    % ('CLOCK=0' in cfg_text and 'THEME=AMBER' in cfg_text and 'SHADOW=' in cfg_text)))
                checks.append(Check('%s/saved-msg' % v,
                                    asciiz(run, 'saved', 'STATMSG') == '[SAVED]',
                                    'Status bar displays [SAVED]: %r' % asciiz(run, 'saved', 'STATMSG')))
        return checks


# --- H38  DISK ERROR AND ABORT HANDLER (_DEFER / _DEFAB) --------------


class H38DiskError(Case):
    name = 'H38-disk-error'
    desc = ('Disk error handling via _DEFER and _DEFAB: accessing an empty drive '
            'in the file browser, saving to an empty drive, and opening from an '
            'empty drive fail gracefully without crashing or DOS abort prompts')
    origin = ('_DEFER / _DEFAB disk error handler implementation (2026-10-05)')
    machine = MACH_2MB
    variants = ('browse', 'save', 'load')
    cfg = """; generated by the S6ED test harness
PROFILE=VI
WRAP=DEV
MARKUP=OFF
CLOCK=0
TABWIDTH=4
EOL=AUTO
AUTOALIGN=OFF
THEME=DARK
"""
    def config(self, ctx, variant=None):
        if variant == 'browse':
            return DEFAULT_CFG
        return DEFAULT_CFG.replace('PROFILE=STD', 'PROFILE=VI')

    FIXTURE = crlf(['LINE 1', 'LINE 2', 'LINE 3'])
    BRW_BYTES = BRW_BYTES

    def fixture(self, ctx, variant=None):
        return self.FIXTURE

    def key_for(self, ch):
        return H27ViEx.key_for(self, ch)

    def type_str(self, t, s):
        for ch in s:
            k, mods = self.key_for(ch)
            t.press(k, mods=mods)

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.snap('boot')

        if variant == 'browse':
            b = self.BRW_BYTES
            t.press('O', mods=['CTRL'])
            t.wait(0.5)
            t.snap('open', at='WINPOLL', bytes_=b)
            # Navigate to B: in drive listing: 2 x DOWN -> B: (index 10)
            t.press('DOWN')
            t.wait(0.5)
            t.press('DOWN')
            t.wait(0.5)
            t.snap('on_b', at='WINPOLL', bytes_=b)
            t.press('RETURN')
            t.wait(4.0)
            t.snap('b_done', at='WINPOLL', bytes_=b)
            t.press('ESC')
            t.wait(1.5)
            t.snap('closed', bytes_=b)
            return t

        if variant == 'save':
            # Vi console save to empty drive B:
            t.wait(0.5)
            self.type_str(t, ':w B:\\OUT.TXT')
            t.press('RETURN')
            t.wait(4.0)
            t.snap('saved')
            return t

        if variant == 'load':
            # Vi console open from empty drive B:
            t.wait(0.5)
            self.type_str(t, ':e B:\\NOFILE.TXT')
            t.press('RETURN')
            t.wait(4.0)
            t.snap('loaded')
            return t

    def verify(self, ctx, runs):
        checks = []
        for variant, run in sorted(runs.items()):
            v = 'H38/%s' % variant
            if variant == 'browse':
                checks.append(Check('%s/open' % v,
                                    run.var('open', 'WINACTV') == 1,
                                    'Browser opened (WINACTV %s)' % run.var('open', 'WINACTV')))
                # Assert that pressing Enter on empty drive B: did not crash and set DSKERR=0xFC
                checks.append(Check('%s/dskerr' % v,
                                    run.var('b_done', 'WINACTV') == 1 and
                                    run.var('b_done', 'DSKERR') == 0xFC,
                                    'Accessing empty drive B: sets DSKERR=0xFC (#FC) and stays in browser (WINACTV 1)'))
                checks.append(Check('%s/closed' % v,
                                    run.var('closed', 'WINACTV') == 0,
                                    'ESC closes browser cleanly without hang (WINACTV 0)'))
            elif variant == 'save':
                checks.append(Check('%s/saved-err' % v,
                                    run.var('saved', 'DSKERR') == 0xFC and
                                    asciiz(run, 'saved', 'STATMSG') == '[SAVE ERROR]',
                                    'Saving to empty drive B: sets DSKERR=0xFC and reports [SAVE ERROR]'))
                checks.append(Check('%s/doc-kept' % v,
                                    run.var('saved', 'TOTLINES') == 3,
                                    'Document kept intact in memory (TOTLINES 3)'))
            elif variant == 'load':
                checks.append(Check('%s/load-err' % v,
                                    run.var('loaded', 'DSKERR') == 0xFC and
                                    asciiz(run, 'loaded', 'STATMSG') == '[CANNOT OPEN]',
                                    'Loading from empty drive B: sets DSKERR=0xFC and reports [CANNOT OPEN]'))
        return checks


# --- H28  PARAMETRIC TEXTWIDTH (PHASE C2) -----------------------------


class H28TextWidth(Case):
    name = 'H28-textwidth'
    desc = ('TEXTWIDTH= in the CFG, push-wrap at a custom margin, and the VI '
            'ex console :set tw=/nowrap/wrap with SAVETW round-trip')
    origin = ('Phase C2 (2026-09-27): the wrap margin is TXTWIDTH, not '
              'TEXTCOLS.  WRAP_DEV is TXTWIDTH = 0: free typing up to '
              'MAXCOLS with horizontal scroll, and WRAP=TXT on top of a '
              'TXTWIDTH never widens it.  Lines longer than the margin are '
              'data, never broken by viewing or by a later mode change.')
    variants = ('cfg40', 'ex', 'longtail')

    # longtail: a loaded line longer than the margin, edited near its start.
    # The pushed tail is LEN + 1 - SPLIT = 81 characters, far over the
    # margin-sized record EDPSHWR used to reserve (40 -> 48 by quantum), and
    # PUTREC does not check capacity: the attributes landed on text 48..80
    # (measured: 48 x then 33 NULs on disk).
    LONG = 'x' * 120
    LONGNB = ['NEIGHBOUR ONE', 'NEIGHBOUR TWO']

    # keymatrixdown without SHIFT types lowercase.
    HEAD = 'a' * 38 + ' '         # 39 chars: the pushed word breaks after it
    WORD = 'b' * 10
    TW40 = 40

    def config(self, ctx, variant=None):
        if variant == 'longtail':
            return ("PROFILE=STD\r\nTEXTWIDTH=40\r\nMARKUP=OFF\r\n"
                    "CLOCK=0\r\nTABWIDTH=4\r\nEOL=AUTO\r\nAUTOALIGN=OFF\r\n")
        if variant == 'cfg40':
            # Spaced form, on purpose: CFGVAL owns the whitespace rule.
            return ("; TEXTWIDTH in the form that broke TABWIDTH\r\n"
                    "PROFILE = STD\r\n"
                    "TEXTWIDTH = 40\r\n"
                    "MARKUP = OFF\r\n"
                    "CLOCK = 0\r\n"
                    "TABWIDTH = 4\r\n"
                    "EOL = AUTO\r\n"
                    "AUTOALIGN = OFF\r\n")
        return ("PROFILE=VI\nWRAP=DEV\nMARKUP=OFF\nCLOCK=0\n"
                "TABWIDTH=4\nEOL=AUTO\nAUTOALIGN=OFF\n")

    def fixture(self, ctx, variant=None):
        if variant == 'longtail':
            return crlf([self.LONG] + self.LONGNB)
        return crlf([''])

    def key_for(self, ch):
        if ch == ':':
            return (';', ['SHIFT'])
        if ch == ' ':
            return ('SPACE', [])
        return (ch.upper(), [])

    def type_str(self, t, s):
        for ch in s:
            k, mods = self.key_for(ch)
            t.press(k, mods=mods)

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.snap('boot')
        if variant == 'longtail':
            t.wait(1.0)
            t.press('RIGHT', repeat=5)
            t.text('y')                 # push-wrap inside a 120-char line
            t.snap('pushed')
            # The next record is allocated right behind the tail's: an
            # overflowing tail and a new line cannot both survive.
            t.press('DOWN', repeat=3)
            t.press('RIGHT', mods=['CTRL'])
            t.press('RETURN')
            t.text('z')
            t.snap('after')
            t.press('S', mods=['CTRL'])
            t.wait(3.0)
            t.snap('saved')
            return t
        if variant == 'cfg40':
            # 38 a's + space: 39 chars, cursor at 39.  The first b fills the
            # last column (CURX stays 39 on a full line); the second b
            # push-wraps the one-letter word, the remaining 8 land after it.
            t.text('a' * 38 + ' ' + self.WORD)
            t.snap('wrapped')
            t.press('S', mods=['CTRL'])
            t.wait(3.0)
            t.snap('saved')
            return t
        # ex variant: VI profile, no TEXTWIDTH in the CFG (defaults 0 / DEV).
        self.type_str(t, ':set tw=48')
        t.press('RETURN')
        t.wait(1.0)
        t.snap('setw48')
        self.type_str(t, ':set nowrap')
        t.press('RETURN')
        t.wait(1.0)
        t.snap('nowrap')
        # TXTWIDTH = 0: type straight past column 80, no wrap, LEFTCOL scrolls.
        self.type_str(t, 'i')
        t.text('c' * 85)
        t.snap('free')
        t.press('ESC')
        # The 85-char line must survive the mode change untouched.
        # The 85-char free-typing burst leaves the BIOS keyboard ISR draining
        # the tail of the run while the console is already open: a lone RETURN
        # here landed inside that window and was never buffered (measured:
        # console open with ':set wrap' complete, INPLEN = 9, buffer pointers
        # equal).  Two presses a second apart bracket the drain.
        self.type_str(t, ':set wrap')
        t.press('RETURN')
        t.wait(1.0)
        t.press('RETURN')
        t.wait(1.0)
        t.snap('rewrap')
        return t

    def verify(self, ctx, runs):
        checks = []
        run40, runex = runs['cfg40'], runs['ex']
        runlt = runs['longtail']

        # - longtail: the pushed tail is longer than the margin ---------
        head = 'x' * 5 + 'y' + 'x' * 34
        tail = 'x' * (len(self.LONG) - 39)
        checks.append(Check('H28/longtail/totlines',
                            runlt.var('pushed', 'TOTLINES') == 4,
                            'TOTLINES = %s after the push (expected 4)'
                            % runlt.var('pushed', 'TOTLINES')))
        got = runlt.session.extract(runlt.dsk, 'DOC.TXT')
        want = crlf([head, tail] + self.LONGNB + ['z'])
        checks.append(Check('H28/longtail/content', got == want,
                            'an 81-char tail pushed under TW=40 survives '
                            'with its neighbours byte for byte'
                            if got == want else 'got %r' % got))

        # - cfg40: TEXTWIDTH=40 from the CFG, in spaced form ------------
        checks.append(Check('H28/cfg40/boot-txtwidth',
                            run40.var('boot', 'TXTWIDTH') == self.TW40 and
                            run40.var('boot', 'SAVETW') == self.TW40,
                            'TXTWIDTH = %s, SAVETW = %s (expected 40/40)'
                            % (run40.var('boot', 'TXTWIDTH'),
                               run40.var('boot', 'SAVETW'))))
        checks.append(Check('H28/cfg40/boot-wrap',
                            run40.var('boot', 'WRAPMODE') == 1,
                            'TEXTWIDTH=40 implies WRAPMODE = TXT (got %s)'
                            % run40.var('boot', 'WRAPMODE')))
        checks.append(Check('H28/cfg40/boot-flag',
                            run40.var('boot', 'WRAPMODE') == 1,
                            'WRAPMODE = TXT (%s)' % run40.var('boot', 'WRAPMODE')))
        checks.append(Check('H28/cfg40/totlines',
                            run40.var('wrapped', 'TOTLINES') == 2,
                            'TOTLINES = %s after typing past column 40'
                            % run40.var('wrapped', 'TOTLINES')))
        checks.append(Check('H28/cfg40/cursor',
                            run40.var('wrapped', 'DOCLINE') == 1 and
                            run40.var('wrapped', 'CURX') == 10,
                            'cursor (DOCLINE, CURX) = (%s, %s), expected (1, 10)'
                            % (run40.var('wrapped', 'DOCLINE'),
                               run40.var('wrapped', 'CURX'))))
        wb = run40.snaps.get('wrapped', {}).get('WORKBUF', [])
        tail = bytes(wb[1:11]) if len(wb) >= 11 else b''
        checks.append(Check('H28/cfg40/tail',
                            wb and wb[0] == 10 and tail == self.WORD.encode(),
                            'current line holds the pushed word (%d chars)'
                            % (wb[0] if wb else -1)))
        got = run40.session.extract(run40.dsk, 'DOC.TXT')
        want = crlf([self.HEAD, self.WORD])
        checks.append(Check('H28/cfg40/content', got == want,
                            'saved document wraps at column 40'
                            if got == want else 'got %r' % (got,)))

        # - ex: :set tw=48 / nowrap / wrap -------------------------------
        checks.append(Check('H28/ex/boot-dev',
                            runex.var('boot', 'TXTWIDTH') == 0 and
                            runex.var('boot', 'WRAPMODE') == 0 and
                            runex.var('boot', 'SAVETW') == 80,
                            'no CFG key: TXTWIDTH = %s, WRAPMODE = %s, '
                            'SAVETW = %s (expected 0/0/80)'
                            % (runex.var('boot', 'TXTWIDTH'),
                               runex.var('boot', 'WRAPMODE'),
                               runex.var('boot', 'SAVETW'))))
        checks.append(Check('H28/ex/setw48',
                            runex.var('setw48', 'TXTWIDTH') == 48 and
                            runex.var('setw48', 'WRAPMODE') == 1 and
                            runex.var('setw48', 'SAVETW') == 48,
                            ':set tw=48 -> TXTWIDTH = %s, WRAPMODE = %s, '
                            'SAVETW = %s (expected 48/1/48)'
                            % (runex.var('setw48', 'TXTWIDTH'),
                               runex.var('setw48', 'WRAPMODE'),
                               runex.var('setw48', 'SAVETW'))))
        checks.append(Check('H28/ex/nowrap',
                            runex.var('nowrap', 'TXTWIDTH') == 0 and
                            runex.var('nowrap', 'WRAPMODE') == 0 and
                            runex.var('nowrap', 'SAVETW') == 48,
                            ':set nowrap -> TXTWIDTH = %s, WRAPMODE = %s, '
                            'SAVETW kept at %s (expected 0/0/48)'
                            % (runex.var('nowrap', 'TXTWIDTH'),
                               runex.var('nowrap', 'WRAPMODE'),
                               runex.var('nowrap', 'SAVETW'))))
        checks.append(Check('H28/ex/free-typing',
                            runex.var('free', 'TOTLINES') == 1 and
                            runex.var('free', 'CURX') == 85,
                            'nowrap: 85 chars on one line, CURX = %s, '
                            'TOTLINES = %s'
                            % (runex.var('free', 'CURX'),
                               runex.var('free', 'TOTLINES'))))
        checks.append(Check('H28/ex/free-scroll',
                            runex.var('free', 'LEFTCOL') == 9,
                            'LEFTCOL = %s after scrolling past column 80 '
                            '(expected 9: 80 - 80 + 1 + 8)'
                            % runex.var('free', 'LEFTCOL')))
        wb = runex.snaps.get('free', {}).get('WORKBUF', [])
        checks.append(Check('H28/ex/free-line',
                            wb and wb[0] == 85,
                            'the line holds all 85 characters (LEN = %s)'
                            % (wb[0] if wb else '?')))
        checks.append(Check('H28/ex/rewrap',
                            runex.var('rewrap', 'TXTWIDTH') == 48 and
                            runex.var('rewrap', 'WRAPMODE') == 1,
                            ':set wrap restores SAVETW: TXTWIDTH = %s, '
                            'WRAPMODE = %s (expected 48/1)'
                            % (runex.var('rewrap', 'TXTWIDTH'),
                               runex.var('rewrap', 'WRAPMODE'))))
        wb = runex.snaps.get('rewrap', {}).get('WORKBUF', [])
        checks.append(Check('H28/ex/long-line-survives',
                            wb and wb[0] == 85,
                            'the 85-char line is untouched by the mode '
                            'change (LEN = %s)' % (wb[0] if wb else '?')))
        return checks



# --- U6..U9  EDITS THAT USED TO ESCAPE THE HISTORY -------------------
#
# Before 2026-09-23 only typing, in-line Backspace/Delete, Ctrl+Y, Enter and
# the line joins were recorded.  Everything else -- deleting a selection
# (and so Cut, and typing or pasting over one), word delete, paste, bold and
# italic, push-wrap, reflow -- changed the document behind the ring's back.
# The ring stores LINE NUMBERS, so the next Ctrl+Z replayed an old record on
# whatever line now had that number: measured, select three lines + DEL +
# Ctrl+Z after typing an X on line 3 overwrote LINE 6 with the old LINE 3.

UNDO_CFG = """; generated by the S6ED test harness
PROFILE=STD
WRAP=DEV
MARKUP=OFF
CLOCK=0
TABWIDTH=4
EOL=AUTO
AUTOALIGN=OFF
THEME=DARK
"""


def undo_cycle(t, save=True):
    """Ctrl+Z, Ctrl+Shift+Z, Ctrl+Z -- a snapshot after each -- then save."""
    t.press('Z', mods=['CTRL'])
    t.wait(1.0)
    t.snap('undone')
    t.press('Z', mods=['SHIFT', 'CTRL'])
    t.wait(1.0)
    t.snap('redone')
    t.press('Z', mods=['CTRL'])
    t.wait(1.0)
    t.snap('undone2')
    if save:
        t.press('S', mods=['CTRL'])
        t.wait(3.0)
        t.snap('saved')
    return t


def disk_lines(run):
    got = run.session.extract(run.dsk, 'DOC.TXT')
    if got is None:
        return None
    return got.decode('latin-1').split('\r\n')[:-1]


def at(run, label):
    return tuple(run.var(label, v) for v in ('TOTLINES', 'DOCLINE', 'CURX'))


class U6UndoSelDel(Case):
    name = 'U6-undo-seldel'
    desc = 'deleting a selection is one undo step: Ctrl+Z restores every line'
    origin = ('ACTDLS recorded nothing, so Ctrl+Z after deleting a selection '
              'either did nothing or -- with older history -- replayed a stale '
              'record on the line that now had its number and destroyed it')
    cfg = UNDO_CFG
    variants = ('multi', 'stale', 'single', 'scrolled')
    LINES = ['LINE %d %s' % (i, c * 4) for i, c in enumerate('ABCDEFGH')]
    LONG = ['ROW %02d OF A DOCUMENT THAT SCROLLS' % i for i in range(40)]

    def lines(self, variant):
        return self.LONG if variant == 'scrolled' else self.LINES

    def fixture(self, ctx, variant=None):
        return crlf(self.lines(variant))

    def want(self, variant):
        want = list(self.lines(variant))
        if variant == 'stale':
            want[5] = 'X' + want[5]
        return want

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.wait(1.0)
        if variant == 'stale':
            # A recorded edit BELOW the range: after the delete its line
            # number names a different line.
            t.press('DOWN', repeat=5)
            t.text('X')
            t.press('UP', repeat=5)
            t.press('LEFT')
        if variant == 'scrolled':
            t.press('DOWN', repeat=35)      # the viewport leaves line 0
            t.wait(1.0)
            t.snap('scrolled')
            t.press('A', mods=['CTRL'])
            t.press('DEL')
            t.wait(1.0)
            t.snap('deleted')
            t.press('S', mods=['CTRL'])
            t.wait(3.0)
            t.snap('saved')
            return t
        elif variant == 'single':
            t.press('RIGHT', repeat=2)
            t.press('RIGHT', mods=['SHIFT'], repeat=5)
        else:
            t.press('RIGHT', repeat=3)
            t.press('DOWN', mods=['SHIFT'], repeat=3)
        t.wait(1.0)
        t.snap('selected')
        t.press('DEL')
        t.wait(1.0)
        t.snap('deleted')
        return undo_cycle(t)

    def verify(self, ctx, runs):
        checks = []
        for v in self.variants:
            run = runs[v]
            if v == 'scrolled':
                # The selection began above the viewport: ACTDLS must bring
                # the cursor back on screen via SHOWLN so CURY is not negative.
                ok = (run.var('scrolled', 'TOPLINE') > 0 and
                      run.var('deleted', 'TOPLINE') <= 0 and
                      run.var('deleted', 'CURY') == 0)
                checks.append(Check('U6/scrolled/visible', ok,
                                    'cursor on screen after delete'
                                    if ok else
                                    'scrolled top=%s; deleted top=%s cury=%s'
                                    % (run.var('scrolled', 'TOPLINE'),
                                       run.var('deleted', 'TOPLINE'),
                                       run.var('deleted', 'CURY'))))
                continue
            n = len(self.lines(v))
            if v == 'single':
                gone, col = 0, 2
            else:
                gone, col = 3, 3
            checks.append(Check('U6/%s/recorded' % v,
                                run.var('deleted', 'UNDOPTR') != 0 and
                                at(run, 'deleted') == (n - gone, 0, col),
                                'deleted: %s, UNDOPTR %s'
                                % (at(run, 'deleted'),
                                   run.var('deleted', 'UNDOPTR'))))
            checks.append(Check('U6/%s/undo' % v,
                                at(run, 'undone') == (n, 0, col),
                                'Ctrl+Z -> (TOTLINES, DOCLINE, CURX) %s, '
                                'expected %s' % (at(run, 'undone'),
                                                 (n, 0, col))))
            checks.append(Check('U6/%s/redo' % v,
                                at(run, 'redone') == (n - gone, 0, col),
                                'Ctrl+Shift+Z -> %s, expected %s'
                                % (at(run, 'redone'), (n - gone, 0, col))))
            got = disk_lines(run)
            want = self.want(v)
            checks.append(Check('U6/%s/content' % v, got == want,
                                'document restored byte for byte'
                                if got == want else
                                'got %r' % (got[:8] if got else got)))
        return checks


class U7UndoRing(Case):
    name = 'U7-undo-ring'
    desc = 'a group lives or dies whole in the ring, and a new edit cuts redo'
    origin = ('a selection delete records one line per record, so a group '
              'can be evicted in the middle -- replaying its tail without its '
              'first record is half an edit -- and one larger than the ring '
              'would evict itself.  Found on the way: a new edit left the head '
              'linked to the stale redo records, so evicting the head made the '
              'new record its own predecessor and Ctrl+Z toggled it forever')
    cfg = UNDO_CFG
    variants = ('evict', 'selfloop', 'toobig', 'depth')
    LINES = ['R%02d %s' % (i, 'LINE OF THE RING TEST') for i in range(60)]
    # 171-byte records: 23 fit under the top of the 4 KB ring, so 26 edits
    # wrap it three times and evict exactly the three oldest
    EDITS, KEPT = 26, 23

    def fixture(self, ctx, variant=None):
        return crlf(self.LINES)

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.wait(1.0)
        if variant == 'evict':
            # 22 records (UNDOGMAX): lines 0..21, from BAS to BAS + 3762
            t.press('DOWN', mods=['SHIFT'], repeat=21)
            t.press('DEL')
            t.wait(1.0)
            t.snap('deleted')
            # Two one-line records: the second no longer fits under the top,
            # wraps to BAS and collides with the group's first record
            t.press('DOWN', repeat=2)
            t.text('Y')
            t.press('DOWN', repeat=2)
            t.text('Z')
            t.wait(1.0)
            t.snap('typed')
            for i in range(3):
                t.press('Z', mods=['CTRL'])
                t.wait(1.0)
            t.snap('undone')
        elif variant == 'selfloop':
            # R0 at BAS, then a 22-record group behind it: 23 records, full
            t.text('X')
            t.press('LEFT')
            t.press('DOWN')
            t.press('DOWN', mods=['SHIFT'], repeat=21)
            t.press('DEL')
            t.press('Z', mods=['CTRL'])     # the group goes to redo
            t.wait(1.0)
            t.snap('ungrouped')
            # The new record wraps onto R0, the head of the undo chain
            t.press('DOWN', repeat=25)
            t.text('Y')
            t.press('Z', mods=['CTRL'])
            t.wait(1.0)
            t.snap('undone')
            t.press('Z', mods=['CTRL'])
            t.wait(1.0)
            t.snap('undone2')
        elif variant == 'depth':
            for i in range(self.EDITS):     # one record per line
                t.text('Q')
                t.press('LEFT')
                t.press('DOWN')
            t.wait(1.0)
            t.snap('typed')
            t.press('Z', mods=['CTRL'], repeat=self.EDITS)
            t.wait(1.0)
            t.snap('undone')
        else:
            t.press('A', mods=['CTRL'])     # 60 lines: more than UNDOGMAX
            t.press('DEL')
            t.wait(1.0)
            t.snap('deleted')
            t.press('Z', mods=['CTRL'])
            t.wait(1.0)
            t.snap('undone')
        t.press('S', mods=['CTRL'])
        t.wait(3.0)
        t.snap('saved')
        return t

    def verify(self, ctx, runs):
        checks = []
        got = disk_lines(runs['evict'])
        want = self.LINES[21:]
        checks.append(Check('U7/evict/content', got == want,
                            'the evicted group is not replayed: Ctrl+Z x3 '
                            'undoes Z and Y and stops'
                            if got == want else
                            '%s lines, first %r' % (len(got) if got else got,
                                                    got[:3] if got else got)))
        checks.append(Check('U7/evict/undoptr',
                            runs['evict'].var('undone', 'UNDOPTR') == 0,
                            'history empty after the two typed records'))

        run = runs['selfloop']
        want = list(self.LINES)
        want[0] = 'X' + want[0]
        got = disk_lines(run)
        checks.append(Check('U7/selfloop/ungroup',
                            run.var('ungrouped', 'TOTLINES') == 60,
                            'TOTLINES = %s after undoing the group'
                            % run.var('ungrouped', 'TOTLINES')))
        checks.append(Check('U7/selfloop/content', got == want,
                            'Y undone once and stays undone'
                            if got == want else
                            'line 26 = %r' % (got[26] if got and
                                              len(got) > 26 else got)))
        checks.append(Check('U7/selfloop/empty',
                            run.var('undone2', 'UNDOPTR') == 0 and
                            run.var('undone2', 'REDOPTR') != 0,
                            'UNDOPTR %s, REDOPTR %s after the second Ctrl+Z'
                            % (run.var('undone2', 'UNDOPTR'),
                               run.var('undone2', 'REDOPTR'))))

        run = runs['depth']
        got = disk_lines(run)
        lost = self.EDITS - self.KEPT
        want = ['Q' + x if i < lost else x for i, x in enumerate(self.LINES)]
        kept = sum(1 for i in range(self.EDITS)
                   if got and i < len(got) and not got[i].startswith('Q'))
        checks.append(Check('U7/depth/content', got == want,
                            '%d edits, the ring kept the last %d across three '
                            'wraps' % (self.EDITS, self.KEPT) if got == want
                            else '%d of %d edits could be undone, expected %d'
                            % (kept, self.EDITS, self.KEPT)))

        run = runs['toobig']
        got = disk_lines(run)
        checks.append(Check('U7/toobig/dropped',
                            run.var('deleted', 'UNDOPTR') == 0 and
                            run.var('undone', 'TOTLINES') == 1 and
                            got == [''],
                            'a 60-line delete drops the history instead of '
                            'recording half of it' if got == [''] else
                            'UNDOPTR %s, TOTLINES %s, doc %r'
                            % (run.var('deleted', 'UNDOPTR'),
                               run.var('undone', 'TOTLINES'),
                               got[:3] if got else got)))
        return checks


class U8UndoDropped(Case):
    name = 'U8-undo-dropped'
    desc = 'an edit that moves text across lines unrecorded drops the history'
    origin = ('push-wrap and reflow shift line numbers and are not recorded; '
              'the record of an earlier edit then names the wrong line and '
              'Ctrl+Z overwrote it')
    variants = ('reflow', 'pushwrap')
    FULL = ' '.join(['WORD'] * 16) + 'S'        # 80 characters, no room
    LINES = {
        'reflow': ['AAA', 'BBB', 'C' * 80, 'L3', 'L4', 'L5 TARGET'],
        'pushwrap': ['FIRST', FULL, 'L2', 'L3', 'L4', 'L5'],
    }

    def config(self, ctx, variant=None):
        return UNDO_CFG.replace('WRAP=DEV', 'WRAP=TXT')

    def fixture(self, ctx, variant=None):
        return crlf(self.LINES[variant])

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.wait(1.0)
        t.press('DOWN', repeat=4)
        t.text('X')                         # recorded, on line 4
        t.press('UP', repeat=3)             # line 1, column 1
        if variant == 'reflow':
            t.press('LEFT')
            t.press('BS')                   # col 0 in WRAP_TXT: REFLOW
        else:
            t.text('Q')                     # full line: EDPSHWR
        t.wait(1.0)
        t.snap('moved')
        t.press('Z', mods=['CTRL'])
        t.wait(1.0)
        t.snap('undone')
        t.press('S', mods=['CTRL'])
        t.wait(3.0)
        t.snap('saved')
        return t

    def verify(self, ctx, runs):
        checks = []
        run = runs['reflow']
        got = disk_lines(run)
        want = ['AAA BBB', 'C' * 80, 'L3', 'XL4', 'L5 TARGET']
        checks.append(Check('U8/reflow/dropped',
                            run.var('moved', 'UNDOPTR') == 0,
                            'UNDOPTR = %s after the reflow'
                            % run.var('moved', 'UNDOPTR')))
        checks.append(Check('U8/reflow/content', got == want,
                            'Ctrl+Z leaves the reflowed document alone'
                            if got == want else 'got %r' % got))
        run = runs['pushwrap']
        got = disk_lines(run)
        checks.append(Check('U8/pushwrap/dropped',
                            run.var('moved', 'UNDOPTR') == 0 and
                            run.var('moved', 'TOTLINES') == 7,
                            'UNDOPTR %s, TOTLINES %s after the push'
                            % (run.var('moved', 'UNDOPTR'),
                               run.var('moved', 'TOTLINES'))))
        tail_ok = got is not None and got[3:] == ['L2', 'L3', 'XL4', 'L5']
        checks.append(Check('U8/pushwrap/content', tail_ok,
                            'Ctrl+Z leaves every shifted line alone'
                            if tail_ok else 'got %r' % got))
        return checks


class U9UndoLineEdits(Case):
    name = 'U9-undo-line-edits'
    desc = 'paste, word delete, markup wrap and a style toggle undo in one step'
    origin = ('EDINSRUN, ACTDWLFT, WRAPSEL and APPLSEL wrote lines with no '
              'record: Ctrl+Z skipped them and undid something older')
    variants = ('paste', 'wordel', 'wrapsel', 'style')
    LINES = ['HELLO WORLD', 'ALPHA BETA GAMMA', 'THIRD LINE HERE']

    def config(self, ctx, variant=None):
        if variant == 'wrapsel':
            return UNDO_CFG.replace('MARKUP=OFF', 'MARKUP=MD')
        return UNDO_CFG

    def fixture(self, ctx, variant=None):
        return crlf(self.LINES)

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.wait(1.0)
        if variant == 'paste':
            t.press('RIGHT', mods=['SHIFT'], repeat=5)
            t.press('C', mods=['CTRL'])
            t.press('DOWN')                 # deselects: (1, 5)
            t.press('V', mods=['CTRL'])
        elif variant == 'wordel':
            t.press('DOWN')
            t.press('RIGHT', repeat=10)     # just after BETA
            t.press('BS', mods=['GRAPH'])
        elif variant == 'wrapsel':
            t.press('RIGHT', mods=['SHIFT'], repeat=5)
            t.press('B', mods=['CTRL'])     # **HELLO**
        else:
            t.snap('before', vram=True)
            t.press('DOWN', mods=['SHIFT'], repeat=2)
            t.press('RIGHT', mods=['SHIFT'], repeat=3)
            t.press('B', mods=['CTRL'])     # bold across three lines
            t.wait(1.0)
            t.snap('styled', vram=True)
        t.wait(1.0)
        t.snap('edited')
        t.press('Z', mods=['CTRL'])
        t.wait(1.0)
        t.snap('undone', vram=(variant == 'style'))
        t.press('Z', mods=['SHIFT', 'CTRL'])
        t.wait(1.0)
        t.snap('redone', vram=(variant == 'style'))
        t.press('Z', mods=['CTRL'])
        t.wait(1.0)
        t.snap('undone2', vram=(variant == 'style'))
        t.press('S', mods=['CTRL'])
        t.wait(3.0)
        t.snap('saved')
        return t

    WHERE = {'paste': (1, 5), 'wordel': (1, 10), 'wrapsel': None,
             'style': (0, 0)}

    def verify(self, ctx, runs):
        checks = []
        for v in ('paste', 'wordel', 'wrapsel'):
            run = runs[v]
            got = disk_lines(run)
            edited = run.var('edited', 'UNDOPTR') != 0
            checks.append(Check('U9/%s/content' % v,
                                edited and got == self.LINES,
                                'recorded, and Ctrl+Z / redo / Ctrl+Z ends on '
                                'the original' if edited and got == self.LINES
                                else 'UNDOPTR %s, got %r'
                                % (run.var('edited', 'UNDOPTR'), got)))
            where = self.WHERE[v]
            if where:
                pos = (run.var('undone', 'DOCLINE'), run.var('undone', 'CURX'))
                checks.append(Check('U9/%s/cursor' % v, pos == where,
                                    'Ctrl+Z puts the cursor back at %s'
                                    % (where,) if pos == where else
                                    'cursor %s, expected %s' % (pos, where)))
        run = runs['style']
        before = run.blob('before', 'vram')
        styled = run.blob('styled', 'vram')
        undone = run.blob('undone', 'vram')
        undone2 = run.blob('undone2', 'vram')
        redone = run.blob('redone', 'vram')
        cur = [(0, 0)]
        changed = bool(vram.diff(before, styled, ignore_cells=cur))
        d1 = vram.diff(before, undone, ignore_cells=cur)
        d2 = vram.diff(before, undone2, ignore_cells=cur)
        again = bool(vram.diff(before, redone, ignore_cells=cur))
        checks.append(Check('U9/style/undo',
                            changed and not d1 and not d2 and again,
                            'bold across three lines: Ctrl+Z restores the '
                            'screen, redo brings it back'
                            if changed and not d1 and not d2 and again else
                            'styled %s, undo diff %d px, redo %s, undo2 diff '
                            '%d px' % (changed, len(d1), again, len(d2))))
        return checks

# --- H40 / H41  DISK ACTIVITY ON THE STATUS BAR ------------------------


class H40LoadProgress(Case):
    name = 'H40-load-progress'
    desc = ('a load shows a progress bar over the file size on the status '
            'bar, full at the end of the read, and leaves it clean')
    origin = ('2026-10-06: the 990-line manual took 15 s to load with nothing '
              'on screen, which read as a hang')
    absolute = True

    def fixture(self, ctx, variant=None):
        return crlf(numbered(40))

    def timeline(self, ctx, variant=None):
        t = Timeline(start=2.0)
        t.snap('loaded', at='LOADDOC.CLSFIL')
        t.snap('boot', at='MAINLOOP')
        t.t = 45.0
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        raw = run.snaps.get('loaded', {}).get('STATMSG')
        msg = bytes(raw).split(b'\0')[0] if raw is not None else None
        want = b'Loading... ' + b'\xdb' * 10 + b' 100%'
        after = asciiz(run, 'boot', 'STATMSG')
        return [
            Check('H40/progress', msg == want,
                  'STATMSG at the end of the read: %r (want %r)' % (msg, want)),
            Check('H40/cleared', after == '' and
                  run.var('boot', 'TOTLINES') == 40,
                  'STATMSG %r with %s lines once the editor is up'
                  % (after, run.var('boot', 'TOTLINES'))),
        ]


class H41BrowseBusy(Case):
    name = 'H41-browse-busy'
    desc = ('Ctrl+O says "Reading directory..." on the status bar while it '
            'scans, and a rescan says it on the information line')
    origin = ('2026-10-06: the first scan ran before the window opened, so '
              'Ctrl+O left the screen unchanged while the disk worked')

    def fixture(self, ctx, variant=None):
        return crlf(numbered(5))

    def disk_files(self, ctx, variant=None):
        files = Case.disk_files(self, ctx, variant)
        files['SUB\\NOTE.TXT'] = crlf(['NOTE'])
        return files

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.snap('boot')
        t.snap('scan', at='BRWSCNM.SCAN')       # armed before the key
        t.press('O', mods=['CTRL'])
        t.wait(2.0)
        t.snap('busy', at='BRWBUSY.DONE')       # SUB\ sorts first
        t.press('RETURN')
        t.wait(2.0)
        t.press('ESC')
        t.wait(1.0)
        t.snap('after')
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        scan = asciiz(run, 'scan', 'STATMSG')
        busy = asciiz(run, 'busy', 'BRWINF')
        after = asciiz(run, 'after', 'STATMSG')
        return [
            Check('H41/scan', scan == 'Reading directory...',
                  'STATMSG during the first scan: %r' % scan),
            Check('H41/busy', busy is not None and
                  busy.startswith('Reading directory...'),
                  'information line during the rescan: %r' % busy),
            Check('H41/cleared', after == '',
                  'STATMSG after the browser closed: %r' % after),
        ]


class H42IoBlocks(Case):
    name = 'H42-io-blocks'
    desc = ('a document across the 1 KB disk I/O buffer loads and saves back '
            'byte for byte: a CR LF split over two reads, lines split over '
            'several buffer flushes, a line over MAXCOLS kept to 255')
    origin = ('2026-10-06: loads read 256 B per call and saves wrote twice per '
              'line (394 s for the manual on S2ED); both now go through IOBUF, '
              'so the loader carries a CR across reads and the saver splits '
              'lines across flushes')
    variants = ('dos', 'unix')

    def _doc(self, variant):
        return io_fixture(b'\r\n' if variant == 'dos' else b'\n')

    def fixture(self, ctx, variant=None):
        return self._doc(variant)[0]

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.snap('loaded')
        t.press('S', mods=['CTRL'])
        t.wait(6.0)
        t.snap('saved')
        return t

    def verify(self, ctx, runs):
        checks = []
        for variant, run in sorted(runs.items()):
            _, want, count = self._doc(variant)
            eol = 0 if variant == 'dos' else 1
            got = run.session.extract(run.dsk, self.fixture_name)
            lines = run.var('loaded', 'TOTLINES')
            checks.append(Check('H42/%s/lines' % variant, lines == count,
                                'TOTLINES %s after the load (want %d)'
                                % (lines, count)))
            checks.append(Check('H42/%s/eol' % variant,
                                run.var('loaded', 'SAVEEOL') == eol,
                                'SAVEEOL %s (want %d)'
                                % (run.var('loaded', 'SAVEEOL'), eol)))
            if got == want:
                why = '%d bytes back, byte for byte' % len(got)
            elif got is None:
                why = 'no file on disk'
            else:
                at = next((i for i in range(min(len(got), len(want)))
                           if got[i] != want[i]), min(len(got), len(want)))
                why = ('%d bytes, want %d; first difference at %d: %r / %r'
                       % (len(got), len(want), at, got[at:at + 12],
                          want[at:at + 12]))
            checks.append(Check('H42/%s/content' % variant, got == want,
                                why))
        return checks

# --- R1-R4  RECORD STORE UNDER PRESSURE (RC1 REVIEW, 2026-10-06) ------
#
# On the 128 kB machine the text lives in one 16 KB segment. These fixtures
# fill it to within a few bytes with 36-byte records (lines of 16 characters
# or fewer), so the next record that does not fit forces SEGCOMP exactly where
# the defect was.

def short_lines(count, first=0):
    """Lines of exactly 16 characters: one default 36-byte record each."""
    return ['R%04d ABCDEFGHIJ' % i for i in range(first, first + count)]


SEG_FULL = 455          # 455 * 36 = 16380 of 16384 bytes


class R1FreeListCompact(Case):
    name = 'R1-freelist-compact'
    desc = ('two short lines deleted, then a line grown past 16 characters '
            'with the segment full: the compaction walks the freed records')
    origin = ('2026-10-06 review: FREEPSH wrote its link over RECCAP and the '
              'low byte of RECLEN, so SEGCOMP sized a freed record by the link '
              'and took it for a live one -- a slide by garbage, LINEOFF past '
              '16 KB, records allocated in page 3')

    LINES = short_lines(SEG_FULL)

    def fixture(self, ctx, variant=None):
        return crlf(self.LINES)

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.snap('boot')
        t.press('Y', mods=['CTRL'])
        t.wait(1.0)
        t.press('Y', mods=['CTRL'])
        t.wait(1.0)
        t.snap('deleted')
        t.text('X')                     # 17 characters: a 68-byte record
        t.wait(15.0)                    # SEGCOMP + DIRUPDOF over 453 lines
        t.snap('grown')
        # Two new lines at the end of it. The first takes the one record
        # on the free list; the second finds the list empty and the segment
        # full, and is refused. A list that survived the compaction still
        # names offset 36 -- now a live, slid record -- and hands it out.
        t.press('RIGHT', repeat=16)
        t.press('RETURN')
        t.wait(2.0)
        t.press('RETURN')
        t.wait(15.0)
        t.snap('entered')
        t.press('S', mods=['CTRL'])
        t.wait(6.0)
        t.snap('saved')
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        want = crlf(['X' + self.LINES[2], ''] + self.LINES[3:])
        got = run.session.extract(run.dsk, 'DOC.TXT')
        # The two dead records go (72 B), the 453 live ones slide down,
        # the grown line takes 68 B at the tail, and its old 36-byte record
        # is retired onto the -- just emptied -- free list.
        want_off = (SEG_FULL - 2) * 36 + 68
        off = run.var('grown', 'LINEOFF')
        return [
            Check('R1/boot', run.var('boot', 'LINEOFF') == SEG_FULL * 36,
                  'LINEOFF %s after the load (want %d)'
                  % (run.var('boot', 'LINEOFF'), SEG_FULL * 36)),
            Check('R1/compacted', off == want_off and
                  run.var('grown', 'TOTLINES') == SEG_FULL - 2,
                  'LINEOFF %s (want %d), TOTLINES %s after the growth'
                  % (off, want_off, run.var('grown', 'TOTLINES'))),
            Check('R1/freelist', run.var('grown', 'FREEHD') != 0xFF and
                  run.var('grown', 'FREEOF') == 0,
                  'FREEHD %s FREEOF %s: the retired record, slid to offset 0'
                  % (run.var('grown', 'FREEHD'), run.var('grown', 'FREEOF'))),
            Check('R1/entered', run.var('entered', 'TOTLINES') == SEG_FULL - 1
                  and run.var('entered', 'LINEOFF') == want_off,
                  'TOTLINES %s (want %d), LINEOFF %s: one Return from the '
                  'free list, the second refused'
                  % (run.var('entered', 'TOTLINES'), SEG_FULL - 1,
                     run.var('entered', 'LINEOFF'))),
            Check('R1/content', got == want, disk_diff(got, want)),
        ]


class R2LinewrtOom(Case):
    name = 'R2-linewrt-oom'
    desc = ('a line grown past its record with the segment full and nothing '
            'to compact: the growth is refused and the document is intact')
    origin = ('2026-10-06 review: LINEWRT tombstoned the old record before '
              'NEWREC, so an OOM left the directory on a dead record, read '
              'back as 255 bytes of its neighbours')

    LINES = short_lines(SEG_FULL)

    def fixture(self, ctx, variant=None):
        return crlf(self.LINES)

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.snap('boot')
        t.text('X')
        t.wait(15.0)
        t.snap('refused')
        t.press('S', mods=['CTRL'])
        t.wait(6.0)
        t.snap('saved')
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        want = crlf(self.LINES)
        got = run.session.extract(run.dsk, 'DOC.TXT')
        return [
            Check('R2/alive', run.var('saved', 'SCRRDY') == 0xFF and
                  run.var('refused', 'TOTLINES') == SEG_FULL,
                  'SCRRDY %s, TOTLINES %s'
                  % (run.var('saved', 'SCRRDY'),
                     run.var('refused', 'TOTLINES'))),
            Check('R2/content', got == want, disk_diff(got, want)),
        ]


class R3UndoCompactIX(Case):
    name = 'R3-undo-compact-ix'
    desc = ('undeleting a long line when the segment is full: UNDORST holds '
            'its record in IX across a NEWREC that compacts')
    origin = ('2026-10-06 review: SEGCOMP repaints the status bar, and B2D16 '
              'zeroes IX; UNDORST / UNDOSWP then wrote their record over '
              'page 0')

    LONG = 'LONG LINE 0123456'          # 17 characters: a 68-byte record
    LINES = [LONG] + short_lines(453)   # 68 + 453 * 36 = 16376

    def fixture(self, ctx, variant=None):
        return crlf(self.LINES)

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.snap('boot')
        t.press('Y', mods=['CTRL'])
        t.wait(1.0)
        t.snap('deleted')
        t.press('Z', mods=['CTRL'])
        t.wait(15.0)
        t.snap('undone')
        t.press('S', mods=['CTRL'])
        t.wait(6.0)
        t.snap('saved')
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        want = crlf(self.LINES)
        got = run.session.extract(run.dsk, 'DOC.TXT')
        return [
            Check('R3/deleted', run.var('deleted', 'TOTLINES') == 453,
                  'TOTLINES %s after Ctrl+Y' % run.var('deleted', 'TOTLINES')),
            Check('R3/undone', run.var('undone', 'TOTLINES') == 454 and
                  run.var('saved', 'SCRRDY') == 0xFF,
                  'TOTLINES %s after Ctrl+Z, SCRRDY %s'
                  % (run.var('undone', 'TOTLINES'),
                     run.var('saved', 'SCRRDY'))),
            Check('R3/content', got == want, disk_diff(got, want)),
        ]


class R4UndoLongLine(Case):
    name = 'R4-undo-long-line'
    desc = ('undo of an edit on a line longer than an undo record (TEXTCOLS): '
            'never a half-restored line')
    origin = ('2026-10-06 review: UNDOPAK / UNDOUPK keep TEXTCOLS characters '
              'but the length byte whole, so a restore kept the edited tail '
              'past TEXTCOLS; and a redo of a line the edit made too long '
              'brought back a truncated image')
    variants = ('long', 'redo')

    @staticmethod
    def _line(n):
        return ''.join(chr(65 + i % 26) for i in range(n))

    def _first(self, variant):
        return self._line(90 if variant == 'long' else 80)

    def fixture(self, ctx, variant=None):
        return crlf([self._first(variant), 'SECOND LINE'])

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.snap('boot')
        t.text('X')
        t.wait(1.0)
        t.snap('typed')
        t.press('Z', mods=['CTRL'])
        t.wait(1.0)
        t.snap('undone')
        t.press('Z', mods=['SHIFT', 'CTRL'])
        t.wait(1.0)
        t.snap('redone')
        t.press('S', mods=['CTRL'])
        t.wait(3.0)
        t.snap('saved')
        return t

    def verify(self, ctx, runs):
        checks = []
        for variant, run in sorted(runs.items()):
            first = self._first(variant)
            got = run.session.extract(run.dsk, 'DOC.TXT')
            if variant == 'long':
                # 90 > TEXTCOLS: the edit drops the history, so Ctrl+Z and
                # Ctrl+Shift+Z do nothing and the typed X stays.
                want = crlf(['X' + first, 'SECOND LINE'])
                checks.append(Check(
                    'R4/long/dropped', run.var('typed', 'UNDOPTR') == 0,
                    'UNDOPTR %s after typing on a %d-character line (want 0)'
                    % (run.var('typed', 'UNDOPTR'), len(first))))
            else:
                # 80 fits a record, 81 does not: the undo is exact and the
                # redo is withdrawn rather than replayed from a truncated image.
                want = crlf([first, 'SECOND LINE'])
                checks.append(Check(
                    'R4/redo/withdrawn', run.var('undone', 'REDOPTR') == 0,
                    'REDOPTR %s after the undo (want 0)'
                    % run.var('undone', 'REDOPTR')))
            checks.append(Check('R4/%s/content' % variant, got == want,
                                disk_diff(got, want)))
        return checks


def disk_diff(got, want):
    if got == want:
        return '%d bytes, byte for byte' % len(got)
    if got is None:
        return 'no file on disk'
    at = next((i for i in range(min(len(got), len(want)))
               if got[i] != want[i]), min(len(got), len(want)))
    return ('%d bytes, want %d; first difference at %d: %r / %r'
            % (len(got), len(want), at, got[at:at + 16], want[at:at + 16]))

# --- K1-K3  DISK ERRORS HALFWAY (RC1 REVIEW, 2026-10-06) ---------------


def eject_at(ctx, label, nth=1):
    """Tcl: eject drive A the nth time our code reaches `label`.

    Gated on the label's own opcodes, as every snapshot breakpoint is: with
    the image below #4000 the address is also DOS 2 kernel code at times.
    """
    addr = ctx.sym[label]
    com = os.path.join(ctx.code_dir, ctx.prefix + '.COM')
    with open(com, 'rb') as fh:
        sig = list(fh.read()[addr - 0x100:addr - 0x100 + 4])
    checks = ' '.join(
        'if {[rb %d] != %d} return;' % (addr + i, b) for i, b in enumerate(sig))
    return ('set ::ejn 0; debug set_bp %d {} {%s incr ::ejn; '
            'if {$::ejn == %d} {diska eject; p "EJECTED"}}' % (addr, checks, nth))


class K1WqSaveFailed(Case):
    name = 'K1-wq-save-failed'
    desc = ':wq and :x stay in the editor when the save fails'
    origin = ('2026-10-06 review: .WQDO called FILESAVE and jumped to TERM '
              'without testing CY -- "[SAVE ERROR]", then the document gone')
    machine = MACH_2MB                  # two drives: B: is empty
    variants = ('wq', 'x')

    def config(self, ctx, variant=None):
        return DEFAULT_CFG.replace('PROFILE=STD', 'PROFILE=VI')

    def fixture(self, ctx, variant=None):
        return crlf(['LINE 1', 'LINE 2'])

    def type_str(self, t, s):
        for ch in s:
            k, mods = H27ViEx.key_for(self, ch)
            t.press(k, mods=mods)

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.snap('boot')
        self.type_str(t, ':w B:\\OUT.TXT')  # names the document B:\OUT.TXT
        t.press('RETURN')
        t.wait(4.0)
        self.type_str(t, ':' + variant)
        t.press('RETURN')
        t.wait(4.0)
        t.snap('after')
        return t

    def verify(self, ctx, runs):
        checks = []
        for variant, run in sorted(runs.items()):
            msg = asciiz(run, 'after', 'STATMSG')
            checks.append(Check(
                'K1/%s/stayed' % variant,
                run.var('after', 'SCRRDY') == 0xFF and msg == '[SAVE ERROR]',
                'after :%s -- SCRRDY %s, STATMSG %r (want the editor up, '
                'saying [SAVE ERROR])' % (variant, run.var('after', 'SCRRDY'),
                                          msg)))
        return checks


class K2LoadDiskError(Case):
    name = 'K2-load-disk-error'
    desc = ('a disk error halfway through a load rolls it back: no garbage '
            'lines, no file name left for Ctrl+S to overwrite')
    origin = ('2026-10-06 review: LOADDOC tested only HL after DSKREAD; on an '
              'abort DSKABTH leaves a kernel word in HL, read as a byte count')
    absolute = True

    def fixture(self, ctx, variant=None):
        return crlf(numbered(90, width=40))     # ~4 KB: four 1 KB reads

    def timeline(self, ctx, variant=None):
        t = Timeline(start=0.0)
        t.at(eject_at(ctx, 'LOADDOC.READBLK', nth=2))
        t.wait(40.0)
        t.snap('boot')                  # the next MAINLOOP pass after 40 s
        t.t = 80.0
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        name = asciiz(run, 'boot', 'FILENAME')
        return [
            Check('K2/ejected', any(l == 'EJECTED' for l in run.lines),
                  'drive A ejected during the second read'),
            Check('K2/rolled-back',
                  run.var('boot', 'TOTLINES') == 1 and
                  run.var('boot', 'LOADERR') == 0 and name == '',
                  'TOTLINES %s, LOADERR %s, FILENAME %r (want 1, 0, empty: '
                  'a read error, not a load of garbage)'
                  % (run.var('boot', 'TOTLINES'), run.var('boot', 'LOADERR'),
                     name)),
        ]


class K3SaveCloseError(Case):
    name = 'K3-save-close-error'
    desc = 'a save whose close fails says so and keeps the document modified'
    origin = ('2026-10-06 review: FILESAVE ignored the DSKCLOSE carry (and '
              'CFGSAVE every write), so a failed save showed "[SAVED]"')

    def fixture(self, ctx, variant=None):
        return crlf(['LINE 1', 'LINE 2'])

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.snap('boot')
        t.text('X')
        t.at(eject_at(ctx, 'DSKCLSW'))
        t.press('S', mods=['CTRL'])
        t.wait(6.0)
        t.snap('after')
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        msg = asciiz(run, 'after', 'STATMSG')
        return [
            Check('K3/ejected', any(l == 'EJECTED' for l in run.lines),
                  'drive A ejected before the close'),
            Check('K3/reported', msg == '[SAVE ERROR]' and
                  run.var('after', 'MODIFIED') != 0,
                  'STATMSG %r, MODIFIED %s (want [SAVE ERROR], still modified)'
                  % (msg, run.var('after', 'MODIFIED'))),
        ]


CASES = [G1Image(), G2Save(), G3Oom(), G3BOomShort(), G4FreeList(), G5Clock(), G6Hooks(),
         G7Selection(), G8Config(), G9Directory(), G10Autoalign(), G11Paste(),
         G12ScreenRestore(), G13FeatureResidency(), H1Help(), H2HelpQuestion(), H3HelpFile(), H4FileSwitch(), H5Verbose(), H6DatMissing(), H7AboutDialog(),
         H8DatBadMagic(), H9DatBadVersion(), H10DatNoBlocks(),
         H11DatTruncHdr(), H12DatTruncTbl(), H13DatLenZero(), H14DatLenOver(),
         H15DatBadBlkID(), H16DatTruncPay(), H17DatPadded(), H18WindowRobustness(),
         H19QuitDialog(), H20QuitDirty(), H21Shadow(), H22FileMenu(), H23MenuNav(),
         H24GoToLine(), H25FindReplace(), H26FindCurrentLine(), H27ViEx(),
         H28TextWidth(), H29HomePath(), H30NewDocument(), H31EditOpen(),
         H32SaveNoName(), H33LongPath(), H34BrowseOpen(),
         H35BrowseMany(), H36BrowseSaveAs(), H37Settings(), H38DiskError(), H39DatForeign(),
         H40LoadProgress(), H41BrowseBusy(), H42IoBlocks(),
         R1FreeListCompact(), R2LinewrtOom(), R3UndoCompactIX(), R4UndoLongLine(),
         K1WqSaveFailed(), K2LoadDiskError(), K3SaveCloseError(),
         B2Font(), B3Rom(), B4CfgStream(), B5ShippedDisk(), F1Scroll(), F2Keyrun(),
         D1Insert(), D2Enter(), D3Backspace(), D4Delete(), D5WordLineDel(), D6Reflow(),
         D7Tabs(), D8Accents(), D9Kana(), D10Markup(), D11Margin(), D12LongLine(),
         E1Cut(), E2Paste(), E3SelScroll(), E4SelAllDel(), E5Replace(), E6SelWordPage(), E7ClipLimit(),
         I1UnixAuto(), I2DosAuto(), I3ConvertDosToUnix(), I4ConvertUnixToDos(),
         U1UndoMod(), U2UndoDel(), U3UndoSplit(), U4UndoJoin(), U5UndoSel(),
         U6UndoSelDel(), U7UndoRing(), U8UndoDropped(), U9UndoLineEdits()]


def run(ctx, cases):
    checks = []
    for case in cases:
        try:
            runs = case.execute(ctx)
        except Exception as exc:                          # noqa: BLE001
            checks.append(Check(case.name, False, 'harness error: %s' % exc))
            continue
        broken = [v for v, r in runs.items()
                  if r.timed_out or 'DONE' not in r.lines]
        if broken:
            checks.append(Check(case.name, False,
                                'session did not finish: %s'
                                % ', '.join(str(v) for v in broken)))
            continue
        try:
            checks += case.verify(ctx, runs)
        except Exception as exc:                          # noqa: BLE001
            checks.append(Check(case.name, False,
                                'verify error: %s: %s'
                                % (type(exc).__name__, exc)))
    return checks
