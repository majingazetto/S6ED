# SXED System Architecture & Technical Specification

**SXED** (Screen X Text Editor) is a family of full-screen text editors written in pure Z80 assembly language for MSX computers running MSX-DOS 2 or Nextor.

This document details the unified system architecture, memory map, multi-segment mapper management, rendering engines, and error handling shared across all three targets (**S6ED**, **S61ED**, and **S2ED**).

---

## 1. The Multi-Target Model

SXED is structured around a shared core (`CODE/SRC/CORE/`) and target-specific drivers (`CODE/SRC/S6/`, `CODE/SRC/S61/`, `CODE/SRC/S2/`):

| Target | Display Processor | Mode | Visible Geometry | Cell & Font | VRAM Transfers |
|:---|:---|:---|:---|:---|:---|
| **S6ED** | Yamaha V9938 / V9958 | Screen 6 ($512 \times 212$, 4 col) | 80 cols $\times$ 24 rows | 6×8 glyph in 8×8 cell (cols 6–7 discarded) | VDP `LMMM` (char blit), `HMMM`/`YMMM` (scroll) |
| **S61ED** | Yamaha V9938 / V9958 | Screen 6 ($512 \times 212$, 4 col) | 61 cols $\times$ 24 rows | 8×8 glyph (byte-aligned, 16 px left margin) | VDP `HMMM` (byte-aligned blits & scroll) |
| **S2ED** | Texas Instruments TMS9918A / V9938 | Screen 2 ($256 \times 192$, 16 col) | 61 cols $\times$ 22 rows | 4×8 dual glyphs per $8 \times 8$ cell | Direct VRAM register writes via unrolled `OUTI; JP NZ` loops (29 T/byte) |

---

## 2. Logical Memory Map & Address Space

SXED executes as an MSX-DOS transient program (`.COM` entry at `#0100`). In the standard MSX-DOS 2 memory architecture, the 64 KB Z80 address space is organized into four 16 KB pages:

```
+-------------------------------------------------------+ #FFFF
| PAGE 3: System RAM & Unbanked Buffers (#C000 - #FFFF) |
| - MSX System Workspace & Interrupt Hooks (#F380-#FFFF)|
| - Main Stack (SP initialized from #0006, runs down)   |
| - Line Directory & Browser buffers (P3BASE / P3TOP)   |
| - Unbanked Line Buffers: WORKBUF (#C000), WORKBUF2,   |
|   PREVBUF (#C400), IOBUF (1 KB for disk streaming)    |
| - S2ED Window Save Buffer: WSVBUF (#C600 - #CBFF)     |
+-------------------------------------------------------+ #C000
| PAGE 2: Switched Mapper Window (#8000 - #BFFF)        |
| - Switched via MSX-DOS 2 Mapper Manager (MPUTP2)      |
| - Text Window (TXPAGE = #8000) for mapped text segs   |
| - Line Directory Window (DIRWIN = #8000) for DIRSEG   |
| - Feature Container Window (FTRBASE):                 |
|   * S6ED/S61ED: Full 16 KB (#8000-#BFFF) for S6ED.DAT |
|   * S2ED: VIDSEG shared partition (Shadows + S2ED.DAT)|
+-------------------------------------------------------+ #8000
| PAGE 1: TPA Executable & Dynamic Buffers (#4000-#7FFF)|
| - Executable Code (.COM loaded at #0100 spans into P1)|
| - Fixed Variables: VARS .. ENDVARS (#5777 .. #62AC)   |
| - Dynamic TPA Chain (never hardcoded addresses):      |
|   * UNDOBAS: Base of Undo Ring Buffer (UNDOSIZ)       |
|   * FONT4H (S2ED): 4x8 Font aligned to 256 bytes      |
|   * TPATOP <= #8000 (asserted below Page 2)           |
+-------------------------------------------------------+ #4000
| PAGE 0: MSX-DOS Kernel, TPA Base & BIOS (#0000-#3FFF) |
| - Base Page / Zero Page:                              |
|   * #0000: Warm boot jump                             |
|   * #0005: BDOS call entry vector                     |
|   * #0006: Top of available TPA RAM (BIOS word)       |
|   * #005C / #006C: Default FCBs                       |
|   * #0080: Command tail buffer & default DTA          |
| - Executable code image begins at #0100 (Page 0 TPA)  |
| - BIOS inter-slot access: CALSLT (#001C) & RDSLT      |
+-------------------------------------------------------+ #0000
```

### 2.1 Dynamic TPA Allocations (`tpa-chain`)
All resident buffers extending beyond the compiled variables chain dynamically off `ENDVARS`:
- `UNDOBAS`: Base of the circular multi-level undo/redo buffer in Page 1 RAM.
- `FONT4H` (S2ED): 2,048-byte high-nibble 4×8 font copy in TPA RAM (256-byte aligned).
- `TPATOP`: Top of allocated TPA RAM. The build statically enforces `ASSERT TPATOP <= TXPAGE (#8000)` to ensure zero overlap with the Page 2 banking window.

---

## 3. Mapper Management & Segment Partitioning

SXED uses the official MSX-DOS 2 / Nextor Extended BIOS mapper routines (`EXTBIO` with device ID `MAP_DEV`). Memory banking is strictly performed through the registered driver jump table:
- `ALL_SEG` (`MALLSEG`): Allocate a 16 KB mapper segment.
- `FRE_SEG` (`MFRESEG`): Free a 16 KB mapper segment.
- `PUT_P2` (`MPUTP2`): Bank a segment into Page 2 (`#8000-#BFFF`).
- `GET_P2` (`MGETP2`): Read the segment currently banked in Page 2.

Direct port I/O to mapper registers (`OUT (#FE), A`) is prohibited to guarantee full compatibility with internal mappers, external slot expanders, and Nextor drivers.

### 3.1 The Two-Segment Minimum & Mandatory Reservations
At startup, `SEGRESV` reserves the two mandatory system segments:
1. **`DIRSEG` (Line Directory Segment):** Banked into Page 2 on demand. Holds the line index directory (3 bytes per line: 1 byte segment ID, 2 bytes offset within text segment).
2. **`FTRSEG` (Feature Passenger Segment):** Holds the resident feature container loaded from disk (`.DAT` file), containing the configuration engine (`CFG`), window manager (`WINDOW`), dropdown menus (`MENU`), and file browser (`BROWSE`).

### 3.2 S6ED / S61ED vs. S2ED Page 2 Partitioning
Because Screen 6 hardware has dedicated VRAM for display, composition, and font tables, **S6ED and S61ED allocate the entire 16 KB Page 2 window to the feature container** (`FTRBASE = #8000`, `FTRTOP = #C000`).

In contrast, **S2ED runs on MSX1 machines where VDP hardware commands do not exist and a stock 128 KB machine has exactly 0 spare segments** (`SEGAVL = 0` after `DIRSEG` and `FTRSEG`). Consequently, **`VIDSEG` and `FTRSEG` are the exact same 16 KB mapper segment**, partitioned as follows:

```
+---------------------------------------------------------------+ #C000
| FTRBASE (#9C00 - #BFFF): S2ED Feature Container (5,120 bytes)  |
| - CFG.Z8A, WINDOW.Z8A, MENU.Z8A, BROWSE.Z8A, BROWSER.Z8A      |
+---------------------------------------------------------------+ #9C00
| COLEXP  (#9B00 - #9BFF): Row color staging buffer (256 bytes) |
+---------------------------------------------------------------+ #9B00
| COLMAP  (#9800 - #9AFF): Color shadow map (768 bytes, 1B/cell)|
+---------------------------------------------------------------+ #9800
| PATSHAD (#8000 - #97FF): Pattern shadow buffer (6,144 bytes)  |
| - 24 rows x 32 cells x 8 bytes (256 bytes per screen row)     |
+---------------------------------------------------------------+ #8000
```
- **The 1-Byte/Cell Optimization:** TMS9918 Screen 2 requires 6,144 bytes of color table (8 bytes per cell). By storing only 1 byte per cell in RAM (768 bytes), 5,376 bytes are freed to host `FTRBASE`. On VRAM dump, `COLDMPC` dynamically expands the cell byte 8 times into `COLEXP` on the fly.
- **Window Save Buffer (`WSVBUF`):** To avoid competing with the tight `FTRBASE` budget in Page 2 or TPA in Page 1, `WSVBUF` (1,536 bytes) is placed in unbanked Page 3 RAM at `#C600`.

---

## 4. Document Storage & Segment Compactor

Text is stored in dynamically allocated 16 KB mapper segments (`TXPAGE = #8000`).

### 4.1 Variable-Length Line Storage
Lines are stored as variable-length records:
- `LEN` (1 byte): Number of text characters ($0 \dots 255$).
- `TEXT` ($N$ bytes): Raw character codes.
- `ATTR` ($N$ bytes): Corresponding character markup / attribute bits (Bold, Italic, Markup markers).
- Maximum record size: `LINEREC = 1 + TEXTCOLS + TEXTCOLS` (161 bytes on S6ED, 123 bytes on S61ED and S2ED).

### 4.2 Segment Compactor
When insertions or edits exhaust contiguous space in a segment:
1. Inactive or deleted line records are compacted in-place.
2. Active records are shifted towards the segment base.
3. If the compacted segment cannot accommodate the new record, a new 16 KB segment is allocated via `ALLSEG` and registered in `DIRSEG`.

### 4.3 Universal Horizontal Viewport (`LEFTCOL`)
Editing lines wider than the screen (up to 255 columns) is handled by the horizontal viewport engine:
- `LEFTCOL` maintains the horizontal scroll offset.
- Cursor motion past the right screen margin adjusts `LEFTCOL` and triggers an incremental line repaint or full window blit.

---

## 5. Window & Menu Subsystem

SXED provides a modal window and pull-down menu engine:

### 5.1 Window Canvas & Shadows (`WBOX`, `WSHADOW`)
- Window geometries are defined in cell coordinates `(X, Y, W, H)`.
- Prior to displaying a modal window or menu, underlying canvas data and attributes are saved into `WSVBUF`.
- Windows render borders, titles, and a 1-character/4-pixel drop shadow along the right and bottom edges.
- `WINKIL` restores the backing canvas from `WSVBUF` instantly without re-reading or re-rendering document lines.

### 5.2 Interactive Widgets (`WINEDIT`)
Modal dialogs (**Go to Line**, **Find & Replace**, **Settings**) use standard focusable controls:
- Single-line editable text and numeric fields (`ED_DIGIT`, `ED_TEXT`, `ED_FILE`).
- Three-position focus cycling: Input Field $\leftrightarrow$ OK button $\leftrightarrow$ CANCEL button.
- Clean ESC cancellation and ENTER execution.

---

## 6. File Browser Subsystem

The built-in file browser (`CORE/BROWSE.Z8A`):
- Operates with **zero extra mapper segments** by utilizing unbanked Page 3 scratch memory (`BRWPATH`, `BRWFIB`, `BRWTTL`, `BRWINF`).
- Scans directory contents using MSX-DOS 2 `_FFIRST` (`#40`) and `_FNEXT` (`#41`).
- Enumerates available drives via `_LOGIN` (`#68`).
- Displays a multi-column navigable grid with path editing and file metadata formatting.

---

## 7. MSX-DOS 2 & Nextor Disk Error Architecture

To ensure physical disk errors (unformatted media, write-protect, drive not ready) do not trigger kernel console abort prompts (`"Abort, Retry, Ignore?"`) that corrupt graphical canvas modes:

- **Handler Registration:**
  - `DSKINIT`: Registers user disk error routine (`_DEFER`, `#64`) pointing to `DSKERRH`, and user abort routine (`_DEFAB`, `#63`) pointing to `DSKABTH`, conditional on `(DOS2) != 0`.
  - `DSKRST`: Unregisters handlers (`DE = 0`) before exiting via `TERM`.
- **Abort Capture:**
  - `DSKERRH` captures the primary error code in `(DSKERR)` and physical drive in `(DSKDRV)`, returning `A = 1` (Abort).
  - `DSKABTH` intercepts `.ABORT` (`ERRABT` = `#9D`), discards the DOS kernel return address with `POP HL`, sets Carry flag (`CY = 1`), loads `A` with the error code, and returns directly to the application layer.
- **Application Safety:**
  - Failed operations close file handles cleanly and report `[SAVE ERROR]` or `[CANNOT OPEN]` on the status bar without crashing the editor.

---

## 8. Multi-Level Undo / Redo

- **Location:** Circular ring buffer in Page 1 TPA RAM (`UNDOBAS .. UNDOTOP`).
- **Operation:** Records atomic insertion bursts, deletions, splits, joins, and block replacements.
- **State Integrity:** Restores exact document state and cursor coordinates across arbitrary edit sequences.
