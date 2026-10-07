# SXED — Screen X Text Editor for MSX

**SXED** is a family of text editors for the MSX home computer architecture (MSX1, MSX2, MSX2+ and MSX turbo R), written in pure Z80 assembly language.

Designed for serious text editing directly on vintage hardware, SXED features a clean window and pull-down menu user interface, multi-level undo/redo, configurable word wrap, full Vi modal editing, and support for high-column text modes across different MSX video display processors (TMS9918A / V9938).

---

## The Editor Family

| Binary | Target Hardware | Display Mode | Geometry | Font & Styling |
|:---|:---|:---|:---|:---|
| **`S6ED.COM`** | MSX2 / 2+ / TR | Screen 6 ($512 \times 212$, 4 colors) | **80 cols $\times$ 24 rows** | 6×8 bitmap font with 4 dynamic weights (Normal, Bold, Italic, Bold-Italic). |
| **`S61ED.COM`** | MSX2 / 2+ / TR | Screen 6 ($512 \times 212$, 4 colors) | **61 cols $\times$ 24 rows** | 8×8 bitmap font with 4 dynamic weights, centered with a clean 16 px margin. |
| **`S2ED.COM`** | MSX1 / 2 / 2+ / TR | Screen 2 ($256 \times 192$, 16 colors) | **61 cols $\times$ 22 rows** | Dual-glyph 4×8 font in $8 \times 8$ cells, 16 TMS9918 colors with 4 customizable themes. |

---

## Key Features

- **Modern Window & Menu System:**
  - Pull-down menus (`F1`–`F5` or `ESC` hotkeys) with keyboard shortcuts and drop shadows.
  - Interactive modal dialogs with focusable widgets: **Go to Line**, **Find & Replace**, and **Settings**.
  - Built-in zero-extra-segment **File Browser** (Open / Save As) with drive and directory navigation.

- **Editing & Formatting:**
  - **Variable-length line storage** with automatic 16 KB mapper segment compaction.
  - Dynamic **Word Wrap** and paragraph reflow (`AUTOALIGN`).
  - Horizontal viewport panning (`LEFTCOL`) supporting lines up to 255 characters.
  - Markdown-like formatting markers (`*italic*`, `**bold**`, `***bold-italic***`) rendered in real time.
  - Full dead-key accent and international character arbitration (direct matrix polling with BIOS arbitration).

- **Multi-Level Undo & Redo:**
  - Circular undo ring buffer in TPA memory supporting granular typing and structural line edits.
  - Reliable state reconstruction across document edits.

- **Vi Modal Engine:**
  - Full modal editing with **Normal**, **Insert**, and **Visual** modes (`ESC` to normal, `i`, `a`, `o`, `v`, `V`).
  - Standard Vi motions: `h`, `j`, `k`, `l`, `w`, `b`, `e`, `0`, `$`, `gg`, `G`, etc.
  - Operators and actions: `d`, `y`, `p`, `x`, `r`, `c`, `u`, `CTRL-R`.
  - Ex command-line console (`:` prompt) supporting `:w`, `:q`, `:q!`, `:wq`, and line numbers.

- **Multiple Keymap Profiles:**
  - `STD`: Intuitive modern standard profile.
  - `TED`: WordStar-compatible cursor diamonds and shortcuts.
  - `EMC`: Emacs-style control chords (`Ctrl-F`, `Ctrl-B`, `Ctrl-P`, `Ctrl-N`, `Ctrl-A`, `Ctrl-E`, `Ctrl-K`, `Ctrl-Y`).

- **Color Themes & Typography:**
  - Customizable color palettes and shadow rendering (`DARK`, `GREEN`, `AMBER`, `MSX`).
  - Alternative 8×8 fonts for S61ED: `DEFAULT` (by Miguel A. Fernandez), `CGA`, `CPC`, `BIOS`.

---

## System Requirements

- **Operating System:** MSX-DOS 2.20+ or Nextor 2.1+.
- **Memory:** MSX Memory Mapper with at least one free 16 KB segment for text storage (4 segments recommended for larger files).
- **VDP:**
  - **S6ED** and **S61ED**: Yamaha V9938 / V9958 Video Display Processor (MSX2, MSX2+, or MSX turbo R) with 128 KB VRAM.
  - **S2ED**: Texas Instruments TMS9918A / TMS9928A / TMS9929A or Yamaha V9938 / V9958 with 16 KB VRAM (runs on standard MSX1).

---

## Documentation

- **User Manual (Markdown):** [`DOC/MANUAL.md`](DOC/MANUAL.md)  
  *Comprehensive online user manual with table of contents, full keystroke tables, command syntax, configuration reference (`SXED.CFG`), and troubleshooting.*
- **User Manual (MSX Text):** [`DOC/SXED.TXT`](DOC/SXED.TXT)  
  *Plain text 61-column reference manual, formatted for viewing directly on vintage MSX hardware inside SXED.*
- **System Architecture & Subsystems:** [`DEV/ARCHITECTURE.md`](DEV/ARCHITECTURE.md)  
  *Detailed engineering specs: multi-target drivers, memory maps, variable-length line records, window engine, and error handling.*
- **Font System & Custom Font Creation Guide:** [`DEV/FONTS.md`](DEV/FONTS.md)  
  *Font specifications (6×8, 8×8, 4×8), derivation tools, and step-by-step instructions for creating your own custom fonts.*

---

## Building from Source

The project builds using [sjasmplus](https://github.com/z00m128/sjasmplus) and standard GNU `make`.

```bash
cd CODE
make            # Builds S6ED.COM, S61ED.COM, S2ED.COM and data files
make check      # Runs static invariant quality gates (~0.2s)
```

Automated headless verification (requires [openMSX](https://openmsx.org/)):
```bash
make gate       # Runs headless openMSX regression test suite
make test-s61   # Runs S61ED computed-screen invariant test suite
make test-s2    # Runs S2ED MSX1 TMS9918 test suite
```

---

## Acknowledgments

- **Armando Pérez Abad** — Concept, architecture and programming.
- **Miguel A. Fernandez** — Hand-drawn 6×8, 8×8, and 4×8 bitmap fonts and testing.
- **Miguel Fides** — Technical support, ideas, and hardware insights.
- **Konamiman** — Nextor operating system.
- **VileR** — IBM CGA font conversion.
- **Amstrad** — Permission for CPC font redistribution.
- **The MSX Community** — For keeping the MSX platform vibrant and alive.
