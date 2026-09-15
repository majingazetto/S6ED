"""The Gate -- the cases that must pass before an integration is closed.

Each one was derived backwards from a defect that actually reached `dev` and
had to be hunted down with the emulator afterwards.  The point is not coverage:
it is that the whole set runs at the end of EVERY integration, whatever was
touched, because not one of these defects was found by the feature that broke
it.  `origin` on each case says which.
"""

import hashlib
import os

import vram
from cases import Case, DEFAULT_CFG, crlf, numbered
from harness import MACH_128K
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
        return crlf(numbered(120))

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
    FLOOR = 180                 # capacity below this is a regression, not noise

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
            Check('G3/truncated', tot is not None and
                  self.FLOOR <= tot < self.FIXTURE_LINES,
                  'loaded %s of %d lines (floor %d)'
                  % (tot, self.FIXTURE_LINES, self.FLOOR)),
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
    # transition.  Nine samples 31 s apart span ~4.1 minutes: at least four.
    SAMPLES = [3.0 + 31.0 * i for i in range(9)]
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


CASES = [G1Image(), G2Save(), G3Oom(), G4FreeList(), G5Clock(), G6Hooks(),
         G7Selection(), G8Config(), G9Directory(), G10Autoalign(), G11Paste()]


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
