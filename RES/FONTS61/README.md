# S61ED example fonts

Example 8x8 fonts for S61ED, built by `../mkfont61.py` from the raw fonts of
other machines, and the editable sheets they produce. Each `.FNT` is four
variants of 2,048 bytes (NORMAL, BOLD, ITALIC, BOLD+ITALIC) in the MSX
international character order; the Makefile builds them, the disks carry them
in `A:\TOOLS\FONTS\`. S61ED's default `S61ED.FNT` is not one of them: it is
the commissioned face by Miguel A. Fernandez, drawn on `../FONTSHEET_S64.PNG`
(NORMAL block; `mkfont61.py sheet --derive` generates the other three weights
until he draws them). `S61ED.PNG` here is that font as a full four-block
sheet, the one to retouch.

| File | Source | Order |
|---|---|---|
| `CGA-TH.F08` | IBM CGA, alternate thin (single-dot) ROM font | CP437 |
| `CGA.F08` | IBM CGA, standard thick (double-dot) ROM font | CP437 |
| `CPC464.F08` | Amstrad CPC 464 firmware ROM, bytes #3800-#3FFF | CPC |
| `*.PNG` | the sheets `mkfont61.py import --sheet` wrote | MSX |
| `S61ED.PNG` | the default face, `mkfont61.py sheet --derive --sheet` | MSX |

**IBM CGA.** NORMAL is the thin font and BOLD the thick one: the CGA card
carried both and IBM's own choice of the thick one as the default is what
makes the pair a regular/bold family. Every Spanish character is native
(CP437 and the MSX set agree on #80-#AF). The raw dumps come from VileR's
collection, https://github.com/viler-int10h/vga-text-mode-fonts
(`FONTS/PC-IBM/CGA.F08`, `CGA-TH.F08`), whose notes state that including these
plain bitmap fonts does not, as far as its author could determine, violate
any associated copyright. Font design (c) IBM.

**Amstrad CPC 464.** Extracted from `cpc464.rom` as shipped by the Caprice32
emulator (https://github.com/ColinPitrat/caprice32, `rom/cpc464.rom`, offset
#3800, 2,048 bytes). The CPC set has no accented letters: `mkfont61.py`
composes them from the CPC's own spacing marks (acute, grave, circumflex,
diaeresis, tilde) and draws cedilla and ring; BOLD and ITALIC are derived.
*Amstrad have kindly given their permission for the redistribution of their
copyrighted material but retain that copyright.* The ROM was written by
Locomotive Software, whose position on redistribution is not documented.

**MSX BIOS.** `BIOS.PNG` is the international MSX character generator as a
sheet, to start a new design from.

Glyphs a source does not have come from the MSX BIOS font: mostly the
geometric mosaics at #C0-#DF, which the BIOS already draws edge to edge.
`mkfont61.py import --report` lists, for each font, what was composed and what
was borrowed.
