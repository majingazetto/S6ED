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
        'expect_any': ['G5/c%d' % i for i in range(7)],
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
        'name': 'f1a-noftr',
        'why': 'SEGRESV skips the mandatory FTRSEG claim, so the text pool '
               'keeps the segment and the 128 kB ceiling goes back to 202',
        'file': 'MAPPER.Z8A',
        'old': """                CALL    SEGGET          ; 2: FEATURE SEGMENT
                JP      C, .NOFTR
                LD      (FTRSEG), A""",
        'new': """                XOR     A               ; MUTATION: NO FEATURE RESERVATION
                LD      (FTRSEG), A""",
        'filter': 'G3',
        'expect': ['G3/truncated'],
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
    {
        'name': 'd1-insert',
        'why': 'EDINSCHR fails to shift and insert characters',
        'file': 'EDIT.Z8A',
        'old': """                LD      A, (CURX)
                CALL    WBINS           ; TEXT + ATTRS SHIFTED, LENGTH UPDATED""",
        'new': """                LD      A, (CURX)
                NOP                     ; MUTATION: TEXT NOT INSERTED
                NOP
                NOP""",
        'filter': 'D1',
        'expect': ['D1/content'],
    },
    {
        'name': 'd2-enter',
        'why': 'EDNWLIN always splits at column 0',
        'file': 'EDIT.Z8A',
        'old': """SPLITL          LD      A, (CURX)""",
        'new': """SPLITL          XOR     A               ; MUTATION: ALWAYS SPLIT AT COL 0""",
        'filter': 'D2',
        'expect': ['D2/content'],
    },
    {
        'name': 'd3-backspace',
        'why': 'EDDELBK does not join line in WRAP_DEV mode',
        'file': 'EDIT.Z8A',
        'old': """                LD      A, (WRAPMODE)
                CP      WRAP_TXT
                JP      NZ, EDJNDEV     ; IN WRAP_DEV: DEV LINE JOIN / LINE DELETE""",
        'new': """                LD      A, (WRAPMODE)
                CP      WRAP_TXT
                RET     NZ              ; MUTATION: NO DEV LINE JOIN""",
        'filter': 'D3',
        'expect': ['D3/content'],
    },
    {
        'name': 'd4-delete',
        'why': 'EDDELCHR does not pull next line up at EOL in WRAP_DEV mode',
        'file': 'EDIT.Z8A',
        'old': """                LD      A, (WRAPMODE)
                CP      WRAP_TXT
                JP      NZ, EDDELDV     ; IN WRAP_DEV: DEV LINE JOIN / LINE DELETE BELOW""",
        'new': """                LD      A, (WRAPMODE)
                CP      WRAP_TXT
                RET     NZ              ; MUTATION: NO DEV LINE PULL""",
        'filter': 'D4',
        'expect': ['D4/content'],
    },
    {
        'name': 'd5-wordline-del',
        'why': 'ACTDWLFT word delete left is disabled',
        'file': 'ACTION.Z8A',
        'old': """ACTDWLFT        LD      A, (CURX)
                OR      A
                RET     Z""",
        'new': """ACTDWLFT        RET                     ; MUTATION: WORD DELETE NO-OP
                LD      A, (CURX)
                OR      A
                RET     Z""",
        'filter': 'D5',
        'expect': ['D5/content'],
    },
    {
        'name': 'd6-reflow',
        'why': 'REFLOW cascade reflow is disabled',
        'file': 'EDIT.Z8A',
        'old': """REFLOW          LD      (RFLINE), HL""",
        'new': """REFLOW          RET                     ; MUTATION: REFLOW NO-OP
                LD      (RFLINE), HL""",
        'filter': 'D6',
        'expect': ['D6/content'],
    },
    {
        'name': 'd7-tabs',
        'why': 'ACTTAB fails to insert spaces up to next tab stop',
        'file': 'ACTION.Z8A',
        'old': """ACTTAB          LD      A, (SELACT)""",
        'new': """ACTTAB          RET                     ; MUTATION: ACTTAB NO-OP
                LD      A, (SELACT)""",
        'filter': 'D7',
        'expect': ['D7/content', 'D7/curx'],
    },
    {
        'name': 'd8-accents',
        'why': 'CHKACNT fails to scan matrix for GRAPH accent combinations',
        'file': 'INPUT.Z8A',
        'old': """CHKACNT         ; --- STEP 1: CHECK DEAD KEY (ROW 2 BIT 5) OR KANA (ROW 6 BIT 4) ---""",
        'new': """CHKACNT         OR      A               ; MUTATION: CHKACNT NO-OP
                RET
                ; --- STEP 1: CHECK DEAD KEY (ROW 2 BIT 5) OR KANA (ROW 6 BIT 4) ---""",
        'filter': 'D8',
        'expect': ['D8/content'],
    },
    {
        'name': 'd8-double',
        'why': 'the BIOS GRAPH code and the matrix scan both deliver one press',
        'file': 'DISP.Z8A',
        'old': 'LD      (HL), A         ; CLAIM IT SO CHKACNT STAYS QUIET',
        'new': 'NOP                     ; MUTATION: NEVER CLAIM THE PRESS',
        'filter': 'D8',
        'expect': ['D8/content'],
    },
    {
        'name': 'd9-kana',
        'why': 'KANARST fails to extinguish physical KANA LED via PSG R15 bit 7',
        'file': 'INPUT.Z8A',
        'old': """                OR      #80             ; BIT 7 = 1 -> KANA LED OFF""",
        'new': """                AND     #7F             ; MUTATION: FORCE KANA LED ON (BIT 7 = 0)""",
        'filter': 'D9',
        'expect': ['D9/led-off'],
    },
    {
        'name': 'd10-markup',
        'why': 'ACTCYCMK markup mode cycling is disabled',
        'file': 'MARKUP.Z8A',
        'old': """ACTCYCMK        LD      A, (MKUPMD)""",
        'new': """ACTCYCMK        RET                     ; MUTATION: ACTCYCMK NO-OP
                LD      A, (MKUPMD)""",
        'filter': 'D10',
        'expect': ['D10/mode-cycle', 'D10/content'],
    },
    {
        'name': 'e1-cut',
        'why': 'ACTCUT copies to clipboard but skips deleting selection from document',
        'file': 'ACTION.Z8A',
        'old': """ACTCUT          CALL    ACTCOPY
                LD      HL, (CLIPLEN)
                LD      A, H
                OR      L
                RET     Z               ; NOTHING COPIED
                JP      ACTDLS          ; DELETE SELECTION FROM DOCUMENT""",
        'new': """ACTCUT          CALL    ACTCOPY
                LD      HL, (CLIPLEN)
                LD      A, H
                OR      L
                RET                     ; MUTATION: SKIP ACTDLS DELETION
                JP      ACTDLS          ; DELETE SELECTION FROM DOCUMENT""",
        'filter': 'E1',
        'expect': ['E1/totlines', 'E1/content'],
    },
    {
        'name': 'e2-paste',
        'why': 'PSTNL does not create new lines during multi-line paste',
        'file': 'ACTION.Z8A',
        'old': """PSTNL           LD      HL, (TOTLINES)
                PUSH    HL
                CALL    EDNWLIN""",
        'new': """PSTNL           LD      HL, (TOTLINES)
                PUSH    HL
                NOP                     ; MUTATION: NO NEWLINES ON PASTE
                NOP
                NOP""",
        'filter': 'E2',
        'expect': ['E2/totlines', 'E2/content'],
    },
    {
        'name': 'e3-sel-scroll',
        'why': 'ACTSLMD does not advance row on selection',
        'file': 'ACTION.Z8A',
        'old': """ACTSLMD         CALL    SELBEG
                LD      A, (CURY)""",
        'new': """ACTSLMD         RET                     ; MUTATION: ACTSLMD NO-OP
                LD      A, (CURY)""",
        'filter': 'E3',
        'expect': ['E3/docline-advanced', 'E3/viewport-scrolled'],
    },
    {
        'name': 'e4-selall-del',
        'why': 'ACTSELAL fails to set SELACT to 1',
        'file': 'ACTION.Z8A',
        'old': """                XOR     A
                LD      (SELANCX), A
                LD      A, 1
                LD      (SELACT), A""",
        'new': """                XOR     A
                LD      (SELANCX), A
                XOR     A               ; MUTATION: DO NOT ACTIVATE SELECTION
                LD      (SELACT), A""",
        'filter': 'E4',
        'expect': ['E4/sel-active'],
    },
    {
        'name': 'e5-replace',
        'why': '.DOPRINT does not call ACTDLS when typing over active selection',
        'file': 'DISP.Z8A',
        'old': """                LD      A, (SELACT)
                OR      A
                JR      Z, .NOSELDL""",
        'new': """                LD      A, (SELACT)
                OR      A
                JR      .NOSELDL        ; MUTATION: DO NOT DELETE SELECTION ON TYPING""",
        'filter': 'E5',
        'expect': ['E5/content'],
    },
    {
        'name': 'e6-sel-word-page',
        'why': 'ACTSLWRT does not advance to next word',
        'file': 'ACTION.Z8A',
        'old': """ACTSLWRT        CALL    SELBEG
                CALL    SELPRE
                CALL    ACTWRGT""",
        'new': """ACTSLWRT        CALL    SELBEG
                CALL    SELPRE
                NOP                     ; MUTATION: DO NOT ADVANCE TO NEXT WORD
                NOP
                NOP""",
        'filter': 'E6',
        'expect': ['E6/word-curx'],
    },
    {
        'name': 'e7-clip-limit',
        'why': 'ACTCOPY does not clamp copy bytes to CLIPMAX',
        'file': 'ACTION.Z8A',
        'old': """.CPYLINE        ; CHECK IF TOTAL BYTES EXCEEDS CLIPMAX
                LD      HL, (CPYCNT)
                LD      DE, CLIPMAX
                CALL    CMPHLDE
                JP      NC, .CPYEXIT    ; CLIPBOARD FULL""",
        'new': """.CPYLINE        ; CHECK IF TOTAL BYTES EXCEEDS CLIPMAX
                LD      HL, (CPYCNT)
                LD      DE, 4096        ; MUTATION: DO NOT CLAMP TO CLIPMAX
                CALL    CMPHLDE
                NOP
                NOP
                NOP""",
        'also': [('ACTION.Z8A',
                  """                ; CLAMP K TO REMAINING CLIPBOARD SPACE (CLIPMAX - CPYCNT)
                LD      HL, CLIPMAX
                LD      DE, (CPYCNT)
                OR      A
                SBC     HL, DE          ; HL = REMAINING""",
                  """                ; CLAMP K TO REMAINING CLIPBOARD SPACE (CLIPMAX - CPYCNT)
                LD      HL, 4096        ; MUTATION: EXPAND CAPACITY PAST BUFFER
                LD      DE, (CPYCNT)
                OR      A
                SBC     HL, DE          ; HL = REMAINING""")],
        'filter': 'E7',
        'expect': ['E7/cliplen'],
    },
    {
        'name': 'g12-screen-restore',
        'why': 'TERM does not call RSTPAL to restore standard VDP palette',
        'file': 'BDOS.Z8A',
        'old': """                ; 5. RESTORE VDP PALETTE (ALL 16 REGISTERS)
                CALL    RSTPAL""",
        'new': """                ; 5. RESTORE VDP PALETTE (ALL 16 REGISTERS)
                NOP                     ; MUTATION: DO NOT RESTORE PALETTE
                NOP
                NOP""",
        'filter': 'G12',
        'expect': ['G12/vdp-palette'],
    },
    {
        'name': 'h1-help',
        'why': 'the /H switch is missing from SWTTBL: S6ED /H boots instead '
               'of printing help and exiting in text mode',
        'file': 'PARAMS.Z8A',
        'old': """SWTTBL          DEFB    '?'
                DEFW    DOHLP
                DEFB    'H'""",
        'new': """SWTTBL          DEFB    '?'
                DEFW    DOHLP
                DEFB    'Z'             ; MUTATION: /H NOT IN TABLE""",
        'filter': 'H1',
        'expect': ['H1/help-printed', 'H1/no-screen6', 'H1/no-segments'],
    },
    {
        'name': 'h2-question',
        'why': 'the /? switch is missing from SWTTBL: S6ED /? boots instead '
               'of printing help and exiting in text mode',
        'file': 'PARAMS.Z8A',
        'old': """SWTTBL          DEFB    '?'
                DEFW    DOHLP""",
        'new': """SWTTBL          DEFB    'Z'             ; MUTATION: /? NOT IN TABLE
                DEFW    DOHLP""",
        'filter': 'H2',
        'expect': ['H2/help-printed', 'H2/no-screen6', 'H2/no-segments'],
    },
    {
        'name': 'h4-chkfile',
        'why': 'CHKFILE does not skip / switches, treating /X as the filename',
        'file': 'PARAMS.Z8A',
        'old': """                LD      A, (HL)
                CP      '/'
                JR      NZ, .FOUND      ; NOT A SWITCH → FILENAME""",
        'new': """                LD      A, (HL)
                CP      '/'
                JR      Z, .FOUND       ; MUTATION: ACCEPTS / SWITCH AS FILENAME""",
        'filter': 'H4',
        'expect': ['H4/file-loaded'],
    },
    {
        'name': 'h5-verbose',
        'why': 'the /V switch is missing from SWTTBL: S6ED /V boots quiet without verbose mode',
        'file': 'PARAMS.Z8A',
        'old': """                DEFB    'V'
                DEFW    DOVRB""",
        'new': """                DEFB    'Z'             ; MUTATION: /V NOT IN TABLE
                DEFW    DOVRB""",
        'filter': 'H5',
        'expect': ['H5/text-printed', 'H5/verbose-set'],
    },
    {
        'name': 'i1-unix-save',
        'why': 'FILESAVE always writes CRLF ignoring SAVEEOL = 1',
        'file': 'FILEIO.Z8A',
        'old': """                LD      A, (SAVEEOL)
                OR      A
                JR      Z, .WREOL2""",
        'new': """                JR      .WREOL2         ; MUTATION: ALWAYS WRITE CRLF
                LD      A, (SAVEEOL)
                OR      A""",
        'filter': 'I1',
        'expect': ['I1/no-cr', 'I1/content'],
    },
    {
        'name': 'i2-autolod-lf',
        'why': 'FILELOAD does not auto-detect standalone LF as UNIX EOL',
        'file': 'FILEIO.Z8A',
        'old': """                LD      A, 1
                LD      (SAVEEOL), A    ; DETECTED UNIX (LF)""",
        'new': """                XOR     A               ; MUTATION: DO NOT DETECT UNIX
                LD      (SAVEEOL), A    ; DETECTED UNIX (LF)""",
        'filter': 'I1',
        'expect': ['I1/saveeol', 'I1/content'],
    },
    {
        'name': 'f1-homeseg',
        'why': 'FCALL leaves HOMESEG non-zero when returning to core',
        'file': 'XSEG.Z8A',
        'old': """                LD      HL, HOMESEG
                LD      (HL), B""",
        'new': """                LD      HL, HOMESEG
                LD      (HL), 1         ; MUTATION: LEAVE HOMESEG DIRTY""",
        'filter': 'G13',
        'expect': ['G13/homeseg-idle'],
    },
    {
        'name': 'f1-copy',
        'why': 'F1COPY truncates blob copy so feature code is not fully present',
        'file': 'XSEG.Z8A',
        'old': """                LD      BC, FTRBLEN
                LDIR""",
        'new': """                LD      BC, 10          ; MUTATION: TRUNCATE FEATURE BLOB COPY
                LDIR""",
        'filter': 'G13',
        'expect': ['G13/cfg-applied'],
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
