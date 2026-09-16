"""Self-test: put each defect back and prove the Gate still bites.

A suite that has only ever been green says nothing about what it would catch.
Every mutation here is the ACTUAL defect as it shipped, reintroduced verbatim,
with the checks that must go red.  Run it after changing the suite, and after
any refactor that moves the code these cases reach into.
"""

import os
import shutil

MUTATIONS = [
    {
        'name': 'g2-dcreate',
        'why': 'DOS 2 _CREATE refuses an existing file when B bit 7 is set',
        'file': 'BDOS.Z8A',
        'old': 'LD      B, 0            ; B = 0: NORMAL FILE, OVERWRITE EXISTING (B7=0)',
        'new': 'LD      B, #80          ; MUTATION: DO NOT OVERWRITE',
        'filter': 'G2',
        'expect': ['G2/content'],
    },
    {
        'name': 'g4-freelist',
        'why': 'LINEDEL abandons the record instead of handing it back',
        'file': 'BUFFER.Z8A',
        'old': 'CALL    FREEPSH         ; HAND THE RECORD BACK BEFORE IT IS LOST',
        'new': 'NOP                     ; MUTATION: LEAK THE RECORD',
        'filter': 'G4',
        'expect': ['G4/no-growth'],
    },
    {
        'name': 'g5-hmmv',
        'why': 'the HH:MM clear truncated to byte units leaves two pixel columns',
        'file': 'UI.Z8A',
        'old': 'LD      HL, 5 * CELLW   ; 5 GLYPHS',
        'new': 'LD      HL, 28          ; MUTATION: HMMV BYTE TRUNCATION',
        'filter': 'G5',
        # Which sample goes red depends on which digits happen to change, so
        # the requirement is that at least one of them does.  G5 guarantees a
        # revealing transition is in the window; see the note on SAMPLES.
        'expect_any': ['G5/c%d' % i for i in range(9)],
    },
    {
        'name': 'g7-selrange',
        'why': 'the painted range overlaps SELDIFF\'s own scratch',
        'file': 'VARS.Z8A',
        'old': """DRWSTRL         DEFW    0               ; PAINTED START LINE
DRWSTRX         DEFB    0               ; PAINTED START COL
DRWENDL         DEFW    0               ; PAINTED END LINE
DRWENDX         DEFB    0               ; PAINTED END COL""",
        'new': """DRWSTRL         DEFW    0               ; PAINTED START LINE
SELTMPL2        DEFW    0               ; MUTATION: SCRATCH BEHIND THE RECORD
SELTMPXA2       DEFB    0
SELTMPXB2       DEFB    0
DRWSTRX         EQU     DRWSTRL + 2
DRWENDL         EQU     DRWSTRL + 3
DRWENDX         EQU     DRWSTRL + 5""",
        'also': [('VARS.Z8A',
                  """SELTMPL         DEFW    0               ; TEMP LINE VAR
SELTMPXA        DEFB    0               ; TEMP COL XA
SELTMPXB        DEFB    0               ; TEMP COL XB""",
                  """SELTMPL         EQU     SELTMPL2
SELTMPXA        EQU     SELTMPXA2
SELTMPXB        EQU     SELTMPXB2""")],
        'filter': 'G7',
        'expect': ['G7/render-pure'],
        'expect_static': ['record-exclusive'],
    },
    {
        'name': 'g9-dirbank',
        'why': 'DIRBANK lets PUTP2 destroy the line number in HL',
        'file': 'BUFFER.Z8A',
        'old': """DIRBANK         PUSH    HL
                LD      A, (DIRSEG)
                LD      (TXSEG), A
                CALL    PUTP2
                POP     HL
                RET""",
        'new': """DIRBANK         LD      A, (DIRSEG)
                LD      (TXSEG), A
                CALL    PUTP2
                RET""",
        'filter': 'G9',
        'expect': ['G9/round-trip'],
    },
    {
        'name': 'g10-align',
        'why': 'the align gate tests CURX == length instead of CURX >= length',
        'file': 'ACTION.Z8A',
        'old': 'JR      C, .PLAIN       ; CURX < LENGTH: GENUINELY MID-LINE',
        'new': 'JR      NZ, .PLAIN      ; MUTATION: ONLY WHEN EXACTLY EQUAL',
        'filter': 'G10',
        'expect': ['G10/no-trailing-spaces'],
    },
    {
        'name': 'b2-font',
        'why': 'EXPNORM fails to expand high bit of ink color 1',
        'file': 'FONT.Z8A',
        'old': """                SET     6, H
.P1             ADD     A, A""",
        'new': """                RES     6, H            ; MUTATION: PIXEL 0 LOST
.P1             ADD     A, A""",
        'filter': 'B2',
        'expect': ['B2/vram-tables'],
    },
    {
        'name': 'b3-rom',
        'why': 'UI does not show [ROM] indicator when S6ED.FNT is missing',
        'file': 'UI.Z8A',
        'old': """                LD      HL, .STRROM
                JR      Z, .PUTFNT
                LD      HL, .STRNOFN""",
        'new': """                LD      HL, .STRNOFN    ; MUTATION: SILENT FALLBACK
                JR      Z, .PUTFNT
                LD      HL, .STRNOFN""",
        'filter': 'B3',
        'expect': ['B3/status-bar-rom'],
    },
    {
        'name': 'f1-scroll',
        'why': 'SCRLDNN scrolls to the wrong destination scanline',
        'file': 'SCROLL.Z8A',
        'old': """                LD      HL, TXORG_Y     ; DY = TOP OF ROW 1
                LD      (VDP_DY), HL""",
        'new': """                LD      HL, TXORG_Y + 8 ; MUTATION: DESTINATION SHIFTED BY ONE ROW
                LD      (VDP_DY), HL""",
        'filter': 'F1',
        'expect': ['F1/render-pure'],
    },
    {
        'name': 'f2-keyrun',
        'why': 'bottom-row scroll does not advance viewport TOPLINE',
        'file': 'EDIT.Z8A',
        'old': """                LD      HL, (TOPLINE)
                ADD     HL, DE
                LD      (TOPLINE), HL
                LD      A, E
                CP      SCRROWS""",
        'new': """                LD      HL, (TOPLINE)
                ADD     HL, DE
                NOP                     ; MUTATION: TOPLINE NOT ADVANCED
                NOP
                NOP
                LD      A, E
                CP      SCRROWS""",
        'filter': 'F2',
        'expect': ['F2/burst-collapsed'],
    },
]


class Applied(object):
    """Applies one mutation and always puts the sources back."""

    def __init__(self, ctx, mut):
        self.ctx = ctx
        self.mut = mut
        self.backups = {}

    def __enter__(self):
        edits = [(self.mut['file'], self.mut['old'], self.mut['new'])]
        edits += self.mut.get('also', [])
        for fname, old, new in edits:
            path = os.path.join(self.ctx.src_dir, fname)
            if path not in self.backups:
                self.backups[path] = path + '.mutbak'
                shutil.copy(path, self.backups[path])
            with open(path) as fh:
                text = fh.read()
            if old not in text:
                self.__exit__(None, None, None)
                raise RuntimeError('mutation %s: anchor not found in %s'
                                   % (self.mut['name'], fname))
            with open(path, 'w') as fh:
                fh.write(text.replace(old, new, 1))
        return self

    def __exit__(self, *exc):
        for path, bak in self.backups.items():
            if os.path.exists(bak):
                shutil.move(bak, path)
        return False
