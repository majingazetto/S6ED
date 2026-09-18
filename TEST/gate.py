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
from cases import Case, DEFAULT_CFG, crlf, numbered
from harness import MACH_128K, MACH_JP
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
    desc = 'mapper exhaustion truncates, keeps the editor alive, refuses Enter'
    origin = ('STORLINE claimed a text segment without setting APPSEG, so the '
              'first Return overwrote a loaded line; and NEWREC ended in '
              'JP C, ERRMEM, which threw the whole document away')
    machine = MACH_128K
    FIXTURE_LINES = 400
    # 128 kB DOS 2: 2 free segments, both reserved (DIRSEG + FTRSEG), so the
    # text pool is DEFSEG2 alone = LINEPSEG lines. Was 202 before FTRSEG.
    CAPACITY = 101

    def fixture(self, ctx, variant=None):
        return crlf(numbered(self.FIXTURE_LINES))

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.snap('loaded')
        # One Return with the mapper full: it must be refused, and refused
        # without touching the document or the cursor.
        t.press('RETURN')
        t.snap('refused')
        t.press('S', mods=['CTRL'])
        t.wait(3.0)
        t.snap('saved')
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        tot = run.var('loaded', 'TOTLINES')
        checks = [
            Check('G3/truncated', tot == self.CAPACITY,
                  'loaded %s of %d lines (capacity %d)'
                  % (tot, self.FIXTURE_LINES, self.CAPACITY)),
            Check('G3/alive', run.var('refused', 'SCRRDY') == 0xFF,
                  'editor still running after the refusal'),
        ]
        for name in ('TOTLINES', 'DOCLINE', 'CURX', 'LINEOFF'):
            checks.append(Check('G3/refusal-%s' % name.lower(),
                                run.var('loaded', name) == run.var('refused', name),
                                '%s %s -> %s' % (name, run.var('loaded', name),
                                                 run.var('refused', name))))
        got = run.session.extract(run.dsk, 'DOC.TXT')
        want = crlf(numbered(self.FIXTURE_LINES)[:tot]) if tot else None
        checks.append(Check('G3/document-intact', got == want,
                            'the %s loaded lines survive byte for byte' % tot
                            if got == want else
                            'saved %d bytes, expected %d'
                            % (len(got or b''), len(want or b''))))
        return checks


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
    desc = 'every S6ED.CFG key parsed with spaces around the ='
    origin = ('CFGVAL matched the key as a bare prefix, so "TABWIDTH = 8" with '
              'spaces failed and the whole line was ignored -- reported as '
              '"the CFG is ignored"')
    cfg = ("; spaced form, trailing comments, CRLF\r\n"
           "PROFILE = VI\r\n"
           "WRAP  =  TXT\r\n"
           "MARKUP = LIT\r\n"
           "CLOCK = 0\r\n"
           "TABWIDTH = 8\r\n"
           "EOL = UNIX\r\n"
           "AUTOALIGN = ON\r\n"
           "THEME = AMBER\r\n")
    # THMAMBR in CFG.Z8A
    AMBER = [0x00, 0x00, 0x70, 0x04, 0x20, 0x01, 0x70, 0x06]

    def fixture(self, ctx, variant=None):
        return crlf(numbered(5))

    def timeline(self, ctx, variant=None):
        t = Timeline()
        t.snap('boot', palette=True)
        return t

    def verify(self, ctx, runs):
        run = one(runs)
        want = [('KMAPID', 3, 'PROFILE=VI'), ('WRAPMODE', 1, 'WRAP=TXT'),
                ('MKUPMD', 2, 'MARKUP=LIT'), ('SHOWCLK', 0, 'CLOCK=0'),
                ('TABWIDTH', 8, 'TABWIDTH=8'), ('SAVEEOL', 1, 'EOL=UNIX'),
                ('AUTOALGN', 1, 'AUTOALIGN=ON')]
        checks = [Check('G8/%s' % why.split('=')[0].lower(),
                        run.var('boot', name) == value,
                        '%s -> %s = %s' % (why, name, run.var('boot', name)))
                  for name, value, why in want]
        pal = run.snaps.get('boot', {}).get('PALDATA')
        checks.append(Check('G8/theme', pal == self.AMBER,
                            'PALDATA = %s' % (' '.join('%02X' % b for b in pal)
                                              if pal else '?')))
        vdp = run.blob('boot', 'pal')
        checks.append(Check('G8/vdp-palette',
                            vdp is not None and list(vdp[:8]) == self.AMBER,
                            'VDP palette registers 0-3 match the theme'
                            if vdp else 'no palette dump'))
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
        t.press('DOWN', repeat=30)
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
            if off > SEGLAST or off % LINEREC:
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
              'and did not formally restore screen mode, line width or text colors')

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
        t.snap('boot', palette=True)
        # 2. Arm exit snap at TERM.TERMDON so breakpoint is active when TERM runs
        t.snap('exit', palette=True, at='TERM.TERMDON')
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

        return checks


# --- G13 FEATURE SEGMENT RESIDENCY & INTER-SEGMENT INTEGRITY ------------


class G13FeatureResidency(Case):
    name = 'G13-feature-residency'
    desc = 'FTRSEG stays resident in SEGTBL[1], HOMESEG clean at idle, CFG applied'
    origin = ('Fase 1b inter-segment architecture: feature code lives in FTRSEG, '
              'is copied at boot, and retains residency across execution')
    cfg = ("; spaced form, trailing comments, CRLF\r\n"
           "PROFILE = WS\r\n"
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
        """The version the banner must show, straight from CONST.Z8A."""
        with open(os.path.join(ctx.src_dir, 'CONST.Z8A')) as fh:
            src = fh.read()
        maj = re.search(r"\.MAJOR\s+EQU\s+'(.)'", src).group(1)
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
        # 1. Open with F1, close with RETURN
        t.press('F1')
        t.snap('dialog1', vram=True, at='WINPOLL')
        t.press('RETURN')
        t.snap('after_ret', vram=True)
        # 2. Open with F1, close with SPACE
        t.press('F1')
        t.snap('dialog2', vram=True, at='WINPOLL')
        t.press('SPACE')
        t.snap('after_spc', vram=True)
        # 3. Open with F1, close with ESC
        t.press('F1')
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
                            hi_pixels > 500,
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
           "PROFILE = WS\r\n"
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
        # Inject stray space into BIOS buffer right as F1 opens modal
        t.at('type " "')
        t.press('F1')
        t.snap('modal_open', vram=True, at='WINPOLL')
        # Close with RETURN
        t.press('RETURN')
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
            Check('D1/curx', run.var('saved', 'CURX') == 79,
                  'CURX = %s (expected 79)' % run.var('saved', 'CURX')),
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
    # With the clock off that phase is fixed, so the run is deterministic and
    # what decides it is how many presses are made and how fast.  Measured
    # against the defect put back (mutation d8-double): the row typed twice at
    # the default gap never reproduced it, and at 50 ms it depended on the gap
    # to the millisecond.  Typed FOUR times with 50 ms between presses it goes
    # red at every gap tried from 20 to 120 ms -- 36 presses drift far enough
    # through the phase that one of them always lands in the window.  The
    # fixed build is byte for byte correct at every one of those gaps.
    GRAPH_ROW = 'AEIOUNW1/'
    GRAPH_PASSES = 4
    GRAPH_GAP = 0.050

    def timeline(self, ctx, variant=None):
        t = Timeline()
        # Line 0: unshifted GRAPH combinations (á é í ó ú ñ ü ¡ ¿), four times
        for key in self.GRAPH_PASSES * self.GRAPH_ROW:
            t.press(key, mods=['GRAPH'], tail=self.GRAPH_GAP)
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


CASES = [G1Image(), G2Save(), G3Oom(), G4FreeList(), G5Clock(), G6Hooks(),
         G7Selection(), G8Config(), G9Directory(), G10Autoalign(), G11Paste(),
         G12ScreenRestore(), G13FeatureResidency(), H1Help(), H2HelpQuestion(), H3HelpFile(), H4FileSwitch(), H5Verbose(), H6DatMissing(), H7AboutDialog(),
         H8DatBadMagic(), H9DatBadVersion(), H10DatNoBlocks(),
         H11DatTruncHdr(), H12DatTruncTbl(), H13DatLenZero(), H14DatLenOver(),
         H15DatBadBlkID(), H16DatTruncPay(), H17DatPadded(), H18WindowRobustness(),
         H19QuitDialog(), H20QuitDirty(),
         B2Font(), B3Rom(), F1Scroll(), F2Keyrun(),
         D1Insert(), D2Enter(), D3Backspace(), D4Delete(), D5WordLineDel(), D6Reflow(),
         D7Tabs(), D8Accents(), D9Kana(), D10Markup(),
         E1Cut(), E2Paste(), E3SelScroll(), E4SelAllDel(), E5Replace(), E6SelWordPage(), E7ClipLimit(),
         I1UnixAuto(), I2DosAuto(), I3ConvertDosToUnix(), I4ConvertUnixToDos()]


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
