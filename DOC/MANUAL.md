# SXED User Manual & Reference Guide

**SXED Screen X Text Editor v0.1**  
*(c) 2024 - 2026 Armando Pérez Abad*  
*Fonts by Miguel A. Fernandez*

---

## Table of Contents

- [1.- INTRODUCTION / AIM.](#1-introduction-aim)
- [2.- THE EDITORS.](#2-the-editors)
- [3.- REQUIREMENTS & FILES.](#3-requirements-files)
- [4.- STARTING THE EDITOR.](#4-starting-the-editor)
- [5.- THE SCREEN.](#5-the-screen)
- [6.- BASIC EDITING.](#6-basic-editing)
  - [6.1.- MOVING THE CURSOR.](#6-1-moving-the-cursor)
  - [6.2.- INSERT, DELETE & LINES.](#6-2-insert-delete-lines)
  - [6.3.- TABS.](#6-3-tabs)
  - [6.4.- WORD WRAP & TEXT WIDTH.](#6-4-word-wrap-text-width)
  - [6.5.- AUTOALIGN.](#6-5-autoalign)
  - [6.6.- ACCENTS & DEAD KEYS.](#6-6-accents-dead-keys)
  - [6.7.- MARKUP.](#6-7-markup)
- [7.- KEYMAP PROFILES.](#7-keymap-profiles)
  - [7.1.- STANDARD PROFILE (STD).](#7-1-standard-profile-std)
  - [7.2.- TED PROFILE (TED).](#7-2-ted-profile-ted)
  - [7.3.- EMACS PROFILE (EMC).](#7-3-emacs-profile-emc)
- [8.- VI MODE.](#8-vi-mode)
  - [8.1.- NORMAL MODE.](#8-1-normal-mode)
  - [8.2.- INSERT MODE.](#8-2-insert-mode)
  - [8.3.- VISUAL MODE.](#8-3-visual-mode)
  - [8.4.- EX COMMANDS.](#8-4-ex-commands)
- [9.- SELECTION, CLIPBOARD & UNDO.](#9-selection-clipboard-undo)
- [10.- MENUS & DIALOGS.](#10-menus-dialogs)
  - [10.1.- THE MENU BAR.](#10-1-the-menu-bar)
  - [10.2.- FILE MENU.](#10-2-file-menu)
  - [10.3.- EDIT MENU.](#10-3-edit-menu)
  - [10.4.- HELP MENU.](#10-4-help-menu)
  - [10.5.- FILE BROWSER (OPEN / SAVE AS).](#10-5-file-browser-open-save-as)
  - [10.6.- GO TO LINE.](#10-6-go-to-line)
  - [10.7.- FIND & REPLACE.](#10-7-find-replace)
  - [10.8.- SETTINGS.](#10-8-settings)
  - [10.9.- CONFIRMATION DIALOGS.](#10-9-confirmation-dialogs)
  - [10.10.- ABOUT.](#10-10-about)
- [11.- CONFIGURATION FILE.](#11-configuration-file)
- [12.- THEMES.](#12-themes)
- [13.- FONTS.](#13-fonts)
- [14.- FILES & DISK.](#14-files-disk)
- [15.- TROUBLESHOOTING.](#15-troubleshooting)
- [16.- THANKS.](#16-thanks)

---

## 1.- INTRODUCTION / AIM

SXED is a family of full screen text editors for MSX computers running MSX-DOS 2 or Nextor.

Why another text editor? Because we wanted a modern editor on real MSX hardware: pull-down menus, dialogs, mouse-free fast keyboard control, multiple keymap profiles (including a real modal Vi), undo/redo, word wrap, themes, accented characters, and a file browser. All of it fast enough to be pleasant on a stock 3.58 MHz machine.

SXED is one program built three times, for two video chips. The three editors share the same core: same features, same menus, same keymaps, same configuration keys and same file formats. Learn one and you know the others.

This manual is 61 columns wide on purpose: you can read it with any of the editors themselves, without horizontal scrolling.

## 2.- THE EDITORS

The SXED family has three members:

- S6ED - Screen 6 editor for MSX2/2+/turbo-R (V9938/V9958).

- SCREEN 6 bitmap: 512x212 pixels, 4 colors.
- 80 columns x 24 rows of text.
- Hand-drawn 6x8 font with 4 weights: normal, bold, italic and bold+italic (used by the markup engine).
- 6 color themes plus fully custom colors.
- Program: S6ED.COM

- S61ED - Screen 6 editor for MSX2/2+/turbo-R, big type.

- SCREEN 6 bitmap: 512x212 pixels, 4 colors.
- 61 columns x 24 rows of text, 8x8 character cells.
- For those who prefer big characters over wide lines: every cell is byte aligned, so it is also the fastest of the three at drawing text.
- Hand-drawn 8x8 font with the same 4 weights; the IBM CGA, Amstrad CPC and MSX BIOS faces come along as alternatives (see 13).
- The same 6 color themes and custom colors as S6ED.
- Program: S61ED.COM

- S2ED - Screen 2 editor for MSX1/2/2+/turbo-R (TMS9918).

- SCREEN 2 driven as a bitmap: 256x192, 16 fixed colors.
- 61 columns x 22 rows of text (plus menu/status bars).
- Hand-drawn 4x8 font, two characters per 8x8 cell.
- 6 color themes mapping the 16 TMS9918 colors.
- Program: S2ED.COM

Everything in this manual applies to all three editors unless a note says otherwise. Differences (screen geometry, themes, color configuration) are marked with [S6ED], [S61ED] or [S2ED]. S6ED and S61ED share the Screen 6 hardware, so most of those notes read [S6ED/S61ED].

## 3.- REQUIREMENTS & FILES

Minimum requirements (all editors):

- MSX-DOS 2 or Nextor (plain MSX-DOS 1 is rejected).
- A memory mapper with the standard mapper support routines (any MSX-DOS 2 / Nextor system has them).
- At least 2 free 16 KB mapper segments.

Notes per editor:

- [S6ED/S61ED] need an MSX2 or higher. On a 128 KB machine they run under MSX-DOS 2 (101 lines of text capacity on S6ED, 133 on S61ED) but NOT under Nextor, which reserves one segment more; with Nextor use 256 KB or more. More mapper memory means bigger documents (up to 5461 lines).
- [S2ED] runs on MSX1. MSX-DOS 2 does not run on MSX1, so on MSX1 you need Nextor (a 128 KB mapper machine with a disk interface works fine).

Each editor is made of four files, named after it (S6ED.*, S61ED.* or S2ED.*):

| Key / Command | Description |
|:---|:---|
| `.COM` | The program. |
| `.DAT` | Feature container. MANDATORY: the editor aborts |
| `` | if it is missing or corrupt. |
| `.FNT` | Font file. Optional: if missing or of the wrong |
| `` | size, the MSX ROM charset is used instead |
| `` | ([S6ED/S61ED] show [ROM] on the status bar). |
| `.CFG` | Configuration. Optional (defaults are used if |
| `` | absent). See 11. |

The editor finds its files "next to the program": when COMMAND2.COM runs the editor (even through PATH) it tells it the full path it was found at, and .DAT, .FNT and the general .CFG are searched there first, falling back to the current directory. You can keep the editors in A:\TOOLS and run them from anywhere. See 11 for the local .CFG override.

Three disk images are distributed, all laid out the same way: the editors in A:\TOOLS, this manual and a sample document in A:\DEV, and an AUTOEXEC.BAT that sets the PATH, changes to \DEV and starts an editor.

| Key / Command | Description |
|:---|:---|
| `S6ED.DSK` | MSX2. Carries all three editors and starts |
| `` | S6ED. Run the others from \DEV with |
| `` | "S61ED TEST_S61.TXT" or "S2ED TEST_S2.TXT". |
| `S61ED.DSK` | MSX2. S61ED alone. |
| `S2ED.DSK` | MSX1 (Nextor) or MSX2. S2ED alone. |

The MSX2 disks also carry S61ED's example fonts in A:\TOOLS\FONTS (see 13).

## 4.- STARTING THE EDITOR

Usage:

```text
S6ED  [file] [/V] [/H | /?]
S61ED [file] [/V] [/H | /?]
S2ED  [file] [/V] [/H | /?]
```

| Key / Command | Description |
|:---|:---|
| `file` | File to open. Full DOS 2 paths are allowed |
| `` | (A:\DIR\FILE.TXT, up to 63 characters). If the |
| `` | file does not exist a new empty document is |
| `` | created under that name ([NEW FILE]). |
| `/V` | Verbose boot: shows mapper memory, reserved |
| `` | segments and text capacity, and waits for a key. |
| `` | /H, /?  Shows a short help and exits to DOS. |

With no parameters the editor starts with an empty document.

The boot process checks the machine BEFORE entering graphics mode and aborts with a clear message if something is missing:

```text
Requires MSX-DOS 2 or Nextor.
No mapper manager found.
Insufficient Page 3 memory.
S6ED requires 2 free mapper segments.
Out of mapper memory.
S6ED.DAT not found.   /   S6ED.DAT corrupt.
```

(with S61ED or S2ED in place of S6ED for the other editors).

While editing, use ESC or Ctrl+Q to leave the editor. If the document has unsaved changes a confirmation dialog appears first (see 10.9). Everything is restored on exit: screen mode, colors, palette, function keys and keyboard click.

## 5.- THE SCREEN

The screen has three areas:

```text
Row 0        Menu bar: program name, the File/Edit/Help
             menus, the current file name and the clock.
Text area    [S6ED]  24 rows x 80 columns.
             [S61ED] 24 rows x 61 columns.
             [S2ED]  22 rows x 61 columns.
Last row     Status bar.
```

The menu bar shows the base name of the current file (up to 20 characters) right-aligned, followed by " *" while the document has unsaved changes ("Untitled *" if it has no name yet). At the far right, the HH:MM clock read from the DOS real time clock; its colon blinks once per second. The clock hides while a dialog is open and can be turned off in Settings.

The status bar has two channels:

- Left: ephemeral messages ([SAVED], [SAVE ERROR], [NEW FILE], [CANNOT OPEN], [FILE TOO LARGE], [ROM]...). In Vi mode this is also the ":" command line. Messages disappear with the next keystroke. While the disk is busy it says so: loading and saving show a progress bar with a percentage, and "Reading directory..." shows while the file browser scans.
- Right: a mode tag and the cursor position:

```text
    [INS]   insert mode        [OVR]   overwrite mode
    [SEL]   selection active
    [NORM]  Vi normal mode     [VIS]   Vi visual mode
```

```text
    Ln NNNNN/NNNNN  Col NNN    (S6ED)
    Ln NNNNN/NNNNN Col NNN     (S61ED, S2ED)
```

```text
  Line and column numbers are 1-based; the second figure
  is the total line count.
```

## 6.- BASIC EDITING

### 6.1.- MOVING THE CURSOR

These keys work the same in the STD, TED and EMC profiles (Vi has its own set, see 8):

| Key / Command | Description |
|:---|:---|
| `Left / Right` | One character left / right |
| `Up / Down` | One line up / down |
| `Ctrl+Left/Right` | Beginning / end of line |
| `Ctrl+Up / Ctrl+Down` | Top / bottom of the document |
| `GRAPH+Left/Right` | One word left / right |
| `` | GRAPH+Up / GRAPH+Down One page up / down |

Lines can be up to 255 characters long. When the cursor moves past the right edge the window scrolls horizontally in 8 column steps, so long lines are never cut.

In WRAP=TXT mode (see 6.4) moving right past the end of a line jumps to the start of the next one, and moving left at column 1 jumps to the end of the previous one.

### 6.2.- INSERT, DELETE & LINES

| Key / Command | Description |
|:---|:---|
| `INSERT` | Toggles insert / overwrite mode ([INS]/[OVR]). |
| `RETURN` | Splits the line at the cursor. |
| `BS` | Deletes the character before the cursor; at |
| `` | column 1 it joins the line with the previous. |
| `DEL` | Deletes the character under the cursor; at the |
| `` | end of line it pulls the next line up. |

Deleting a selection, typing over it or pasting over it works as expected: the selected text is replaced (see 9).

### 6.3.- TABS

TAB inserts spaces up to the next tab stop (soft tabs: real spaces are stored, never a TAB character). The tab width is 2, 4 or 8 (Settings or TABWIDTH=, default 4).

When a file containing raw TAB characters is loaded they are expanded to spaces at the configured width. They are not converted back on save.

### 6.4.- WORD WRAP & TEXT WIDTH

Two wrap modes, toggled with Ctrl+W or WRAP= in the CFG:

```text
WRAP=DEV   Developer mode (default): no wrapping, lines
           grow up to 255 columns with horizontal scroll.
           Thought for source code: lines are never
           broken for you.
WRAP=TXT   Text mode: typing past the right margin pushes
           the last word to the next line (word wrap),
           and deleting pulls words back up (reflow).
```

The margin is the text width: the screen width by default (80 / 61 / 61) or the TEXTWIDTH= value (0 = no margin, i.e. DEV mode). In Vi mode: ":set wrap", ":set nowrap", ":set tw=N".

### 6.5.- AUTOALIGN

AUTOALIGN (OFF by default, or AUTOALIGN=ON / DEV) is an assembly layout aid: pressing RETURN at the end of a line places the cursor of the new line under the first token of the line just split (the mnemonic column), so

```text
LABEL   LD  A,10
        JP  SUBRT
```

chains naturally without typing spaces. Nothing is written until you type: blank lines stay blank. DEV means "only when WRAP=DEV".

### 6.6.- ACCENTS & DEAD KEYS

Spanish accented characters work in every profile, on any regional machine, via the GRAPH key:

| Key / Command | Description |
|:---|:---|
| `GRAPH+A/E/I/O/U` | Ã¡ Ã© Ã­ Ã³ Ãº |
| `GRAPH+N` | Ã± |
| `GRAPH+W` | Ã¼ |
| `GRAPH+1` | Â¡ |
| `GRAPH+?` | Â¿ |

SHIFT only changes N, E and W: Ã, Ã and Ã (the MSX charset has no other uppercase accented vowels).

Dead keys: pressing the accent dead key (the acute accent key on European keyboards; KANA/CODE on Japanese ones) and then a vowel produces the acute vowel; SHIFT+dead key arms the diaeresis (Ã¼). Dead key + space types the quote itself. ESC or BS cancels a pending dead key.

On Japanese machines the editor keeps the KANA lock permanently suppressed and the KANA LED off, so KANA can always be used as the dead key.

### 6.7.- MARKUP

The markup engine (MARKUP=OFF / MD / LIT, default MD) colors or re-weights styled spans without modifying the file:

```text
MD   CommonMark:  **bold**  *italic*  _italic_
LIT  Chat style:  *bold*  _italic_
OFF  Raw text (best for source code).
```

[S6ED/S61ED] render bold/italic with the font weights; [S2ED] renders them in theme colors. Ctrl+T cycles the mode. Ctrl+B / Ctrl+I (STD profile) insert a delimiter pair or wrap the current selection.

## 7.- KEYMAP PROFILES

Four keyboard profiles are built in. Ctrl+K cycles them (STD -> TED -> EMC -> VI), the Settings dialog selects one, and PROFILE= sets it in the CFG. The active profile is remembered when you save Settings.

The full tables follow. Unless noted, "the editor" means all three editors. In all profiles any unmapped printable key is typed into the document (in Vi, only in insert mode).

Common to ALL profiles:

| Key / Command | Description |
|:---|:---|
| `F1 / SELECT / F10` | Open the File menu |
| `F2` | Open the Edit menu |
| `F3 / F4 / F5` | Open the Help menu (there are only |
| `` | three menus) |
| `RETURN` | New line / split line |
| `TAB` | Insert to next tab stop |
| `BS / DEL` | Delete backward / forward |
| `INSERT` | Toggle insert / overwrite |
| `Ctrl+K` | Cycle keymap profile |
| `Ctrl+G` | Go to line... |
| `Ctrl+S` | Save |
| `Ctrl+Q / ESC` | Quit (ESC first drops a selection) |

### 7.1.- STANDARD PROFILE (STD)

Classic CUA-style editing (the default):

| Key / Command | Description |
|:---|:---|
| `Left/Right/Up/Down` | Move cursor |
| `Ctrl+Left / Ctrl+Right` | Beginning / end of line |
| `Ctrl+Up / Ctrl+Down` | Top / bottom of document |
| `GRAPH+Left/Right` | Word left / right |
| `GRAPH+Up / GRAPH+Down` | Page up / down |
| `` | Shift+Left/Right/Up/Down Extend selection |
| `Shift+Ctrl+Left/Right` | Select to line start / end |
| `Shift+Ctrl+Up/Down` | Select to doc top / bottom |
| `Shift+GRAPH+Left/Right` | Select word left / right |
| `Shift+GRAPH+Up/Down` | Select page up / down |
| `Ctrl+A` | Select all |
| `` | Ctrl+X / Ctrl+C / Ctrl+V Cut / copy / paste |
| `Ctrl+Y` | Delete current line |
| `GRAPH+BS` | Delete word left |
| `Ctrl+F` | Find & replace... |
| `Ctrl+L / Ctrl+R` | Find next / previous |
| `Ctrl+N` | New document |
| `Ctrl+O` | Open... (file browser) |
| `Ctrl+Shift+S` | Save as... (file browser) |
| `Ctrl+B / Ctrl+I` | Bold / italic delimiters |
| `Ctrl+T` | Cycle markup mode |
| `Ctrl+W` | Toggle wrap mode |
| `Ctrl+Z / Ctrl+Shift+Z` | Undo / redo |
| `ESC` | Cancel selection, else quit |

### 7.2.- TED PROFILE (TED)

Compatible with the classic MSX TED 2.6 editor. Note: in TED Shift+cursor is word/page navigation; selection uses Shift+Ctrl or Shift+GRAPH:

| Key / Command | Description |
|:---|:---|
| `Left/Right/Up/Down` | Move cursor |
| `` | Shift+Left / Shift+Right Word left / right |
| `Shift+Up / Shift+Down` | Page up / down |
| `Ctrl+Left / Ctrl+Right` | Beginning / end of line |
| `Ctrl+Up / Ctrl+Down` | Page up / down |
| `GRAPH+Left/Right` | Word left / right |
| `GRAPH+Up / GRAPH+Down` | Page up / down |
| `Shift+Ctrl+Left/Right` | Select to line start / end |
| `Shift+Ctrl+Up/Down` | Select to doc top / bottom |
| `Shift+GRAPH+Left/Right` | Select word left / right |
| `Shift+GRAPH+Up/Down` | Select page up / down |
| `Ctrl+A` | Select all |
| `` | Ctrl+X / Ctrl+C / Ctrl+V Cut / copy / paste |
| `Ctrl+Y / Ctrl+DEL` | Delete current line |
| `GRAPH+BS` | Delete word left |
| `Ctrl+Z` | Find & replace... |
| `Ctrl+N` | Find next |
| `Ctrl+G` | Go to line... |
| `Ctrl+T / Ctrl+O` | Top / bottom of document |
| `Ctrl+B / Ctrl+S` | Save |
| `Ctrl+Shift+S` | Save as... |
| `Ctrl+L` | Open... (file browser) |
| `Ctrl+U / Ctrl+Shift+U` | Undo / redo |
| `ESC` | Cancel selection, else quit |

### 7.3.- EMACS PROFILE (EMC)

Basic Emacs-style control keys plus the standard cursor block:

| Key / Command | Description |
|:---|:---|
| `Ctrl+B / Ctrl+F` | Cursor left / right |
| `Ctrl+P / Ctrl+N` | Previous / next line |
| `Ctrl+A / Ctrl+E` | Beginning / end of line |
| `Ctrl+D` | Delete character forward |
| `Ctrl+Y` | Kill current line |
| `Left/Right/Up/Down` | Move cursor |
| `Ctrl+Left / Ctrl+Right` | Beginning / end of line |
| `Ctrl+Up / Ctrl+Down` | Top / bottom of document |
| `GRAPH+Left/Right` | Word left / right |
| `GRAPH+Up / GRAPH+Down` | Page up / down |
| `GRAPH+BS` | Delete word left |
| `Ctrl+T` | Cycle markup mode |
| `Ctrl+W` | Toggle wrap mode |
| `Ctrl+Z / Ctrl+Shift+Z` | Undo / redo |
| `ESC` | Cancel selection, else quit |

The VI profile is a modal world of its own: see chapter 8.

## 8.- VI MODE

The VI profile is a real modal editor: Normal mode for moving and commands, Insert mode for typing, Visual mode for selecting. The status bar shows [NORM], [INS] or [VIS].

### 8.1.- NORMAL MODE

Movement:

| Key / Command | Description |
|:---|:---|
| `h / j / k / l` | Left / down / up / right |
| `Cursor keys` | Also move |
| `w / b` | Word forward / backward |
| `0 or ^ / $` | Beginning / end of line |
| `gg` | Top of document |
| `G` | Bottom of document |
| `Ctrl+F / Ctrl+D` | Page down |
| `Ctrl+B / Ctrl+U` | Page up |
| `Ctrl+Left/Right` | Beginning / end of line |
| `Ctrl+Up/Down` | Top / bottom of document |

Entering Insert mode:

```text
i    Insert at cursor        I  Insert at line start
a    Append after cursor     A  Append at end of line
o    Open line below         O  Open line above
```

Editing:

```text
x / X                    Delete char under / before
dd                       Delete current line
D                        Delete to end of line
p                        Paste clipboard
u / Ctrl+R               Undo / redo
```

Selection and search:

```text
v    Visual (charwise)     V  Visual (linewise)
/    Find & replace...     n / N  Find next / previous
```

Miscellaneous:

```text
:    Ex command line (see 8.4)
Ctrl+G  Go to line...    Ctrl+S  Save    Ctrl+Q  Quit
Ctrl+K  Cycle profile    Ctrl+T  Cycle markup mode
```

Leader sequences: after "d" or "g" the editor waits for the next key ("dd", "gg"). Any other key cancels the leader and is processed normally.

### 8.2.- INSERT MODE

ESC returns to Normal mode. While inserting:

```text
Cursor keys              Move (staying in Insert)
RETURN / TAB / BS / DEL  As usual
Ctrl+B / Ctrl+I          Bold / italic delimiters
Ctrl+T                   Cycle markup mode
Any printable key        Typed into the document
```

### 8.3.- VISUAL MODE

v starts a characterwise selection, V selects whole lines: however the cursor moves, every line it covers is selected from its first character to its line break. v and V switch between the two (the same key again leaves visual mode). Movements extend the selection instead of moving the cursor:

```text
h / j / k / l            Extend left/down/up/right
w / b                    Extend word forward/backward
0 or ^ / $               Extend to line start / end
gg / G                   Extend to doc top / bottom
Ctrl+F / Ctrl+D          Extend one page down
Ctrl+B / Ctrl+U          Extend one page up
Cursor keys              Also extend
y                        Yank (copy), back to Normal
d / x                    Cut, back to Normal
ESC                      Cancel, back to Normal
```

### 8.4.- EX COMMANDS

":" opens a command line on the status bar (BS edits, BS on an empty line or ESC cancels). Commands are case insensitive:

| Key / Command | Description |
|:---|:---|
| `:w` | Save |
| `:w <name>` | Save under a new name |
| `:wq  or  :x` | Save and quit |
| `:q` | Quit (refused with unsaved changes) |
| `:q!` | Quit discarding changes |
| `:e` | Open the file browser |
| `:e <name>` | Load file (refused if modified) |
| `:e! <name>` | Load file discarding changes |
| `:e!` | Reload the current file from disk |
| `:<number>` | Go to that line |
| `:set wrap` | Smart word wrap on |
| `:set nowrap` | Wrap off |
| `:set tw=N` | Set text width (0 = no wrap) |
| `:set textwidth=N` | Same as tw=N |

## 9.- SELECTION, CLIPBOARD & UNDO

Selection: Shift+cursor keys (STD), Shift+Ctrl / Shift+GRAPH combos (STD and TED), or Visual mode (VI). Ctrl+A selects the whole document; Edit > Deselect (or ESC in STD) drops the selection. Typing, pasting or RETURN over a selection replaces it.

Clipboard: Ctrl+X cut, Ctrl+C copy, Ctrl+V paste (Vi: d/x, y, p). Multi-line selections copy and paste whole lines with their line breaks. In Vi visual mode a selection that reaches the end of a line with $ takes its line break too, and V always takes whole lines with their breaks, so pasting either opens a new line.

Undo/redo:

| Key / Command | Description |
|:---|:---|
| `` | STD / EMC:  Ctrl+Z undo, Ctrl+Shift+Z redo |
| `TED:` | Ctrl+U undo, Ctrl+Shift+U redo |
| `VI:` | u undo, Ctrl+R redo |

Undo covers typing (a continuous run of edits on one line is ONE undo step), line split/join/delete, word delete, paste, selection edits and replace: a whole Replace All reverts with a single undo. Each undo also restores the cursor position and the viewport. A new edit invalidates the redo chain.

The undo history lives in a 4 KB ring (about 23 operations on S6ED, 30 on S61ED and S2ED); the oldest operations are forgotten as it fills. A single operation touching more lines than the ring can hold (a huge selection delete, for example) cannot be recorded half-way: then the whole history is dropped instead of restoring a partial, wrong state.

## 10.- MENUS & DIALOGS

### 10.1.- THE MENU BAR

F1, F2 (and F3/F4/F5), SELECT or F10 open the menus; the active menu title is highlighted on row 0. Inside a menu:

```text
Left / Right     Switch to the previous / next menu
Up / Down        Move over the items (skips separators)
RETURN / SPACE   Execute the selected item
Letter keys      Accelerators (shown by the items)
ESC / SELECT     Close the menu
```

The three menus are File, Edit and Help.

### 10.2.- FILE MENU

```text
New          Ctrl+N   New document (asks if modified)
Open...      Ctrl+O   File browser in open mode
Save         Ctrl+S   Save the document
Save As...            File browser in save mode
----
Quit         Ctrl+Q   Exit to DOS (asks if modified)
```

### 10.3.- EDIT MENU

```text
Cut          Ctrl+X   Cut selection to clipboard
Copy         Ctrl+C   Copy selection to clipboard
Paste        Ctrl+V   Paste clipboard
Delete Line  Ctrl+Y   Delete the current line
----
Select All   Ctrl+A   Select the whole document
Deselect              Drop the selection
----
Go to Line...Ctrl+G   Jump to a line number
Find...      Ctrl+F   Find & replace dialog
```

### 10.4.- HELP MENU

```text
Settings...  (S)      The settings dialog (see 10.8)
Help...               Reserved
----
About...     (A)      Version and build information
```

### 10.5.- FILE BROWSER (OPEN / SAVE AS)

The browser shows the files of a directory as a grid (5x14 slots on S6ED, 4x12 on S61ED and S2ED), sorted: "..", then directories, then files, then drives, each group in alphabetical order. Hidden and system files are shown in a different style. The information line under the grid shows name, size (or <DIR>), date, time and attributes of the selected entry, plus the entry count (N+/MAX if the directory has more entries than the browser holds: 160 on S6ED and S61ED, 64 on S2ED).

The starting directory is the current file's directory when known, or the current directory.

In the grid:

| Key / Command | Description |
|:---|:---|
| `Arrow keys` | Move the selection (scrolls as needed) |
| `` | Letter/digit  Jump to the next entry starting with it |
| `` | RETURN/SPACE  Open a file, enter a directory, select a |
| `` | drive or go to the parent with ".." |
| `BS` | Go up one directory |
| `TAB` | Cycle focus: list -> Name field -> |
| `` | [Open]/[Save] -> [Cancel] |
| `ESC` | Cancel |

In the Name field (38 chars) you can type:

```text
A name        Selects that file (relative to the shown
              directory)
With * or ?   Changes the file mask
Ending in \   Changes to that directory
D:\PATH       An absolute path with drive
```

In Save As mode the field starts with the current file name and the focus is on the field. If the target file exists, an "Overwrite file?" dialog asks first; answering No returns to the browser exactly as you left it.

### 10.6.- GO TO LINE

Ctrl+G (or Edit > Go to Line) opens a small dialog asking "Line number (1-N):". Digits type, BS deletes, ENTER accepts (empty cancels), ESC cancels, and TAB/arrows move between the field and the [OK]/[Cancel] buttons. Out of range numbers are clamped; the view is centered on the target line (or left untouched if the line is already visible).

### 10.7.- FIND & REPLACE

Ctrl+F (or Edit > Find, "/" in Vi) opens the Find & Replace dialog:

| Key / Command | Description |
|:---|:---|
| `Find:` | Text to search (up to 18 characters) |
| `Replace:` | Replacement text |
| `Match case:` | [X] case sensitive; default is case |
| `` | insensitive |
| `[ Find ]` | Find next match |
| `[ Repl ]` | Replace the current match and find next |
| `[ All  ]` | Replace all matches in the document |
| `[Cancel]` | Close |

TAB/Down move forward through fields and buttons, Up moves back, Left/Right move between buttons, SPACE toggles the checkbox or activates a button, and ENTER in a text field finds the next match immediately. ESC closes the dialog.

A found match becomes the current selection. The search wraps around the document; when there is no match the machine beeps. Ctrl+L / Ctrl+R (STD), n / N (Vi) repeat the last search forwards / backwards. Replace All is a single undo group: one undo reverts every replacement.

### 10.8.- SETTINGS

Help > Settings (accelerator S) edits all the options in one dialog:

| Key / Command | Description |
|:---|:---|
| `Profile` | STD / TED / EMC / VI |
| `Wrap` | DEV / TXT |
| `Autoalign` | OFF / ON / DEV |
| `Clock` | OFF / ON |
| `Tab width` | 2 / 4 / 8 |
| `EOL` | AUTO / DOS / UNIX |
| `Markup` | OFF / MD / LIT |
| `Theme` | DARK / AMBER / GREEN / LIGHT / MSX / MONO |
| `Shadow` | OFF / ON     (window drop shadows) |

Up/Down choose the option, Left/Right/SPACE cycle its value, and the [ OK ] / [Cancel] buttons are at the bottom. Nothing is changed until you accept.

[ OK ] commits the options, applies them immediately (the theme changes on the spot) and saves them to the CFG file: the local one in the current directory if there is one, otherwise the general one next to the program (see 11). The status bar shows "Saving..." and then [SAVED] or [SAVE ERROR]. [Cancel] or ESC discards everything.

### 10.9.- CONFIRMATION DIALOGS

Quitting with unsaved changes, File > New or Open with a modified document, and overwriting in Save As all ask first:

```text
[ YES ]  /  [ NO ]      Default is always NO
Left / Right            Move between buttons
Y / N                   Direct answers
RETURN / SPACE          Accept the focused button
ESC                     Same as NO
```

With a dirty document the warning "Unsaved changes!" is shown. Note: ESC with an active selection only drops the selection; it does not quit.

### 10.10.- ABOUT

Help > About shows the version, display mode, font and memory summary. RETURN, SPACE or ESC close it.

## 11.- CONFIGURATION FILE

S6ED.CFG, S61ED.CFG and S2ED.CFG are plain text files of KEY=VALUE lines, one per line. Spaces around "=" are allowed, ";" and "#" start comments, blank lines are ignored, and values are case insensitive. Unknown keys or values are ignored silently.

Two files are read, in this order:

```text
1. The general CFG next to the program (.COM).
2. The local CFG in the current directory, only when it
   differs from the program's directory.
```

Later keys win, so the local file only needs the keys you want to override. Settings > OK saves to the local file if one was read, otherwise to the general one.

Keys (defaults in brackets):

| Key / Command | Description |
|:---|:---|
| `PROFILE` | STD / TED / EMC / VI              [STD] |
| `WRAP` | DEV / TXT                         [DEV] |
| `` | TEXTWIDTH 0..255 (alias TW; 0 = no margin)  [0] |
| `MARKUP` | OFF / MD / LIT                    [MD] |
| `CLOCK` | 0 / 1                             [1] |
| `TABWIDTH  2 / 4 / 8` | [4] |
| `EOL` | AUTO / DOS / UNIX                 [AUTO] |
| `AUTOALIGN OFF / ON / DEV` | [OFF] |
| `THEME` | DARK / AMBER / GREEN / LIGHT / |
| `MSX / MONO` | [DARK] |
| `SHADOW` | See below                  [S6ED/S61ED: OFF] |
| `` | [S2ED: ON] |

SHADOW chooses which color the window drop shadows borrow:

```text
[S6ED/S61ED]  OFF or BG (document background), FG, UI,
              HI. ON means UI.
[S2ED]        OFF, ON (the theme's own shadow color) or
              a single hex digit 0-F (a TMS9918 color).
```

Extra keys, only on [S6ED/S61ED] (Screen 6 has a programmable palette; they are never written by Settings):

```text
COLOR_BG=R,G,B          Background   (color 0)
COLOR_TEXT=R,G,B        Text ink     (color 1)
COLOR_UI=R,G,B          Chrome       (color 2)
COLOR_HIGHLIGHT=R,G,B   Accent       (color 3)
```

```text
(R,G,B are 0..7; COLOR_FG and COLOR_HI are aliases.)
```

Settings saves exactly the nine dialog options; TEXTWIDTH and the COLOR_* keys are never written by it.

## 12.- THEMES

THEME= changes the whole look at once. All three editors ship the same six themes:

```text
DARK     Light text on dark blue (the default)
AMBER    Amber monochrome look
GREEN    Green monochrome look
LIGHT    Dark text on light grey
MSX      Classic MSX blue
MONO     Pure white on black
```

[S6ED/S61ED] reprogram the four Screen 6 palette entries per theme; COLOR_* keys can then override any of them.

[S2ED] cannot reprogram the fixed TMS9918 palette, so a theme instead chooses which of the 16 hardware colors fills each of the twelve roles (text, menu bar, status bar, window body, accent, focus, shadow...).

The theme can be changed live in Settings and is applied the moment you accept.

## 13.- FONTS

Each editor draws its text with a font file that sits next to the program: S6ED.FNT, S61ED.FNT or S2ED.FNT. If it is missing or has the wrong size, the MSX ROM charset is used instead ([S6ED/S61ED] show [ROM] on the status bar).

All three keep the glyphs in the MSX international character order, 8 bytes per glyph (one per row, bit 7 is the leftmost pixel), 256 glyphs:

| Key / Command | Description |
|:---|:---|
| `S6ED.FNT` | 8192 bytes: four variants of 2048 (normal, |
| `` | bold, italic, bold+italic). Glyphs are 6x8 in |
| `` | bits 7-2. Normal must leave column 5 empty: it |
| `` | is the letter spacing. The other three may use |
| `` | it. |
| `` | S61ED.FNT  8192 bytes: same four variants, 8x8 glyphs, |
| `` | all eight columns drawn. Column 7 is the usual |
| `` | letter spacing; box and block glyphs use it to |
| `` | meet their neighbours. |
| `S2ED.FNT` | 2048 bytes: one variant, 4x8 glyphs in bits |
| `` | 7-4. [S2ED] shows bold and italic with |
| `` | colours. |

The markup engine (6.7) picks the variant, so a font whose four variants are equal simply shows no weights.

Changing the S61ED font: the disks carry example fonts in A:\TOOLS\FONTS. Copy one over the editor's own and start the editor again:

```text
COPY A:\TOOLS\FONTS\CPC.FNT A:\TOOLS\S61ED.FNT
```

The default S61ED.FNT is hand-drawn by Miguel A. Fernandez. Its normal weight is his drawing; bold, italic and bold+italic are derived from it for now.

| Key / Command | Description |
|:---|:---|
| `CGA.FNT` | IBM CGA. Normal is the CGA's thin |
| `` | font and bold its thick one: the card carried |
| `` | both. Font design (c) IBM; raw ROM dumps from |
| `` | VileR's VGA text mode font collection. |
| `CPC.FNT` | Amstrad CPC 464. The CPC has no accented |
| `` | letters: they are built from its own accent |
| `` | marks. Amstrad have kindly given their |
| `` | permission for the redistribution of their |
| `` | copyrighted material but retain that |
| `` | copyright. |
| `BIOS.FNT` | The MSX BIOS font, with derived weights. It |
| `` | is a 6 pixel design, so at 8x8 it looks spaced |
| `` | out. |

Making a font: the source distribution has RES/mkfont61.py, which turns any raw 2048-byte 8x8 font from another machine into an S61ED.FNT (mapping each character by meaning, building missing accented letters, deriving the weights), and writes an editable sheet: a 512x212 indexed PNG with the four variants in 32x8 grids, glyph N at ((N AND 31)*8, (N / 32)*8) of its block, ink in colour 3. Draw on the sheet with any paint program that keeps the palette, then convert it back:

```text
mkfont61.py sheet MYFONT.PNG --out S61ED.FNT
```

With --derive only the normal block is read and the other three weights are generated from it, so you can start by drawing one block.

RES/FONTS61/README.md lists the sources and their credits.

## 14.- FILES & DISK

Line endings (EOL=, default AUTO):

| Key / Command | Description |
|:---|:---|
| `AUTO` | The first line ending found on load decides: CRLF |
| `` | (or bare CR) means DOS, bare LF means UNIX, and |
| `` | saving uses the detected style. |
| `DOS` | Always save with CRLF. |
| `UNIX` | Always save with LF only. |

Limits and safety:

- Lines are truncated at 255 characters on load.
- Raw TABs are expanded to spaces on load (see 6.3).
- A file too big for the available memory is refused BEFORE loading anything ([FILE TOO LARGE]); if memory runs out in the middle of a read, the partial document is discarded and the file name cleared, so a later Ctrl+S can never overwrite the original file with truncated contents.
- A failed open leaves the current document untouched ([CANNOT OPEN]); a nonexistent file opens a new empty document under that name ([NEW FILE]).
- Saving with no file name shows [NO FILE NAME].

Disk errors: the editor installs its own MSX-DOS 2 / Nextor error handlers, so an empty drive, an open drive door or a write-protected disk no longer drops the DOS "Abort, Retry, Ignore?" prompt over the graphics screen. The operation simply fails and the status bar tells you ([SAVE ERROR], [CANNOT OPEN]...). Ctrl+STOP pressed in the middle of a disk operation is handled the same way: the operation is abandoned and the editor carries on.

Every save reports on the status bar: a "Saving..." progress bar over the lines while it writes, then [SAVED] or [SAVE ERROR]. A load shows a "Loading..." bar over the file size: a large file on a floppy takes seconds (the 1,100 lines of this manual, about 10 s); the bar tells a slow disk from a hung machine. The line count on the right grows meanwhile.

Each editor checks that its .DAT file is its own: a sibling's container renamed is refused at start with "<editor>.DAT corrupt.", in text mode.

## 15.- TROUBLESHOOTING

(S6ED is used as the example; read S61ED or S2ED for the other editors.)

"S6ED.DAT not found." / "S6ED.DAT corrupt." The feature container must sit next to the .COM (or in the current directory). Copy it again from the distribution disk. Each editor needs its own .DAT: they are not interchangeable.

The text looks wrong / status bar shows [ROM]  [S6ED/S61ED] The .FNT file is missing or has the wrong size; the MSX ROM charset is being used. Restore the .FNT file.

"S6ED requires 2 free mapper segments." Not enough free mapper memory. Under Nextor on a 128 KB machine only one segment is free: use MSX-DOS 2, or add memory. /V at boot shows the exact numbers.

"Requires MSX-DOS 2 or Nextor." The editor does not run on plain MSX-DOS 1.

"Insufficient Page 3 memory." The transient program area is too small. Remove resident software (TSRs) and try again.

Settings are not being saved Settings writes to the LOCAL .CFG of the current directory when there is one (see 11). Check which file you are editing, and that the disk is not write-protected ([SAVE ERROR] would tell you).

Accents type twice or not at all They should not: the editor reads the keyboard matrix directly and arbitrates against the BIOS. Please report the machine model if you see this.

The disk boots to the DOS prompt instead of the editor AUTOEXEC.BAT must have DOS line endings (CR LF). A file edited on a modern computer and saved with bare LF line endings is ignored by COMMAND2.COM. Save it with EOL=DOS.

## 16.- THANKS

- Miguel A. Fernandez, for the beautiful hand-drawn 6x8, 8x8 and 4x8 fonts (and for testing beyond the call of duty).
- Miguel Fides, for his support and ideas.
- VileR, for the VGA text mode font collection the IBM CGA font comes from. Font design (c) IBM.
- Amstrad, for the CPC font: Amstrad have kindly given their permission for the redistribution of their copyrighted material but retain that copyright.
- Konamiman, for Nextor.
- The whole MSX community, for keeping this machine alive 40+ years on.

Enjoy your MSX!

