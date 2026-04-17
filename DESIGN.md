# S6ED — MSX2 Screen 6 Text Editor

## Concept

A text editor for MSX2 running in SCREEN 6 (GRAPHIC 5):
- 512×212 pixels, 4 colors from 512-color palette
- Pure bitmap mode — software character rendering
- Target: 80 columns × 26 rows with 6×8 pixel font

## Why Screen 6

- 512 horizontal pixels → 80 text columns with 6px font, plus UI gutters
- VDP hardware commands handle scrolling and clearing in one operation
- Full control over font rendering (custom glyphs, styles)
- Sprite mode 2 available for cursor

## Screen Layout

```
Total width: 512px

  [left gutter: 24px] [text area: 480px] [right gutter: 8px]

Left gutter  — line numbers, right-justified, color 2 (UI chrome)
Text area    — 80 cols × 26 rows @ 6×8px
Right gutter — vertical scroll position bar, color 2
```

### Line Number Format

```
Width: 4 chars × 6px = 24px

Lines 1–9999  : right-justified decimal  "   1" " 999" "9999"
Lines 10000+  : k-notation               " 10k" " 99k" "999k"
Lines 1000000+: m-notation               "  1m"
```

### Scroll Bar (right gutter, 8px wide)

```
Thumb height  = (visible_rows / total_rows) × 212  (min 4px)
Thumb Y       = (top_line / total_rows) × 212
Draw with HMMV: 8px wide × thumb_height, updated on every scroll
```

## VRAM Layout

```
SCREEN 6 (GR5): 2bpp, 4 dots/byte, 128 bytes/line

  00000H – 069FFH   Bitmap display (128 × 212 = 27136 bytes)
  06A00H – 06BFFH   Sprite Attribute Table (SAT)
  06C00H – 06FFFH   Sprite Generator Table (SGT)

  Font tables (256 glyphs × 16 bytes each = 4096 bytes per variant):
  07000H – 07FFFH   Font — Normal
  08000H – 08FFFH   Font — Bold
  09000H – 09FFFH   Font — Italic
  0A000H – 0AFFFH   Font — Bold+Italic

  Glyph layout (all tables identical structure):
    32 glyphs per row → 8 rows (256 glyphs total)
    Glyph N: X = (N % 32) * 6,  Y = table_base_y + (N / 32) * 8
    Each glyph = 6×8px = 2 bytes/row × 8 rows = 16 bytes
    (rightmost 2px of each 8px slot = color 0 padding)
```

## Character Grid

```
80 columns × 26 rows
Cell width:  6px (2 bytes in VRAM at 4px/byte, right 2px = padding)
Cell height: 8px

Cell VRAM byte address (text area origin = X:24, Y:0):
  row * 8 * 128 + 24/4 + col * 6/4   ← not byte-aligned; use pixel coords
  DX = 24 + col * 6
  DY = row * 8
```

## Pixel Format (2bpp)

```
Each byte: [px0_b1|px0_b0|px1_b1|px1_b0|px2_b1|px2_b0|px3_b1|px3_b0]
Leftmost pixel in high bits.
Color index 0–3 maps to palette entry 0–3.
```

## Color Palette (4 colors)

Screen 6 is 2bpp = 4 colors, half the VRAM bandwidth of Screen 7 (4bpp).
For a text editor doing constant scroll + full redraw, Screen 6 is strictly faster:

```
Scroll HMMM (480px × 204px):
  Screen 6 → 24,480 bytes     Screen 7 → 48,960 bytes  (2× slower)
```

Screen 6 is the correct choice. 3 usable text colors is enough for syntax highlighting.

### Text / Writer Mode

```
Color 0: Background        (dark blue or black)
Color 1: Normal text       (white / light gray)
Color 2: UI chrome         (gutters, status bar)
Color 3: Cursor / accent
```

### Programmer Mode (syntax highlighting)

Color 2 and 3 are repurposed in the text area; gutters keep their palette entries
but the programmer selects aesthetically matching values at startup.

```
Color 0: Background
Color 1: Default text — labels, symbols, operators, immediates
Color 2: Mnemonics / reserved words   (e.g. cyan or green)
Color 3: Registers                    (e.g. yellow or orange)
```

Syntax categories → color mapping (Z80 assembly example):

| Token class      | Examples               | Color |
|------------------|------------------------|-------|
| Mnemonic         | LD, CALL, DJNZ, PUSH   | 2     |
| Register         | A, HL, IX, SP          | 3     |
| Immediate/number | 10, 0FFH, $1A, %1010   | 1     |
| Label/symbol     | LOOP:, MY_CONST        | 1     |
| Comment          | ; text                 | 2 (dim, same slot as mnemonic — palette choice) |
| String           | "hello"                | 3     |

Comments share color 2 with mnemonics (distinguishable via palette brightness).
Future language modes remap the same 3-color scheme to their own token classes.

## Font

### Source

MSX Screen 0 (TEXT 1) ROM charset — 256 glyphs × 8 bytes, 1bpp, 6 significant
bits per row (bits 7–2). Address read from BIOS work area `CGPNT` at `0004H`.

This is the native 6×8 font; no external asset required.

### Startup Expansion

For each glyph in the ROM font, generate all four VRAM variants:

```
Normal:
  foreach row: expand bits 7-2 → 6 pixels of color 0/1; pad 2 right pixels to 0

Bold:
  foreach row: normal_row | (normal_row >> 1)
  (OR with 1px-right-shifted self — thickens strokes)

Italic:
  Row shift table (8 rows): +1 +1 +1 +1  0  -1 -1 -1
  (positive = shift row left, creating forward slant)
  Clip pixels shifted out of the 6px window

Bold+Italic:
  Apply bold transform first, then italic shift
```

All variants written to respective VRAM font tables via HMMC or block OTIR.

### Underline

Not stored as a glyph variant. Rendered as a post-blit attribute:

```
After LMMM for the character glyph:
  LMMV at DX, DY+7, NX=6, NY=1, CLR=color1, CMR=HMMV|IMP
```

### Character Attributes (per cell)

Each cell in the text buffer carries a 1-byte attribute:

```
Bit 0 : Bold
Bit 1 : Italic
Bit 2 : Underline
Bit 3 : Inverse
Bits 4–7: reserved / color pair index (future)
```

Bits 0–1 select the VRAM font table (Normal / Bold / Italic / Bold+Italic).
Bits 2–3 are rendering modifiers applied after the base blit (see below).

## Character Rendering

### Blit with LMMM

```
variant    = attr & 3            ; 0=Normal 1=Bold 2=Italic 3=Bold+Italic
font_base_y = variant * 64       ; each table = 8 glyph rows × 8px = 64px
                                 ; mapped into VRAM Y space above display
SX = (charcode % 32) * 6
SY = font_base_y + (charcode / 32) * 8
DX = 24 + col * 6               ; 24px left-gutter offset
DY = row * 8
NX = 6,  NY = 8
```

**Normal** (no inverse):
```
CMR = LMMM | IMP                 ; direct copy — 1 command
```

**Inverse** (attr bit 3 set):
```
HMMV DX, DY, NX=6, NY=8, CLR=color1   ; flood cell with fg color
CMR  = LMMM | XOR                      ; ink: 1 XOR 1 = 0  bg: 0 XOR 1 = 1
```
No extra VRAM tables. Two commands instead of one; acceptable for inverse cells.

**Underline** (attr bit 2 set, applied after base blit):
```
HMMV DX, DY+7, NX=6, NY=1, CLR=color1
```

**Future — color pairs** (attr bits 4–7):
```
HMMV DX, DY, NX=6, NY=8, CLR=color_bg  ; fill with pair background
LMMM with TIMP                           ; blit only ink pixels (color 0 = transparent)
```
TIMP preserves the background fill wherever the glyph has color 0.

Poll S#2 bit CE between commands (or pipeline ahead).

## Scrolling

Single HMMM command scrolls the text area up one row (8px):

```
SX=24, SY=8,   DX=24, DY=0
NX=480, NY=204          ; 25.5 rows → 25 rows (204px)
CMR = HMMM
```

Clear last row:
```
HMMV DX=24, DY=208, NX=480, NY=8, CLR=0x00
```

Gutters are not scrolled — they are redrawn independently.

## Cursor

**Option A — XOR overlay via LMMV:**
Draw 6×8 block at cursor cell with XOR logical op each blink tick.
No background save needed. Toggle on/off with same command.

**Option B — Sprite:**
One mode-2 sprite, positioned at cursor pixel coords.
Underline cursor: 6×1 sprite or 6×2 for visibility.

## Text Buffer

```
Fixed-width line buffer:
  80 bytes  text  (one byte per column)
  80 bytes  attr  (one attribute byte per column — see Character Attributes)
  Total per line: 160 bytes

128 lines default → 128 × 160 = 20480 bytes
Line array: flat block; line N starts at N * 160
Attr array begins at line_base + 80

Cursor: (col, row) in document space
Viewport: top_line (first visible document line)
```

## Operations

| Operation         | VDP Command     | Notes                                    |
|-------------------|-----------------|------------------------------------------|
| Draw char         | LMMM            | Font VRAM → screen (6×8)                |
| Underline         | HMMV            | 6×1 fill at row+7                        |
| Clear cell        | HMMV            | Fill 2×8 bytes with color 0             |
| Scroll up/down    | HMMM + HMMV     | Move 480px-wide strip, clear last row   |
| Clear screen      | HMMV            | Fill text area (480×208)                |
| Cursor blink      | LMMV + XOR      | Toggle cursor cell                      |
| Update line nums  | LMMM × 4        | Re-blit 4 chars in left gutter          |
| Update scrollbar  | HMMV × 2        | Erase old thumb, draw new thumb         |
| Status bar        | HMMV + LMMM     | Fill row 26 (or overlay on row 25)      |

## Programmer Mode — Tokenizer

Runs on a single line each time it is modified or loaded into the viewport.
Output: fills the attr byte (bits 4–7 = color pair) for each column.

### Language Descriptor

A small fixed-size block pointed to by `LANG_DESC` (a single word in RAM).
Switching language = one `LD (LANG_DESC), HL`.

```
Offset  Size  Field
  0      2    kw_table     — ptr to primary keyword table   → color 2
  2      2    sec_table    — ptr to secondary token table   → color 3
  4      1    comment_ch   — line comment start char  (e.g. ';' '#' 0=none)
  5      1    comment_ch2  — alternate comment char   (e.g. '/' for //, 0=none)
  6      1    string_ch    — string delimiter          (e.g. '"' 0=none)
  7      1    flags        — bit0: case-insensitive lookup (BASIC, Z80 mnemonics)
                             bit1: # starts preprocessor line (C)
                             bit2: label ends with ':'
                             bit3: first token is always keyword (Z80/BASIC)
  8      2    tokenize_fn  — ptr to custom tokenizer, or 0 = use default engine
```

### Keyword Tables

Each table is a sorted list of uppercase null-terminated strings, terminated by
an empty entry (0x00). Sorted order enables binary search on Z80.

```
kw_table_z80:
  DB "ADC",0, "ADD",0, "AND",0, "BIT",0, "CALL",0, "CCF",0 ...
  DB 0                 ; end sentinel

sec_table_z80:
  DB "A",0, "AF",0, "B",0, "BC",0, "C",0, "D",0, "DE",0 ...
  DB 0
```

### Default Tokenizer Algorithm

Handles most line-oriented languages (Z80, BASIC, Python, simple C):

```
  1. If flags.bit1 and line[0]='#' → whole line color 2 (preprocessor); done
  2. Skip leading whitespace
  3. Collect token (alphanum + '_' + language-specific chars like '$' '%')
  4. If flags.bit2 and token ends ':' → color 1 (label); goto step 5
  5. If flags.bit3 OR binary_search(kw_table, token) → color 2
     else binary_search(sec_table, token):
       found  → color 3
       digit / '$' / '%' / '0x' prefix → color 1 (immediate/number)
       otherwise → color 1 (symbol)
  6. Repeat from step 2 for next token
  7. If comment_ch found → rest of line color 2
     If comment_ch2 found and next char == comment_ch2 → same
```

### Built-in Language Modes

| Mode    | kw_table          | sec_table        | Comment | Notes                    |
|---------|-------------------|------------------|---------|--------------------------|
| Z80     | ~100 mnemonics    | ~30 registers    | `;`     | case-insensitive, labels |
| BASIC   | ~60 keywords      | ~40 functions    | `REM`   | case-insensitive         |
| C       | ~30 keywords      | types + stdlib   | `//`    | bit1 flag for #define    |
| Python  | ~35 keywords      | builtins         | `#`     | —                        |
| None    | —                 | —                | —       | plain text / writer mode |

Custom modes: provide a descriptor block + optionally a `tokenize_fn` for
languages that need multi-line state (block comments, heredocs — future).

## Phases

1. **Scaffold** — init SCREEN 6, set palette, clear VRAM
2. **Font** — read ROM 6×8 charset via CGPNT; generate Normal/Bold/Italic/Bold+Italic tables; upload to VRAM
3. **Renderer** — putchar(col, row, char, attr), clearline(row), redraw_screen()
4. **Gutters** — draw_linenum(row, n), draw_scrollbar(top, total)
5. **Cursor** — draw/erase, blink via TIMI hook
6. **Input** — CHGET / keyboard matrix scan, insert/delete char, attribute toggle keys
7. **Scroll** — HMMM-based scroll up/down, page up/page down; scrollbar update
8. **Status bar** — mode, filename, col/row position
9. **Tokenizer** — per-line syntax highlighter, pluggable language tables
10. **File I/O** — MSX-DOS BDOS fn 0FH+27H to load/save (optional)

## Memory Model

### Requirements

- **Mandatory: MSX-DOS2 or Nextor** — uses the DOS2 mapper manager API.
- Distributed as a standard `.COM` binary.

### Page Map

```
0000H–00FFH   Page 0 — DOS2 zero page (BDOS entry at 0005H)
0100H–3FFFH   Page 0 — Editor code + small vars  (~16KB, .COM loads here)
4000H–7FFFH   Page 1 — Line directory segment (DIRSEG, fixed — never switched)
8000H–BFFFH   Page 2 — Text segment window (TXSEG, switched per line access)
C000H–FFFFH   Page 3 — DOS2/Nextor kernel (untouched)
```

Code target: keep within page 0 (0100H–3FFFH ≈ 16KB).
If code overflows page 0, page 1 can host an extra code segment instead;
the directory would then fall back to RDSEG/WRSEG access (slower but functional).

### Mapper Segment Usage

**Never use direct `OUT (0FEH), A`** — bypasses DOS2 mapper manager,
corrupts internal segment tracking.

All mapper operations go through DOS2/Nextor mapper support routines,
located at startup via EXTBIO (D=4, E=2 → HL = jump table).

```
Startup sequence:
  1. MAPINIT: EXTBIO → store PUT_P1, GET_P1, PUT_P2, GET_P2,
              ALL_SEG, FRE_SEG, RD_SEG, WR_SEG entry addresses in VARS
  2. BUFINIT: ALLSEG → DIRSEG; PUTP1 → bank into page 1 (4000H, permanent)
              ALLSEG → TXSEG;  PUTP2 → bank into page 2 (8000H, first text)
```

```
ALL_SEG  input:  A=0 (user seg), B=0 (primary mapper)
         output: A=segment number; Fc=1 if none free

FRE_SEG  input:  A=segment number, B=0 (primary mapper)

PUT_P1   input:  A=segment number  → banks into 4000H–7FFFH
PUT_P2   input:  A=segment number  → banks into 8000H–BFFFH
GET_P1 / GET_P2  output: A = currently banked segment

RD_SEG   input:  A=segment, HL=address → output: A=byte  (no page disturbed)
WR_SEG   input:  A=segment, HL=address, E=byte            (no page disturbed)
```

### Text Buffer Layout

Lines stored packed and variable-length in text segments (page 2 window).

```
Per-line record:
  [1 byte : text_len]   0–80
  [N bytes: text]       raw characters
  [N bytes: attr]       one attribute byte per character
  Max: 1 + 80 + 80 = 161 bytes   Min: 1 byte (empty line)

Segment capacity:
  16384 / 161 ≈  101 lines  (all 80-char lines)
  16384 /   1 = 16384 lines (all empty)
  Typical ~40 chars/line:   ~200 lines/segment
```

### Line Directory

Flat array at DIRPAGE (4000H) in a dedicated mapper segment (DIRSEG).
Banked into page 1 at startup via PUT_P1 — **never switched**.
Directly accessible as a flat array; no RDSEG/WRSEG needed.

```
Entry: 3 bytes
  [1 byte : segment number]   which text segment holds this line
  [2 bytes: byte offset]      position of line record within that segment

Capacity: 16384 / 3 = 5461 → MAXLINES = 5460
```

### Editing Workflow

```
Open line N for editing:
  1. entry_addr = DIRPAGE + N*3              ; direct — page 1 always mapped
     A  = (entry_addr)                       ; text segment number
     DE = (entry_addr+1)                     ; byte offset within segment
  2. CP (TXSEG): if different → PUTP2 A / LD (TXSEG), A
  3. LD HL, TXPAGE / ADD HL, DE             ; source in page 2
     LD DE, WORKBUF / LD BC, LINEREC / LDIR ; copy to work buffer (TPA)

Edit WORKBUF (flat TPA, no banking)

Write back:
  len_unchanged → LDIR WORKBUF → TXPAGE+offset (in-place patch)
  len_changed   → repack segment tail; update dir[N]; cascade dir[N+1..]
                  segment overflow → ALLSEG new segment, split
```

### File I/O

Load: BDOS open + sequential reads; split on CR/LF; feed into text segments;
build directory entries as we go; ALLSEG when segment fills.

Save: walk directory 0..TOTLINES-1; PUTP2 each segment; write line + LF to file.
One pass, no temporary file.

### Capacity

```
With 128KB RAM (typical MSX2), DOS2 leaves ~6 segments for text + 1 for dir:
  Text: 6 × 16KB = 96KB  →  at 40 chars/line average ≈ 1200 lines

With 256KB RAM (common expansion):
  ~14 free segments → ~224KB → ~2800 lines

Nextor systems often have 512KB or more mapped RAM.
```

## Build System

Follows MSX workspace convention:
- Assembler: `sjasmplus`
- Preprocessor: `gcc -E -P` for Z80 source
- Emulator target: `m2+`
- ROM format: TBD (MSX-DOS .COM or ROM cartridge)
