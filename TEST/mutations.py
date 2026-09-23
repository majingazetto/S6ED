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
        'name': 'g8-alntbl',
        'why': 'PARSALN dispatches on the first letter of the value again, so '
               'OFF and ON collide on O and AUTOALIGN=OFF turns auto-align ON',
        'file': 'CFG.Z8A',
        'old': """                CP      'O'
                RET     NZ              ; UNKNOWN VALUE: KEEP THE DEFAULT
                INC     HL
                LD      A, (HL)
                CALL    UPCASE
                CP      'N'
                JR      Z, .ALNON
                CP      'F'
                RET     NZ
                LD      A, ALGN_OFF
                JR      .ALNSET""",
        'new': """                CP      'O'                 ; MUTATION: ONE LETTER ONLY
                RET     NZ
                JR      .ALNON""",
        'filter': 'G8',
        'expect': ['G8/compact/autoalign'],
    },
    {
        'name': 'd11-splitl',
        'why': 'SPLITL splits at the raw CURX, so a space at the right margin '
               'of a full line carries its last character down instead of '
               'breaking after it',
        'file': 'EDIT.Z8A',
        'old': 'SPLITL          CALL    EFFCURX',
        'new': 'SPLITL          LD      A, (CURX)   ; MUTATION: RAW COLUMN',
        'filter': 'D11',
        'expect': ['D11/space/content'],
    },
    {
        'name': 'd11-pushwrap',
        'why': 'EDPSHWR measures the cursor with the raw CURX, so the '
               'character that forces the wrap lands one place too early '
               'inside the word that moved down',
        'file': 'EDIT.Z8A',
        'old': """                CALL    EFFCURX
                CP      B""",
        'new': """                LD      A, (CURX)       ; MUTATION: RAW COLUMN
                CP      B""",
        'filter': 'D11',
        'expect': ['D11/push/content'],
    },
    {
        'name': 's2-pushwrap',
        'why': 'the same raw-column push-wrap seen on the 64-column record, '
               'with the screen checked as well as the document',
        'target': 'S2ED',
        'file': 'EDIT.Z8A',
        'old': """                CALL    EFFCURX
                CP      B""",
        'new': """                LD      A, (CURX)       ; MUTATION: RAW COLUMN
                CP      B""",
        'filter': 'S2-9',
        'expect': ['S2-9/push/content', 'S2-9/push/screen'],
    },
    # --- SUITE S2 (MSX1 / SCREEN 2) -----------------------------------
    #
    # These run on the S2 target: a different binary, a different gate and a
    # different machine, from the same CORE sources.  `target` says which.
    {
        'name': 's2-render-brow',
        'why': 'RENDEROW calls COMROW with B destroyed, so every text row '
               'composes on top of row 0',
        'target': 'S2ED',
        'file': 'RENDER.Z8A',
        'old': """                ; RESTORE B = SCREEN ROW. LINEREAD ENDS IN AN LDIR AND
                ; SCANMKUP CLOBBERS BC, SO COMROW WOULD OTHERWISE COMPOSE
                ; EVERY ROW ON TOP OF ROW 0.
                POP     BC
                PUSH    BC""",
        'new': """                ; MUTATION: B IS NOT RESTORED BEFORE COMROW""",
        'filter': 'S2-1',
        'expect': ['S2-1/rows'],
    },
    {
        'name': 's2-attr-clear',
        'why': 'FILELOAD clears the attribute half from the S6 offset, so the '
               'first 16 attribute bytes of every S2 record stay dirty and '
               'render as bold (the yellow bands)',
        'target': 'S2ED',
        'file': 'FILEIO.Z8A',
        'old': """                LD      DE, 1 + TEXTCOLS
                ADD     HL, DE          ; HL = ATTR START""",
        'new': """                LD      DE, 81          ; MUTATION: THE S6 LITERAL
                ADD     HL, DE          ; HL = ATTR START""",
        'filter': 'S2-2',
        'expect': ['S2-2/text-colour'],
    },
    {
        'name': 's2-cursor-cell',
        'why': 'the inversion covers the WHOLE cell instead of one text '
               'column -- a two-character cursor, and consecutive selection '
               'deltas that cancel each other out',
        'target': 'S2ED',
        'file': 'RENDER.Z8A',
        'old': """                LD      E, #F0
                JR      Z, .PXHAVE
                LD      E, #0F""",
        'new': """                LD      E, #FF          ; MUTATION: WHOLE CELL
                JR      Z, .PXHAVE
                LD      E, #FF""",
        'filter': 'S2-3',
        'expect': ['S2-3/one-column'],
    },
    {
        'name': 's2-sel-cell',
        'why': 'the same whole-cell inversion seen through the selection: '
               'SELDIFF extends one column at a time, so two deltas land on '
               'one cell and their XORs cancel, leaving residue behind',
        'target': 'S2ED',
        'file': 'RENDER.Z8A',
        'old': """                LD      E, #F0
                JR      Z, .PXHAVE
                LD      E, #0F""",
        'new': """                LD      E, #FF          ; MUTATION: WHOLE CELL
                JR      Z, .PXHAVE
                LD      E, #FF""",
        'filter': 'S2-4',
        'expect': ['S2-4/range'],
    },
    {
        'name': 's2-band-rows',
        'why': 'the cursor is bounded by SCRROWS (the physical screen) where '
               'it means ROWSVIS (the text band), so it walks two rows below '
               'the painted band before the viewport scrolls',
        'target': 'S2ED',
        'file': 'EDIT.Z8A',
        'old': """                LD      A, (CURY)
                CP      ROWSVIS - 1
                JR      Z, .SCRLDN""",
        'new': """                LD      A, (CURY)
                CP      SCRROWS - 1     ; MUTATION: PHYSICAL, NOT VISIBLE
                JR      Z, .SCRLDN""",
        'filter': 'S2-5',
        'expect': ['S2-5/cury'],
    },
    {
        'name': 's2-delbk-79',
        'why': 'EDDELBK walks its shift loop to a literal 79, dragging an '
               'attribute byte into the last text column -- after which '
               'EDINSCHR sees a full record and refuses every keystroke',
        'target': 'S2ED',
        'file': 'EDIT.Z8A',
        'old': """.SHIFTLP        LD      A, B
                CP      TEXTCOLS - 1""",
        'new': """.SHIFTLP        LD      A, B
                CP      79              ; MUTATION: THE S6 LITERAL""",
        'also': [('EDIT.Z8A',
                  """.BLANKLS        LD      HL, WORKBUF + TEXTCOLS
                LD      (HL), ' '       ; BLANK LAST TEXT COL
                LD      HL, WORKBUF + TEXTCOLS + TEXTCOLS""",
                  """.BLANKLS        LD      HL, WORKBUF + 80
                LD      (HL), ' '       ; BLANK LAST TEXT COL
                LD      HL, WORKBUF + 80 + TEXTCOLS""")],
        'filter': 'S2-6',
        'expect': ['S2-6/bs-dev/line'],
    },
    {
        'name': 's2-enterbot-23',
        'why': 'EDNWLIN repaints the shortened head at a literal row 23, '
               'which on S2 is the status bar',
        'target': 'S2ED',
        'file': 'EDIT.Z8A',
        'old': """                LD      B, ROWSVIS - 1
                CALL    RENDEROW""",
        'new': """                LD      B, 23           ; MUTATION: THE S6 LITERAL
                CALL    RENDEROW""",
        'filter': 'S2-7',
        'expect': ['S2-7/head-repainted'],
    },
    {
        'name': 's2-scroll-nodump',
        'why': 'SCRLUPN moves the shadow bands and never pushes the pattern '
               'band to VRAM -- the round-1 defect: the shadows are right and '
               'the screen is a scroll behind',
        'target': 'S2ED',
        'file': 'SCROLL.Z8A',
        'old': """                LD      HL, PATSHAD + ROWLEN
                LD      DE, PGBASE + ROWLEN
                LD      C, 0            ; BC = K * ROWLEN
                CALL    VDPDUMP""",
        'new': """                LD      HL, PATSHAD + ROWLEN
                LD      DE, PGBASE + ROWLEN
                LD      C, 0            ; BC = K * ROWLEN
                                        ; MUTATION: BAND NEVER PUSHED TO VRAM""",
        'filter': 'S2-5',
        'expect': ['S2-5/scrolled-rows'],
    },
    {
        'name': 's2-theme-default',
        'why': 'S2THMBR carries the DARK data, so THEME=AMBER loads the '
               'default theme: the vars say white-on-black and the VRAM '
               'colour table agrees, while the config claims amber',
        'target': 'S2ED',
        'file': 'VDP.Z8A',
        'old': "S2THMBR         DEFB    #A1, #A6, #B1, #71, #31, #E1, 1, #A6  ; AMBER",
        'new': "S2THMBR         DEFB    #F1, #F4, #B1, #71, #31, #E1, 1, #F4  ; MUTATION: DARK DATA",
        'filter': 'S2-10',
        'expect': ['S2-10/amber/vars', 'S2-10/amber/text',
                   'S2-10/amber/menu', 'S2-10/amber/status'],
    },
    {
        'name': 's2-rendiff-hit',
        'why': 'the differential painter takes its cache-hit path and repaints '
               'nothing.  MEASURED: this passes render-pure -- the stale row '
               'survives a full REDRAW, so comparing the screen against the '
               'screen sees two identical wrong pictures.  Only the '
               'comparison against the table computed from the font and the '
               'document catches it, which is the whole argument for this '
               'suite.',
        'target': 'S2ED',
        'file': 'RENDER.Z8A',
        'old': """                ; CACHE HIT: UPDATE ROW AND COMMITTED CACHE
                POP     BC
                CALL    RENDEROW""",
        'new': """                ; CACHE HIT: UPDATE ROW AND COMMITTED CACHE
                POP     BC
                                        ; MUTATION: CACHE HIT REPAINTS NOTHING""",
        'filter': 'S2-8',
        'expect': ['S2-8/matches-document'],
    },
    {
        # The TPA chain (VARS.Z8A) exists so no buffer ever names an address.
        # One literal here and the allocation stops following whatever the
        # target actually declared above it.
        'name': 't0-tpa-fixed',
        'why': 'the S2 window save buffer is pinned to a literal address '
               'instead of chaining off the top of the undo ring',
        'file': 'VARS.Z8A',
        'old': 'WSVBUF          EQU     UNDOTOP',
        'new': 'WSVBUF          EQU     #6D5B',
        'filter': 'T0',
        'expect_static': ['tpa-chain'],
    },
    {
        'name': 's2-wsvbuf-undo',
        'why': 'the window save buffer is allocated on top of the undo ring: '
               'the dialog opens and restores perfectly, and eats the undo '
               'transaction while it is open',
        'target': 'S2ED',
        'file': 'VARS.Z8A',
        'old': 'WSVBUF          EQU     UNDOTOP',
        'new': 'WSVBUF          EQU     UNDOBAS',
        'filter': 'S2-12',
        'expect': ['S2-12/content'],
    },
    {
        # The chrome split of 2026-09-22.  Before it the menu bar, the status
        # bar, the dialog body and the dialog button all came out of two role
        # bytes, so "theming the status bar" was not a thing you could do.
        'name': 's2-role-stat',
        'why': 'DRWSTAT paints the status bar in the document text role, so '
               'the bar stops being chrome and no theme can move it',
        'target': 'S2ED',
        'file': 'UI.Z8A',
        'old': """                ; STATUS BAR HAS ITS OWN ROLE, DISTINCT FROM THE MENU BAR
                LD      A, (VCOLSTAT)""",
        'new': """                ; MUTATION: THE BAR IS NOT CHROME ANY MORE
                LD      A, (VCOLTXT)""",
        'filter': 'S2-10',
        'expect': ['S2-10/amber/status'],
    },
    {
        'name': 's2-role-win',
        'why': 'WBOX fills the dialog body with the document text role, so a '
               'dialog is a patch of document and cannot be themed apart',
        'target': 'S2ED',
        'file': 'WINDOW.Z8A',
        'old': """                LD      A, (VCOLWIN)
                JR      NZ, .CFILS""",
        'new': """                LD      A, (VCOLTXT)    ; MUTATION: BODY = DOCUMENT
                JR      NZ, .CFILS""",
        'filter': 'S2-11',
        'expect': ['S2-11/window-colour'],
    },
    {
        'name': 's2-role-wtit',
        'why': 'WBOX paints the top row as body, so there is no title bar '
               'band and the accent never reaches the screen',
        'target': 'S2ED',
        'file': 'WINDOW.Z8A',
        'old': """                LD      A, (WINR)
                CP      B               ; B IS STILL THE ROW HERE
                LD      A, (VCOLWIN)
                JR      NZ, .CFILS
                LD      A, (VCOLHI)     ; TOP ROW: TITLE BAR
.CFILS          LD      C, A            ; HOLD IT WHILE B TAKES WINNC""",
        'new': """                LD      A, (VCOLWIN)    ; MUTATION: NO TITLE BAR
.CFILS          LD      C, A            ; HOLD IT WHILE B TAKES WINNC""",
        'filter': 'S2-11',
        'expect': ['S2-11/window-colour'],
    },
    {
        'name': 's2-role-btn',
        'why': 'the OK button loses its focus role and wears the plain '
               'accent, so nothing on the dialog shows where the focus is',
        'target': 'S2ED',
        'file': 'WINDOW.Z8A',
        'old': '                LD      A, (VCOLBSEL)   ; THE FOCUSED BUTTON: INVERSE ACCENT',
        'new': '                LD      A, (VCOLHI)     ; MUTATION: NO FOCUS',
        'filter': 'S2-11',
        'expect': ['S2-11/window-colour'],
    },
    {
        # S6ED closes its title band with a COL_HI separator.  On S2 the line
        # has to go in AFTER the title, because WINPUTC overwrites all eight
        # scanlines of a cell -- drawn first it survives everywhere except
        # under the title, which is the half anyone would notice.
        'name': 's2-wbox-sep',
        'why': 'the title bar has no separator closing it, so the dialog '
               'header runs into the body',
        'target': 'S2ED',
        'file': 'WINDOW.Z8A',
        'old': """                LD      A, (WINNC)
                LD      B, A
                LD      A, #FF
.SEPLP          LD      (HL), A""",
        'new': """                LD      A, (WINNC)
                LD      B, A
                LD      A, #00          ; MUTATION: NO SEPARATOR
.SEPLP          LD      (HL), A""",
        'filter': 'S2-11',
        'expect': ['S2-11/title-separator'],
    },
    {
        # PARSTHM dispatches on the FIRST LETTER, which is how AUTOALIGN=OFF
        # once turned auto-align on.  MSX is index 12: with the old A-H table
        # the value is rejected and the editor silently stays on DARK.
        'name': 's2-theme-idx',
        'why': 'the theme index table stops at H again, so THEME=MSX is '
               'rejected in silence and the default theme stays',
        'target': 'S2ED',
        'file': 'CFG.Z8A',
        'old': '                CP      #0D             ; 13 ENTRIES (A-M): MSX IS INDEX 12',
        'new': '                CP      #08             ; MUTATION: A-H ONLY',
        'filter': 'S2-10',
        'expect': ['S2-10/msx/vars'],
    },
    {
        # The last hardcoded colour in the target.  A shadow cell keeps the
        # document's pattern and flattens its colour, so black-on-black is a
        # shadow only where the document is not black -- which was true of
        # exactly one of the four themes.
        'name': 's2-role-shdw',
        'why': 'the drop shadow goes back to a hardcoded black, which is '
               'invisible on every theme whose document background is black',
        'target': 'S2ED',
        'file': 'WINDOW.Z8A',
        'old': """.RSNC           LD      DE, COLMAP
                ADD     HL, DE
                LD      A, (VCOLSHDW)""",
        'new': """.RSNC           LD      DE, COLMAP
                ADD     HL, DE
                LD      A, #11          ; MUTATION: HARDCODED BLACK SHADOW""",
        'filter': 'S2-11',
        'expect': ['S2-11/shadow'],
    },
    {
        'name': 't0-dsk-s6only',
        'why': 'the S6ED disk stops carrying S2ED, so the one image that runs '
               'both editors on an MSX2 quietly goes out with one',
        'file': 'Makefile',
        'old': '\t\t\t  $(OUTPUT_S2) $(DATFILE_S2) $(FNTFILE_S2) $(CFGFILE_S2) TEST_S2.TXT',
        'new': '\t\t\t  $(DATFILE_S2) $(FNTFILE_S2) $(CFGFILE_S2) TEST_S2.TXT',
        'filter': 'T0',
        'expect_static': ['build-symmetry'],
    },
    {
        # The asymmetry the user found on 2026-09-22: clean removed both
        # editors' artefacts while build assembled one, so `make clean build`
        # left the tree half built and the S2 harness died on a missing .sym.
        'name': 't0-build-s6only',
        'why': 'make build assembles S6ED alone again while clean removes '
               'both, so clean+build leaves the tree half built',
        'file': 'Makefile',
        'old': 'build: build-s6 build-s2',
        'new': 'build: build-s6',
        'filter': 'T0',
        'expect_static': ['build-symmetry'],
    },
    {
        # The defect W2 exists to remove: on S2ED, ESC went straight to TERM.
        'name': 's2-quit-direct',
        'why': 'ACTQUIT quits without asking on S2ED, so ESC throws the '
               'document away -- the stub that stood there until W2',
        'target': 'S2ED',
        'file': 'ACTION.Z8A',
        # Anchored below the FTR-BUDGET comment on purpose: that line carries
        # measured byte counts and is rewritten every time the container moves.
        'old': """                LD      A, (FTRSEG)
                LD      HL, DOQIT""",
        'new': """                JP      TERM            ; MUTATION: QUIT WITHOUT ASKING
                LD      HL, DOQIT""",
        'filter': 'S2-15',
        # ESC exits on the spot: either the displayed check goes red, or the
        # case dies waiting for a WINPOLL that never comes.
        'expect_any': ['S2-15/clean/displayed', 'S2-15-quit'],
    },
    {
        'name': 's2-quit-defsel',
        'why': 'the Quit dialog opens with YES selected, so a reflex ENTER '
               'discards the document',
        'target': 'S2ED',
        'file': 'WINDOW.Z8A',
        'old': """                ; DEFAULT: NO SELECTED, RESULT CANCELLED
                LD      A, 1
                LD      (WINSEL), A""",
        'new': """                ; DEFAULT: NO SELECTED, RESULT CANCELLED
                XOR     A               ; MUTATION: YES SELECTED BY DEFAULT
                LD      (WINSEL), A""",
        'filter': 'S2-15',
        'expect': ['S2-15/clean/default-no'],
    },
    {
        'name': 's2-quit-nav',
        'why': 'LEFT and RIGHT are swapped, so the arrow keys move the focus '
               'the wrong way',
        'target': 'S2ED',
        'file': 'WINDOW.Z8A',
        'old': """                CP      CLEFT
                JR      Z, .TOYES
                CP      CRIGHT
                JR      Z, .TONO""",
        'new': """                CP      CLEFT
                JR      Z, .TONO        ; MUTATION: NAVIGATION REVERSED
                CP      CRIGHT
                JR      Z, .TOYES""",
        'filter': 'S2-15',
        'expect': ['S2-15/clean/nav-left'],
    },
    {
        'name': 's2-quit-warn',
        'why': 'the unsaved-changes warning is shown on a clean buffer and '
               'hidden on a dirty one -- the test that matters inverted',
        'target': 'S2ED',
        'file': 'WINDOW.Z8A',
        'old': """                LD      A, (MODIFIED)
                OR      A
                JR      Z, .NOWRN""",
        'new': """                LD      A, (MODIFIED)
                OR      A
                JR      NZ, .NOWRN      ; MUTATION: WARNING INVERTED""",
        'filter': 'S2-15',
        'expect': ['S2-15/clean/warning', 'S2-15/dirty/warning'],
    },
    {
        'name': 's2-quit-yes',
        'why': 'the Y accelerator does not set WINRES, so the editor refuses '
               'to quit however the dialog is answered',
        'target': 'S2ED',
        'file': 'WINDOW.Z8A',
        'old': """.YES            LD      A, 1
                LD      (WINRES), A""",
        'new': """.YES            XOR     A               ; MUTATION: Y CANCELS
                LD      (WINRES), A""",
        'filter': 'S2-15',
        # The exit breakpoint never fires, so either the check sees no exit
        # snapshot or the case dies waiting for one.
        'expect_any': ['S2-15/clean/quit-y', 'S2-15-quit'],
    },
    {
        # The stub W4 exists to remove: MNUENT was the last IFDEF S2ED in the
        # menu and dialog path.
        'name': 's2-menu-stub',
        'why': 'MNUENT returns without opening anything on S2ED, so F1..F5 '
               'and SELECT do nothing -- the stub that stood there until W4',
        'target': 'S2ED',
        'file': 'ACTION.Z8A',
        'old': """                LD      A, (FTRSEG)
                LD      HL, DOMNU
                CALL    FCALL""",
        'new': """                RET                     ; MUTATION: MENUS DISABLED
                LD      HL, DOMNU
                CALL    FCALL""",
        'filter': 'S2-16',
        # SELECT opens nothing, so the timeline's later ESC opens the Quit
        # dialog instead and the WINPOLL gate samples THAT: WINACTV is still
        # 1 and MNUID still 0.  It is the geometry and the accelerator that
        # tell the two apart, which is why S2-16/open names both.
        'expect': ['S2-16/open', 'S2-16/accel-new'],
    },
    {
        'name': 's2-menu-defsel',
        'why': 'a menu opens with the second item selected, so a reflex '
               'ENTER on File runs Open instead of New',
        'target': 'S2ED',
        'file': 'MENU.Z8A',
        'old': """.INITOK         XOR     A
                LD      (MNUSEL), A     ; DEFAULT SELECTION = 0""",
        'new': """.INITOK         LD      A, 1            ; MUTATION: OPENS ON ITEM 1
                LD      (MNUSEL), A""",
        'filter': 'S2-16',
        'expect': ['S2-16/open', 'S2-16/open/colour'],
    },
    {
        'name': 's2-menu-skipsep',
        'why': 'DOWN stops on the separator, so a rule can be selected and '
               'ENTER dispatches an item index that means nothing',
        'target': 'S2ED',
        'file': 'MENU.Z8A',
        'old': """.DWNCHK         CALL    MNUCHKS
                JR      NZ, .MOVE
                INC     A               ; SKIP SEPARATOR""",
        'new': """.DWNCHK         CALL    MNUCHKS
                JR      .MOVE           ; MUTATION: SEPARATOR SELECTABLE
                INC     A""",
        'filter': 'S2-16',
        'expect': ['S2-16/skip-separator'],
    },
    {
        'name': 's2-menu-title',
        'why': 'the title in row 0 is never highlighted, so nothing on the '
               'bar says which menu is open',
        'target': 'S2ED',
        'file': 'MENU.Z8A',
        'old': """MNUTITL         LD      A, (MNUID)
                ADD     A, A            ; TWO BYTES PER SPAN""",
        'new': """MNUTITL         RET                     ; MUTATION: NO HIGHLIGHT
                ADD     A, A            ; TWO BYTES PER SPAN""",
        'filter': 'S2-16',
        'expect': ['S2-16/title-highlight'],
    },
    {
        'name': 's2-menu-nav-wrap',
        'why': 'RIGHT stops at Help instead of wrapping round to File, so '
               'the bar is a dead end in one direction',
        'target': 'S2ED',
        'file': 'MENU.Z8A',
        'old': """                JR      C, .RGHTOK
                XOR     A               ; WRAP 4 -> 0""",
        'new': """                JR      C, .RGHTOK
                DEC     A               ; MUTATION: RIGHT DOES NOT WRAP""",
        'filter': 'S2-17',
        'expect': ['S2-17/walk'],
    },
    {
        'name': 's2-menu-enter',
        'why': 'RETURN cancels instead of accepting, so the only way to run a '
               'menu item is its accelerator',
        'target': 'S2ED',
        'file': 'MENU.Z8A',
        'old': """                CP      CR
                JP      Z, .ACCEPT""",
        'new': """                CP      CR
                JP      Z, .CANCEL      ; MUTATION: RETURN CANCELS""",
        'filter': 'S2-17',
        'expect': ['S2-17/action'],
    },
    {
        'name': 's2-menu-swtitl',
        'why': 'switching menus never un-highlights the one it came from, so '
               'the inverted titles pile up along the bar',
        'target': 'S2ED',
        'file': 'MENU.Z8A',
        'old': """                CALL    WINCLOS
                CALL    MNUTITL         ; UN-HIGHLIGHT THE OLD TITLE
                POP     BC""",
        'new': """                CALL    WINCLOS
                POP     BC""",
        'filter': 'S2-17',
        'expect': ['S2-17/r1/title'],
    },
    {
        # The defect this phase removed on the way past: five of the six Edit
        # menu items called the action ID and not the routine.
        'name': 'menu-edit-id',
        'why': 'Edit > Select All calls ACSELAL, the action ID (EQU 42), so '
               'the menu jumps to #002A in the DOS zero page instead of the '
               'routine -- which is what shipped, unnoticed, because no case '
               'had ever pressed an Edit menu item',
        'file': 'ACTION.Z8A',
        'old': """.EALL           CALL    ACTSELAL""",
        'new': """.EALL           CALL    ACSELAL         ; MUTATION: THE ID, NOT THE ROUTINE""",
        'filter': 'H23',
        # Calling into page 0 is undefined: sometimes the selection simply
        # never happens, sometimes the session does not survive it.
        'expect_any': ['H23/edit-action', 'H23-menu-nav'],
    },
    {
        'name': 'goto-nodispatch',
        'why': 'Ctrl+G and Edit > Go to Line reach nothing, the state the '
               'editor was in before this phase',
        'file': 'ACTION.Z8A',
        'old': """                DEFW    ACTGOTO         ; 59 (GO TO LINE)""",
        'new': """                DEFW    ACTNONE         ; MUTATION: GO TO LINE UNBOUND""",
        'filter': 'H24',
        'expect': ['H24/open', 'H24/centred'],
    },
    {
        # The round-3 defect class, and the reason the suite runs two gates:
        # on S6ED this mutation changes nothing at all.
        'name': 'goto-scrrows',
        'why': 'the viewport centres on SCRROWS / 2 instead of ROWSVIS / 2, '
               'which is identical on S6ED and two rows wrong on S2ED',
        'target': 'S2ED',
        'file': 'ACTION.Z8A',
        'old': """.CENTRE         ; TOPLINE = DOCLINE - ROWSVIS / 2, CLAMPED
                LD      DE, ROWSVIS / 2""",
        'new': """.CENTRE         ; TOPLINE = DOCLINE - ROWSVIS / 2, CLAMPED
                LD      DE, SCRROWS / 2 ; MUTATION: THE SCREEN, NOT THE BAND""",
        'filter': 'S2-18',
        'expect': ['S2-18/centred', 'S2-18/space'],
    },
    {
        'name': 'goto-visible',
        'why': 'a line already on screen scrolls the viewport anyway, so '
               'every jump is a jolt',
        'file': 'ACTION.Z8A',
        'old': """                JP      C, SETCURY      ; VISIBLE: DO NOT MOVE THE VIEWPORT""",
        'new': """                JP      C, .CENTRE      ; MUTATION: ALWAYS RECENTRE""",
        'filter': 'H24',
        'expect': ['H24/nearby'],
    },
    {
        'name': 'goto-bs',
        'why': 'Backspace leaves the digit in the field, so a correction '
               'goes to the line the user was trying not to go to',
        'file': 'WINDOW.Z8A',
        'old': """                DEC     A
                LD      (INPLEN), A
                LD      E, A""",
        'new': """                NOP                     ; MUTATION: BACKSPACE REMOVES NOTHING
                LD      (INPLEN), A
                LD      E, A""",
        'filter': 'H24',
        'expect': ['H24/backspace'],
    },
    {
        'name': 'goto-esc',
        'why': 'ESC accepts instead of cancelling, so the way out of the '
               'dialog is the way into a jump nobody asked for',
        'file': 'WINDOW.Z8A',
        'old': """                CP      ESC
                JP      Z, .CANCEL
                CP      CR
                JP      Z, .ACCEPT""",
        'new': """                CP      ESC
                JP      Z, .ACCEPT      ; MUTATION: ESC ACCEPTS
                CP      CR
                JP      Z, .ACCEPT""",
        'filter': 'H24',
        'expect': ['H24/cancel'],
    },
    {
        'name': 'goto-empty',
        'why': 'ENTER on an empty field is taken as line 0, so a reflex ENTER '
               'throws the cursor to the top of the document',
        'file': 'WINDOW.Z8A',
        'old': """                LD      A, (INPLEN)
                OR      A
                JR      Z, .CANCEL      ; AN EMPTY FIELD CANCELS""",
        'new': """                LD      A, (INPLEN)
                OR      A
                JR      C, .CANCEL      ; MUTATION: NEVER TAKEN AFTER OR A""",
        'filter': 'H24',
        'expect': ['H24/empty'],
    },
    {
        'name': 'goto-space',
        'why': 'SPACE accepts while the field has the focus, which is right '
               'for digits and wrong the day a class accepts a space -- the '
               'reason the focus has three positions and not two',
        'file': 'WINDOW.Z8A',
        'old': """.SPACE          LD      A, (WINSEL)
                OR      A
                JP      Z, .KEYLP       ; THE FIELD HAS IT: SPACE IS NOT A KEY""",
        'new': """.SPACE          LD      A, (WINSEL)
                OR      A               ; MUTATION: SPACE ALWAYS ACCEPTS""",
        'filter': 'H24',
        'expect': ['H24/space'],
    },
    {
        'name': 's2-mark-role',
        'why': 'COMCELL never tests ATRMARK, so the ** delimiters fall back '
               'to the document colour and VCOLMARK goes back to being a '
               'theme byte nobody reads',
        'target': 'S2ED',
        'file': 'RENDER.Z8A',
        'old': """.NOTUN          BIT     4, C            ; ATRMARK ?
                JR      Z, .SETCOL
                LD      A, (VCOLMARK)""",
        'new': """.NOTUN          BIT     4, C            ; ATRMARK ?
                JR      .SETCOL         ; MUTATION: DELIMITERS UNMARKED
                LD      A, (VCOLMARK)""",
        'filter': 'S2-14',
        'expect': ['S2-14/line0', 'S2-14/line1'],
    },
    {
        # The ordering decision, not the wiring.  A cell is two characters,
        # so a delimiter starting on an odd column shares its cell with
        # content; testing ATRMARK FIRST paints that content character as a
        # delimiter and it loses its own role.  Line 0 is aligned and cannot
        # see the difference -- only line 1 can, which is why it exists.
        'name': 's2-mark-prio',
        'why': 'ATRMARK is tested before ATRBOLD, so a bold letter sharing a '
               'cell with a delimiter is painted as a delimiter',
        'target': 'S2ED',
        'file': 'RENDER.Z8A',
        'old': """                LD      A, (VCOLTXT)    ; DEFAULT COLOR
                BIT     0, C            ; ATRBOLD ?
                JR      Z, .NOTBD""",
        'new': """                LD      A, (VCOLTXT)    ; DEFAULT COLOR
                BIT     4, C            ; MUTATION: DELIMITER WINS
                JR      Z, .MUTBD
                LD      A, (VCOLMARK)
                JR      .SETCOL
.MUTBD          BIT     0, C            ; ATRBOLD ?
                JR      Z, .NOTBD""",
        'filter': 'S2-14',
        'expect': ['S2-14/line1'],
    },
    {
        # What S2-14/line1 exists for.  A cell is TWO characters and COMCELL
        # ORs both attributes, so a span that starts on an odd column drags
        # its delimiter into the span's colour.  Reading only the left
        # attribute leaves the aligned line looking perfect and silently
        # halves the span on every odd one.
        'name': 's2-comcell-rattr',
        'why': 'COMCELL takes the cell colour from the left character alone, '
               'so a markup span starting on an odd column loses its first '
               'cell -- invisible on any aligned example',
        'target': 'S2ED',
        'file': 'RENDER.Z8A',
        'old': """                LD      A, D
                OR      E               ; A = LATTR | RATTR""",
        'new': """                LD      A, D
                                        ; MUTATION: RIGHT ATTRIBUTE IGNORED""",
        'filter': 'S2-14',
        'expect': ['S2-14/line1'],
    },
    {
        'name': 's2-shadow-off',
        'why': 'WSHDW ignores SHADOW=OFF and recolours the margin anyway, so '
               'the key cannot turn the shadow off',
        'target': 'S2ED',
        'file': 'WINDOW.Z8A',
        'old': """WSHDW           LD      A, (SHDWOFF)
                OR      A
                RET     NZ              ; SHADOW=OFF: LEAVE THE MARGIN ALONE""",
        'new': """WSHDW           LD      A, (SHDWOFF)
                OR      A               ; MUTATION: SHADOW=OFF IGNORED""",
        'filter': 'S2-13',
        'expect': ['S2-13/off/margin'],
    },
    {
        'name': 's2-shadow-hex',
        'why': 'PARSSHD parses the colour digit and never stores it, so '
               'SHADOW=<hex> is accepted in silence and discarded -- the '
               'shape the COLOR_* keys had on S2ED before they were removed',
        'target': 'S2ED',
        'file': 'CFG.Z8A',
        'old': """                OR      C               ; FLATTEN: N << 4 | N
                LD      (VCOLSHDW), A""",
        'new': """                OR      C               ; FLATTEN: N << 4 | N
                                        ; MUTATION: VALUE NEVER STORED""",
        'filter': 'S2-13',
        'expect': ['S2-13/colour/margin'],
    },
    {
        'name': 's2-wbox-rframe',
        'why': 'WBOX reaches the right border with a (WINNC-1)*8 offset from '
               'the cell past the left border, landing on the shadow column: '
               'no right border anywhere, and a stray #03 column in document '
               'colour one cell past the window',
        'target': 'S2ED',
        'file': 'WINDOW.Z8A',
        'old': """                LD      A, (WINNC)
                SUB     2
                ADD     A, A
                ADD     A, A
                ADD     A, A
                LD      E, A
                LD      D, 0
                ADD     HL, DE          ; RIGHT CELL: (WINNC-2)*8 PAST WINC+1""",
        'new': """                LD      A, (WINNC)
                DEC     A               ; MUTATION: ONE CELL TOO FAR
                ADD     A, A
                ADD     A, A
                ADD     A, A
                LD      E, A
                LD      D, 0
                ADD     HL, DE          ; RIGHT CELL: (WINNC-2)*8 PAST WINC+1""",
        'filter': 'S2-11',
        'expect': ['S2-11/side-borders'],
    },
    {
        'name': 's2-selpain-ix',
        'why': 'SELPAIN loads IX once before its row loop and trusts it to '
               'survive SELXOR; PATINV uses IX on S2ED, so every row after '
               'the first reads its extent out of the pattern shadow.  Only '
               'this gate can catch it: S6ED\'s LMMV leaves IX alone',
        'target': 'S2ED',
        'file': 'ACTION.Z8A',
        'old': """SELPAIN         LD      B, 0
.ROWLP          LD      IX, SELSTRL
                PUSH    BC""",
        'new': """SELPAIN         LD      IX, SELSTRL     ; MUTATION: LOADED ONCE
                LD      B, 0
.ROWLP          PUSH    BC""",
        'filter': 'S2-19',
        'expect': ['S2-19/down1'],
    },
    {
        'name': 's2-wbox-title',
        'why': 'WBOX clears (WINNC-2)*8 bytes of the top row for the title '
               'instead of only the cells the title occupies, so the top '
               'edge survives only at the two corner cells',
        'target': 'S2ED',
        'file': 'WINDOW.Z8A',
        'old': """                ; SPAN: THE TITLE STARTS AT CHAR COLUMN (WINC+1)*2 AND
                ; WINPUTS CLIPS IT AT WINCLIM (OR THE RIGHT SCREEN EDGE
                ; WHEN WINCLIM IS 0), TWO CHARACTERS PER CELL
                LD      A, (WINC)
                INC     A
                ADD     A, A
                LD      C, A            ; C = START CHAR COLUMN
                LD      A, (WINCLIM)
                OR      A
                JR      NZ, .TLIM
                LD      A, SCRCOLS
.TLIM           SUB     C               ; A = COLUMNS BEFORE THE CLIP
                LD      B, A
                LD      C, 0            ; C = CHARACTERS DRAWN
                JR      Z, .TSPAN       ; NO ROOM: NOTHING TO CLEAR
.TLEN           LD      A, (HL)
                OR      A
                JR      Z, .TSPAN
                INC     HL
                INC     C
                DJNZ    .TLEN
.TSPAN          LD      A, C
                OR      A
                JR      Z, .TDRAW       ; EMPTY TITLE: NOTHING TO CLEAR
                INC     A
                SRL     A               ; CELLS = (CHARS+1)/2
                ADD     A, A
                ADD     A, A
                ADD     A, A
                LD      B, A            ; B = CELLS*8 BYTES
                LD      A, (WINR)
                ADD     A, #80          ; HIGH(PATSHAD)
                LD      H, A
                LD      A, (WINC)
                INC     A
                ADD     A, A
                ADD     A, A
                ADD     A, A
                LD      L, A            ; CELL WINC+1 OF THE TOP ROW
                XOR     A""",
        'new': """                ; MUTATION: CLEAR THE WHOLE INNER TOP EDGE
                LD      A, (WINR)
                ADD     A, #80          ; HIGH(PATSHAD)
                LD      H, A
                LD      A, (WINC)
                INC     A
                ADD     A, A
                ADD     A, A
                ADD     A, A
                LD      L, A
                LD      A, (WINNC)
                SUB     2
                ADD     A, A
                ADD     A, A
                ADD     A, A
                LD      B, A            ; (WINNC-2)*8 BYTES
                XOR     A""",
        'filter': 'S2-11',
        'expect': ['S2-11/top-edge'],
    },
    {
        # Round 2 fixed the same class in FILEIO.Z8A and stopped there.  This
        # is what was left in ACTDWLFT and ACTDLS: the attribute half of the
        # record addressed as "+ 81", right for a 1+80+80 record and 16 bytes
        # past the text on a 1+64+64 one.
        'name': 't0-layout-off',
        'why': 'CORE addresses the attribute half of a line record as + 81',
        'file': 'ACTION.Z8A',
        'old': 'LD      HL, WORKBUF + 1 + TEXTCOLS\n                ADD     HL, DE\n                EX      DE, HL          ; DE = DEST\n\n                LD      A, (DWFROM)',
        'new': 'LD      HL, WORKBUF + 81\n                ADD     HL, DE\n                EX      DE, HL          ; DE = DEST\n\n                LD      A, (DWFROM)',
        'filter': 'T0',
        'expect_static': ['target-params'],
    },
    {
        # EDDELBK / EDDELCHR walked the shift loop to a hard 79 and blanked
        # WORKBUF + 80.  On S2ED that drags attribute byte 0 into the last
        # text column, after which EDINSCHR sees a full record and silently
        # refuses every keystroke on that line.
        'name': 't0-geom-imm',
        'why': 'CORE bounds a record loop with the literal 79',
        'file': 'EDIT.Z8A',
        'old': '.SHIFTLP        LD      A, B\n                CP      TEXTCOLS - 1',
        'new': '.SHIFTLP        LD      A, B\n                CP      79',
        'filter': 'T0',
        'expect_static': ['target-params'],
    },
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
        'expect': ['G3/load-refused'],
    },
    {
        'name': 'load-rollback',
        'why': 'FILELOAD does not roll back on OOM, leaving truncated lines',
        'file': 'FILEIO.Z8A',
        'old': """.STORCR         CALL    STORLINE
                JR      C, .OOM""",
        'new': """.STORCR         CALL    STORLINE
                JR      C, .CLSFIL      ; MUTATION: NO ROLLBACK ON OOM""",
        'filter': 'G3',
        'expect': ['G3/load-refused'],
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
                CP      ROWSVIS""",
        'new': """                LD      HL, (TOPLINE)
                ADD     HL, DE
                NOP                     ; MUTATION: TOPLINE NOT ADVANCED
                NOP
                NOP
                LD      A, E
                CP      ROWSVIS""",
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
        # Re-anchored 2026-09-21: SPLITL takes its column through EFFCURX now.
        'old': """SPLITL          CALL    EFFCURX""",
        'new': """SPLITL          XOR     A               ; MUTATION: SPLIT AT COL 0""",
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
        # What executes at #8000 when the payload lands elsewhere is
        # UNINITIALISED MAPPER RAM, so the observable is undefined by nature:
        # sometimes an editor that reached MAINLOOP unconfigured, sometimes a
        # session that never gets there.  Pinning it to the first outcome is
        # why this stopped being caught on 2026-09-22 after an unrelated
        # change moved the payload -- expect_any states the real contract.
        'name': 'f2-datload',
        'why': 'DATLOAD loads feature payload at wrong address in page 2, so '
               'the FCALL enters uninitialised segment RAM',
        'file': 'XSEG.Z8A',
        'old': """                LD      A, (DATHAND)
                LD      HL, (DATBLK + 4)
                LD      DE, (DATBLK + 2)
                CALL    DSKREAD""",
        'new': """                LD      A, (DATHAND)
                LD      HL, (DATBLK + 4)
                LD      DE, #9000       ; MUTATION: LOAD AT WRONG ADDRESS
                CALL    DSKREAD""",
        'filter': 'G13',
        'expect_any': ['G13/cfg-applied', 'G13-feature-residency'],
    },
    {
        'name': 'f2-datmagic',
        'why': 'S6ED.DAT header magic corrupted',
        'file': 'S6ED.Z8A',
        'old': """DATHDRS:
                DEFM    "S6ED"          ; 0..3: MAGIC ID (4 BYTES)""",
        'new': """DATHDRS:
                DEFM    "S6XX"          ; MUTATION: CORRUPT MAGIC""",
        'filter': 'G13',
        'expect_static': ['feature-discipline'],
    },
    {
        'name': 'c1-datlen',
        'why': 'DATLOAD does not bound LENGTH or LOADADDR to the container '
               'window: a 16,385-byte payload writes past FTRTOP into the '
               'DOS area and the stack',
        'file': 'XSEG.Z8A',
        'old': """                LD      HL, (DATBLK + 4)
                LD      A, H
                OR      L
                JP      Z, .ERRCOR      ; LENGTH 0
                LD      DE, DATBLEN + 1
                OR      A
                SBC     HL, DE
                JP      NC, .ERRCOR     ; LENGTH > DATBLEN
                LD      HL, (DATBLK + 2)
                LD      DE, FTRBASE
                OR      A
                SBC     HL, DE
                JP      C, .ERRCOR      ; LOADADDR BELOW THE WINDOW
                LD      HL, FTRTOP
                LD      DE, (DATBLK + 2)
                OR      A
                SBC     HL, DE          ; HL = ROOM LEFT IN THE WINDOW
                JP      C, .ERRCOR      ; LOADADDR PAST THE WINDOW
                LD      DE, (DATBLK + 4)
                OR      A
                SBC     HL, DE
                JP      C, .ERRCOR      ; PAYLOAD OVERFLOWS FTRTOP""",
        'new': """                NOP                     ; MUTATION: NO LENGTH OR WINDOW BOUNDS""",
        'filter': 'H14',
        'expect': ['H14/corrupt-printed'],
    },
    {
        'name': 'c1-datblkid',
        'why': 'DATLOAD ignores BLKID and loads any block into FTRSEG',
        'file': 'XSEG.Z8A',
        'old': """                LD      A, (DATBLK)
                CALL    BLKSEG
                JP      C, .ERRCOR      ; UNKNOWN BLOCK ID
                LD      (DATSEG), A""",
        'new': """                LD      A, (DATBLK)
                CALL    BLKSEG
                LD      A, (FTRSEG)     ; MUTATION: UNKNOWN IDS LOAD INTO FTRSEG
                LD      (DATSEG), A""",
        'filter': 'H15',
        'expect': ['H15/corrupt-printed'],
    },
    {
        'name': 'c1-datseek',
        'why': 'DATLOAD reads the payload sequentially instead of seeking '
               'to DATAOFF: a padded or reordered container loads garbage',
        'file': 'XSEG.Z8A',
        'old': """                LD      A, (DATHAND)
                LD      HL, (DATBLK + 6)
                CALL    DSKSEEK
                JP      C, .ERRCOR""",
        'new': """                NOP                     ; MUTATION: NO SEEK, READ SEQUENTIALLY
                NOP
                NOP
                NOP""",
        'filter': 'H17',
        # The payload comes out shifted by the padding: either the editor
        # crashes before MAINLOOP (case-level failure) or it boots with the
        # CFG never applied.
        'expect_any': ['H17/cfg-applied', 'H17-dat-padded-seek'],
    },
    {
        'name': 'c2-wincarry',
        'why': 'WINOPEN applies AND %11111100 before JR NC, clearing carry and corrupting widths >= 253',
        'file': 'WINDOW.Z8A',
        'old': """                LD      HL, (WINW)
                LD      A, L
                ADD     A, 3
                LD      L, A
                JR      NC, .NOWINC
                INC     H
.NOWINC         LD      A, L
                AND     %11111100
                LD      L, A
                LD      (WINW), HL""",
        'new': """                LD      HL, (WINW)
                LD      A, L
                ADD     A, 3
                AND     %11111100
                LD      L, A
                JR      NC, .NOWINC
                INC     H
.NOWINC         LD      (WINW), HL""",
        'filter': 'H7',
        'expect_static': ['window-discipline'],
    },
    {
        'name': 'c2-winactv',
        'why': 'WINOPEN fails to set WINACTV=1 so modal window state is lost and clock is not inhibited',
        'file': 'WINDOW.Z8A',
        'old': """                ; MARK MODAL WINDOW ACTIVE TO INHIBIT CLOCK BLINK
                LD      A, 1
                LD      (WINACTV), A""",
        'new': """                ; MARK MODAL WINDOW ACTIVE TO INHIBIT CLOCK BLINK
                XOR     A
                LD      (WINACTV), A""",
        'filter': 'H7',
        'expect': ['H7/winactv-active'],
    },
    {
        'name': 'c2-winkil',
        'why': 'WINOPEN does not flush keyboard buffer so pre-queued keys dismiss modals prematurely',
        'file': 'WINDOW.Z8A',
        'old': """                ; FLUSH KEYBOARD BUFFER
                CALL    WINKIL""",
        'new': """                ; FLUSH KEYBOARD BUFFER
                NOP
                NOP
                NOP""",
        'filter': 'H18',
        'expect_any': ['H18/key-purged', 'window-discipline'],
    },
    {
        'name': 'c2-winclamp',
        'why': 'WINOPEN does not clamp geometry to screen and VRAM buffer bounds',
        'file': 'WINDOW.Z8A',
        'old': """                ; CLAMP WINX <= 504: WINX + WINW + WINSHDW <= 512, WINW >= 4
                LD      HL, (WINX)
                LD      DE, 504""",
        'new': """                ; CLAMP WINX <= 504: WINX + WINW + WINSHDW <= 512, WINW >= 4
                LD      HL, (WINX)
                LD      DE, 999         ; MUTATION: NO HORIZONTAL CLAMP""",
        'filter': 'H7',
        'expect_static': ['window-discipline'],
    },
    {
        'name': 'c3-accent',
        'why': 'the top accent band is painted in UI color instead of highlight',
        'file': 'WINDOW.Z8A',
        'old': """                ; 4. TOP ACCENT BAND (COL_HI, 1 PX)
                LD      DE, 0
                LD      HL, 1
                LD      A, CLR_HI""",
        'new': """                ; 4. TOP ACCENT BAND (COL_HI, 1 PX)
                LD      DE, 0
                LD      HL, 1
                LD      A, CLR_UI       ; MUTATION: ACCENT IN UI COLOR""",
        'filter': 'H7',
        'expect': ['H7/color-highlight'],
    },
    {
        'name': 'c3-shadow',
        'why': 'the shadow bars ignore SHADOW= and are hardcoded to the '
               'highlight colour, so the key cannot move them and the '
               'default stops being the background',
        'file': 'WINDOW.Z8A',
        'old': """                LD      HL, WINCOMP_Y + WINSHDW
                LD      (VDP_DY), HL
                LD      HL, WINSHDW
                LD      (VDP_NX), HL
                LD      HL, (WINH)
                LD      (VDP_NY), HL
                LD      A, (SHDWCLR)""",
        'new': """                LD      HL, WINCOMP_Y + WINSHDW
                LD      (VDP_DY), HL
                LD      HL, WINSHDW
                LD      (VDP_NX), HL
                LD      HL, (WINH)
                LD      (VDP_NY), HL
                LD      A, CLR_HI       ; MUTATION: SHADOW IN HIGHLIGHT""",
        'filter': 'H21',
        'expect': ['H21/bg/shadow-right', 'H21/ui/shadow-right'],
    },
    {
        'name': 'c3-winupd',
        'why': 'WINUPD blits from the save buffer instead of the composition buffer',
        'file': 'WINDOW.Z8A',
        'old': """                LD      HL, WINCOMP_Y
                ADD     HL, DE
                LD      (VDP_SY), HL    ; SY = WINCOMP_Y + REL Y""",
        'new': """                LD      HL, WINBUF_Y    ; MUTATION: WRONG SOURCE BUFFER
                ADD     HL, DE
                LD      (VDP_SY), HL    ; SY = WINCOMP_Y + REL Y""",
        'filter': 'H19',
        'expect': ['H19/nav-left'],
    },
    {
        'name': 'c2-winchtr-char',
        'why': 'WINSTR.LOOP clobbers A before calling WINCHTR so all characters become control patterns',
        'file': 'WINDOW.Z8A',
        'old': """                PUSH    AF
                LD      A, (WINVAR)
                LD      B, A
                LD      A, (WINOP)
                LD      C, A
                POP     AF
                CALL    WINCHTR""",
        'new': """                LD      A, (WINVAR)
                LD      B, A
                LD      A, (WINOP)
                LD      C, A
                CALL    WINCHTR""",
        'filter': 'H7',
        'expect': ['H7/title-text'],
    },
    {
        'name': 'wq-direct',
        'why': 'ACTQUIT jumps straight to TERM without asking (pre-3b behaviour)',
        'file': 'ACTION.Z8A',
        # Anchored below the FTR-BUDGET comment on purpose: that line carries
        # measured byte counts and is rewritten every time the container moves.
        'old': """                LD      A, (FTRSEG)
                LD      HL, DOQIT""",
        'new': """                JP      TERM            ; MUTATION: QUIT WITHOUT ASKING
                LD      HL, DOQIT""",
        'filter': 'H19',
        # ESC exits on the spot: either the dialog-displayed check goes red,
        # or the whole case dies waiting for a WINPOLL that never comes.
        'expect_any': ['H19/dialog-displayed', 'H19-quit-dialog'],
    },
    {
        'name': 'wq-defsel',
        'why': 'the Quit dialog defaults to YES, so an accidental ENTER quits',
        'file': 'WINDOW.Z8A',
        'old': """                ; DEFAULT: NO SELECTED, RESULT CANCELLED
                LD      A, 1
                LD      (WINSEL), A""",
        'new': """                ; DEFAULT: NO SELECTED, RESULT CANCELLED
                XOR     A               ; MUTATION: DEFAULT SELECTION = YES
                LD      (WINSEL), A""",
        'filter': 'H19',
        'expect': ['H19/default-no'],
    },
    {
        'name': 'wq-nav',
        'why': 'a selection change never repaints the buttons',
        'file': 'WINDOW.Z8A',
        'old': """                LD      (HL), A
                CALL    .BTNS
                CALL    WINVSY""",
        'new': """                LD      (HL), A
                CALL    WINVSY         ; MUTATION: SELECTION NEVER REPAINTS""",
        'filter': 'H19',
        'expect': ['H19/nav-left'],
    },
    {
        'name': 'wq-yes',
        'why': 'the Y accelerator records CANCEL instead of CONFIRM',
        'file': 'WINDOW.Z8A',
        'old': """.YES            LD      A, 1
                LD      (WINRES), A""",
        'new': """.YES            XOR     A               ; MUTATION: Y DOES NOT CONFIRM
                LD      (WINRES), A""",
        'filter': 'H19',
        # Y records CANCEL: either quit-y goes red, or the case dies waiting
        # for a TERM.TERMDON that never comes.
        'expect_any': ['H19/quit-y', 'H19-quit-dialog'],
    },
    {
        'name': 'menu-defsel',
        'why': 'File menu opens with item 1 selected instead of default item 0 (New)',
        'file': 'MENU.Z8A',
        'old': """.INITOK         XOR     A
                LD      (MNUSEL), A     ; DEFAULT SELECTION = 0 (NEW)""",
        'new': """.INITOK         LD      A, 1            ; MUTATION: DEFAULT SELECTION = 1
                LD      (MNUSEL), A""",
        'filter': 'H22',
        'expect': ['H22/default-new'],
    },
    {
        'name': 'menu-skipsep',
        'why': 'DOWN navigation fails to skip the separator line at item 4',
        'file': 'MENU.Z8A',
        'old': """.DWNCHK         CALL    MNUCHKS         ; SEPARATOR?
                JR      NZ, .DWNOK
                INC     A               ; SKIP SEPARATOR
.DWNOK          JR      .MOVE""",
        'new': """.DWNCHK         CALL    MNUCHKS         ; SEPARATOR?
                NOP                     ; MUTATION: NEVER SKIP SEPARATOR
                NOP
                NOP
                NOP
.DWNOK          JR      .MOVE""",
        'filter': 'H22',
        'expect': ['H22/nav-skip-sep'],
    },
    {
        'name': 'menu-title',
        'why': 'cancellation leaves the row 0 File title inverted',
        'file': 'MENU.Z8A',
        'old': """.CANCEL         CALL    WINCLOS
                CALL    MNUTITL         ; UN-HIGHLIGHT TITLE
                SCF                     ; CY = 1 (CANCELLED)""",
        'new': """.CANCEL         CALL    WINCLOS
                NOP                     ; MUTATION: DO NOT UN-HIGHLIGHT TITLE
                NOP
                NOP
                SCF                     ; CY = 1 (CANCELLED)""",
        'filter': 'H22',
        'expect': ['H22/cancel-esc'],
    },
    {
        'name': 'menu-nav-wrap',
        'why': 'RIGHT navigation fails to wrap from Help (4) to File (0)',
        'file': 'MENU.Z8A',
        'old': """.RIGHT          LD      A, (MNUID)
                INC     A
                CP      MNUCOUNT        ; 5
                JR      C, .RGHTOK
                XOR     A               ; WRAP 4 -> 0
.RGHTOK         JP      MNUSWCH""",
        'new': """.RIGHT          LD      A, (MNUID)
                INC     A
                CP      MNUCOUNT        ; 5
                JR      C, .RGHTOK
                LD      A, 4            ; MUTATION: CLAMP TO 4 INSTEAD OF WRAPPING TO 0
.RGHTOK         JP      MNUSWCH""",
        'filter': 'H23',
        'expect': ['H23/nav-right-wrap'],
    },
    {
        'name': 'menu-switch-title',
        'why': 'horizontal switch fails to un-highlight previous menu title',
        'file': 'MENU.Z8A',
        'old': """; 2. UN-HIGHLIGHT CURRENT TITLE IN ROW 0
                CALL    MNUTITL
                POP     BC""",
        'new': """; 2. UN-HIGHLIGHT CURRENT TITLE IN ROW 0
                NOP                     ; MUTATION: SKIP UN-HIGHLIGHT
                NOP
                NOP
                POP     BC""",
        'filter': 'H23',
        'expect': ['H23/title-switch-xor'],
    },
    {
        'name': 'menu-opt-prof',
        'why': 'Options menu item 0 calls ACTCYCMK instead of ACTCYCKM',
        'file': 'ACTION.Z8A',
        'old': """.OPROF          CALL    ACTCYCKM
                JP      DRWSTAT""",
        'new': """.OPROF          CALL    ACTCYCMK        ; MUTATION: WRONG DISPATCH
                JP      DRWSTAT""",
        'filter': 'H23',
        'expect': ['H23/action-keymap-prof'],
    },
    {
        'name': 'undo-dispatch',
        'why': 'Undo action fails to execute when ACTUNDO vector is disconnected',
        'file': 'ACTION.Z8A',
        'old': '                DEFW    ACTUNDO         ; 57 (UNDO)',
        'new': '                DEFW    ACTNONE         ; MUTATION: DISABLE UNDO DISPATCH',
        'filter': 'U1',
        'expect': ['U1/undone-state'],
    },
    {
        'name': 'undo-del',
        'why': 'line deletion fails to record in undo ringbuffer when UNDODEL is bypassed',
        'file': 'ACTION.Z8A',
        'old': """.DLMULT         LD      HL, (DOCLINE)
                CALL    LINEREAD
                CALL    UNDODEL""",
        'new': """.DLMULT         LD      HL, (DOCLINE)
                CALL    LINEREAD
                NOP
                NOP
                NOP""",
        'filter': 'U2',
        'expect': ['U2/undone-totlines'],
    },
    {
        'name': 'undo-split',
        'why': 'line split fails to record in undo ringbuffer when UNDOSPL is bypassed',
        'file': 'EDIT.Z8A',
        'old': """; 2. LOAD THE LINE THAT IS ABOUT TO BE SPLIT
                LD      HL, (DOCLINE)
                CALL    LINEREAD
                CALL    UNDOSPL""",
        'new': """; 2. LOAD THE LINE THAT IS ABOUT TO BE SPLIT
                LD      HL, (DOCLINE)
                CALL    LINEREAD
                NOP
                NOP
                NOP""",
        'filter': 'U3',
        'expect': ['U3/undone-totlines'],
    },
    {
        'name': 'undo-join',
        'why': 'line join fails to record in undo ringbuffer when UNDOJON is bypassed',
        'file': 'EDIT.Z8A',
        'old': """; RECORD JOIN IN UNDO RING BUFFER
                CALL    UNDOJON
                LD      HL, (JOINLA)""",
        'new': """; RECORD JOIN IN UNDO RING BUFFER
                NOP
                NOP
                NOP
                LD      HL, (JOINLA)""",
        'filter': 'U4',
        'expect': ['U4/undone-totlines'],
    },
    {
        'name': 'undo-sel',
        'why': 'ACTUNDO fails to cancel active selection leaving inverted characters in VRAM',
        'file': 'UNDO.Z8A',
        'old': """ACTUNDO         CALL    UNDOCLS
                LD      A, (SELACT)
                OR      A
                CALL    NZ, ACTDSEL""",
        'new': """ACTUNDO         CALL    UNDOCLS
                NOP
                NOP
                NOP
                NOP
                NOP
                NOP
                NOP""",
        'filter': 'U5',
        'expect': ['U5/sel-cancelled'],
    },
    {
        'name': 'undo-seldel-rec',
        'why': 'ACTDLS records nothing again: a deleted selection cannot be '
               'undone, and older history replays on the wrong line',
        'file': 'ACTION.Z8A',
        'old': """.DLSNEMP        ; RECORD EVERY LINE THE DELETE TOUCHES, AS ONE UNDO GROUP
                LD      A, UNDOT_DEL
                CALL    UNDOSEL""",
        'new': """.DLSNEMP        ; MUTATION: NOTHING RECORDED
                LD      A, UNDOT_DEL""",
        'filter': 'U6',
        'expect': ['U6/multi/recorded', 'U6/stale/content'],
    },
    {
        'name': 'undo-group-loop',
        'why': 'ACTUNDO stops after one record, ignoring the chain: a '
               'three-line delete comes back one line at a time',
        'file': 'UNDO.Z8A',
        'old': """                LD      A, B
                AND     UNDOF_CHN
                JP      Z, UNDOPNT      ; THE GROUP'S FIRST RECORD: DONE""",
        'new': """                JP      UNDOPNT         ; MUTATION: ONE RECORD PER CTRL+Z""",
        'filter': 'U6',
        'expect': ['U6/multi/undo'],
    },
    {
        'name': 'undo-redo-loop',
        'why': 'ACTREDO re-applies only the first record of a group',
        'file': 'UNDO.Z8A',
        'old': """                AND     UNDOF_CHN
                JR      Z, .RDDONE      ; NEXT RECORD STARTS ANOTHER ACTION""",
        'new': """                JR      .RDDONE         ; MUTATION: NEVER FOLLOW THE CHAIN""",
        'filter': 'U6',
        'expect': ['U6/multi/redo'],
    },
    {
        'name': 'undo-evict-group',
        'why': 'eviction takes only the colliding record, leaving the rest of '
               'its group to be replayed without its first record',
        'file': 'UNDO.Z8A',
        'old': """                LD      IX, (UNDOBOT)
                LD      A, (IX + 4)
                AND     UNDOF_CHN
                JR      NZ, .EVICT
                JR      .EVCLP          ; CHECK IF NEXT RECORD ALSO COLLIDES""",
        'new': """                JR      .EVCLP          ; MUTATION: GROUPS EVICTED PIECEMEAL""",
        'filter': 'U7',
        'expect': ['U7/evict/content'],
    },
    {
        'name': 'undo-redo-trunc',
        'why': 'a new edit leaves the head linked to the stale redo records: '
               'evicting the head makes the new record its own predecessor',
        'file': 'UNDO.Z8A',
        'old': """                OR      L
                JR      Z, .NOREDO""",
        'new': """                OR      L
                JR      .NOREDO         ; MUTATION: REDO CHAIN LEFT LINKED""",
        'filter': 'U7',
        'expect': ['U7/selfloop/content'],
    },
    {
        'name': 'undo-group-cap',
        'why': 'a group larger than the ring is recorded anyway and evicts its '
               'own first record, leaving a headless tail to replay',
        'file': 'UNDO.Z8A',
        'old': """                CALL    CMPHLDE
                JR      C, .FITS""",
        'new': """                CALL    CMPHLDE
                JR      .FITS           ; MUTATION: NO CAPACITY CHECK""",
        'filter': 'U7',
        'expect': ['U7/toobig/dropped'],
    },
    {
        'name': 'undo-evict-window',
        'why': 'the shipped collision test: its second subtraction ran with '
               'the write base in both registers, so every record above the '
               'write point was evicted -- the whole history on each wrap',
        'file': 'UNDO.Z8A',
        'old': """                SBC     HL, DE          ; HL = UNDOBOT - WRITE BASE
                JR      C, .EVCBEL      ; BELOW THE WINDOW
                LD      DE, UNDOMOD_SZ
                SBC     HL, DE          ; CY = 1 INSIDE THE WINDOW (CY WAS 0)
                POP     HL              ; HL = WRITE BASE
                JR      NC, .EVCDON     ; PAST THE WINDOW -> DONE""",
        'new': """                SBC     HL, DE          ; HL = UNDOBOT - WRITE BASE
                POP     HL
                JR      C, .EVCDON
                PUSH    HL              ; MUTATION: THE 2026-09-19 TEST
                EX      DE, HL
                OR      A
                SBC     HL, DE
                LD      DE, UNDOMOD_SZ
                OR      A
                SBC     HL, DE
                POP     HL
                JR      NC, .EVCDON""",
        'filter': 'U7',
        'expect': ['U7/depth/content', 'U7/evict/content'],
    },
    {
        'name': 'undo-reflow-drop',
        'why': 'a reflow that pulls a whole line up keeps the history, whose '
               'records then name lines the reflow shifted',
        'file': 'EDIT.Z8A',
        'old': """.RFALL          ; ENTIRE LINE L+1 FITS ON LINE L!
                CALL    UNDOINIT""",
        'new': """.RFALL          ; ENTIRE LINE L+1 FITS ON LINE L! MUTATION: HISTORY KEPT""",
        'filter': 'U8',
        'expect': ['U8/reflow/content'],
    },
    {
        'name': 'undo-pushwrap-drop',
        'why': 'push-wrap inserts a line and keeps the history, whose records '
               'then name lines one off',
        'file': 'EDIT.Z8A',
        'old': """                ; (UNDOINIT KEEPS BC AND DE)
                CALL    UNDOINIT""",
        'new': """                ; MUTATION: HISTORY KEPT""",
        'filter': 'U8',
        'expect': ['U8/pushwrap/content'],
    },
    {
        'name': 'undo-insrun-rec',
        'why': 'a pasted run is written with no record, so Ctrl+Z skips it',
        'file': 'EDIT.Z8A',
        'old': """.IRFITS         ; ONE LINE CHANGES: RECORD IT AS IT STANDS IN WORKBUF
                CALL    UNDOCLS
                LD      A, UNDOT_MOD
                CALL    UNDOREC""",
        'new': """.IRFITS         ; MUTATION: NOT RECORDED""",
        'filter': 'U9',
        'expect': ['U9/paste/content'],
    },
    {
        'name': 'undo-dwlft-rec',
        'why': 'word delete is written with no record',
        'file': 'ACTION.Z8A',
        'old': """                ; CTRL+Z PUTS THE CURSOR BACK AFTER THE WORD
                CALL    UNDOCLS
                LD      A, UNDOT_MOD
                CALL    UNDOREC""",
        'new': """                ; MUTATION: NOT RECORDED""",
        'filter': 'U9',
        'expect': ['U9/wordel/content'],
    },
    {
        'name': 'undo-wrapsel-rec',
        'why': 'wrapping a selection in markup delimiters is not recorded',
        'file': 'MARKUP.Z8A',
        'old': """                CALL    UNDOCLS
                LD      HL, (SELSTRL)
                LD      A, UNDOT_MOD
                CALL    UNDOLNR""",
        'new': """                ; MUTATION: NOT RECORDED""",
        'filter': 'U9',
        'expect': ['U9/wrapsel/content'],
    },
    {
        'name': 'undo-applsel-rec',
        'why': 'toggling bold across a selection is not recorded',
        'file': 'ACTION.Z8A',
        'old': """.APLINIT        LD      A, UNDOT_MOD    ; EVERY SELECTED LINE, ONE UNDO GROUP
                CALL    UNDOSEL""",
        'new': """.APLINIT        ; MUTATION: NOT RECORDED""",
        'filter': 'U9',
        'expect': ['U9/style/undo'],
    },
    {
        'name': 'undo-dls-showln',
        'why': 'deleting a selection that starts above the viewport leaves '
               'TOPLINE alone, so CURY goes negative',
        'file': 'ACTION.Z8A',
        'old': """                LD      HL, (SELSTRL)
                LD      (DOCLINE), HL
                CALL    SHOWLN
                CALL    REDRAW""",
        'new': """                LD      HL, (SELSTRL)
                LD      (DOCLINE), HL
                CALL    SETCURY         ; MUTATION: NOT BROUGHT ON SCREEN
                CALL    REDRAW""",
        'filter': 'U6',
        'expect': ['U6/scrolled/visible'],
    },
    {
        'name': 'undo-pnt-showln',
        'why': 'the repaint after an undo trusts the recorded TOPLINE, which '
               'need not show a cursor restored above it',
        'file': 'UNDO.Z8A',
        'old': """UNDOPNT         LD      HL, (DOCLINE)
                CALL    SHOWLN""",
        'new': """UNDOPNT         CALL    SETCURY         ; MUTATION: TOPLINE TRUSTED""",
        'filter': 'U6',
        'expect': ['U6/scrolled/visible'],
    },
    {
        'name': 's2-undo-seldel',
        'why': 'the reported S2ED flow: select the TEST lines, DEL, Ctrl+Z '
               'restores nothing',
        'target': 'S2ED',
        'file': 'ACTION.Z8A',
        'old': """.DLSNEMP        ; RECORD EVERY LINE THE DELETE TOUCHES, AS ONE UNDO GROUP
                LD      A, UNDOT_DEL
                CALL    UNDOSEL""",
        'new': """.DLSNEMP        ; MUTATION: NOTHING RECORDED
                LD      A, UNDOT_DEL""",
        'filter': 'S2-20',
        'expect': ['S2-20/fresh/cycle'],
    },
    {
        'name': 's2-undo-gmax',
        'why': 'UNDOGMAX set too low: S2ED would drop the history on any delete '
               'over 15 lines instead of 28',
        'target': 'S2ED',
        'file': 'CONST_CORE.Z8A',
        'old': """UNDOGMAX        EQU     (UNDOSIZ - UNDOMOD_SZ + 1) / UNDOMOD_SZ""",
        'new': """UNDOGMAX        EQU     15              ; MUTATION: GMAX TOO LOW""",
        'filter': 'S2-20',
        'expect': ['S2-20/big/cycle'],
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
            path = self.ctx.find_src_file(fname)
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
