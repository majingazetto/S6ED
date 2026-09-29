# SPEC — File Browser (Open... / Save As...) and the File Menu

Status: **closed — all decisions taken (§10), awaiting approval to implement** (2026-09-29)
Targets: S6ED (V9938, Screen 6, 80 columns) and S2ED (TMS9918, Screen 2, 64 columns)
Prerequisite shipped: program home directory + two-level CFG (`dev` `6e102d3`)

---

## 1. Why, and what is broken today

The File menu advertises five things and delivers two. Measured in the code:

| Item | State |
|---|---|
| `Ctrl+N` | bound in **no** keymap (Emacs `^N` is cursor down, by design) |
| `Ctrl+O` | printed in the menu, bound nowhere |
| File > New | `.FNEW` resets the buffer **without asking**, even with `MODIFIED` set, and clears `FILENAME` |
| `Ctrl+S` after New | `FILESAVE` with an empty `FILENAME` does `SCF / RET`: **nothing, silently** |
| File > Open, File > Save As | `.FILMNU` dispatches items 0, 2 and 5 only: 1 and 3 do nothing |
| `:e NOEXIST.TXT` | `FILELOAD` calls `FILENEW` **before** `DSKOPEN`: a failed open has already thrown the document away (with `:e!` that bypasses the `MODIFIED` guard) |
| `FILENAME` | `DEFS 40`: too short for a DOS 2 path (63 + NUL) |

Save As needs the browser as much as Open does — without it there is no way to
choose the directory — so both are one dialog in two modes.

---

## 2. Decisions

### 2.1 DOS 2 only, and the browser never moves the process

- Listing: **`_FFIRST` (40H) / `_FNEXT` (41H)** with `DE` = ASCIIZ
  `"D:\PATH\MASK"` and `IX` = a 64-byte **File Info Block** (the DOS 2 structure,
  `program.txt` §3.4: `#FF`, name ASCIIZ at 1..13, attributes at 14, size at
  21..24). Search attributes `B = ATTR_DIR | ATTR_HID | ATTR_SYS` (`#16`):
  **every entry is listed**, hidden and system included, and marked (§3.2). No FCB, no DTA, no DOS 1 path — S6ED/S2ED abort
  at boot without DOS 2 already.
- The browser keeps **its own path string, `BRWPATH`**, and never calls
  `_CHDIR` or `_SELDSK`. Entering a directory appends to `BRWPATH`, `..` strips
  its last item, a drive entry rewrites its prefix. Consequences:
  - nothing to restore on close, on cancel, or after an error;
  - the local CFG (`.\S6ED.CFG`) keeps meaning the directory the editor was run from;
  - `FILENAME` becomes a **full path** (`A:\DEV\NOTES.TXT`), so Ctrl+S writes where
    the file came from wherever the user browsed since.
- Initial `BRWPATH`: the directory part of `FILENAME` if it has one, otherwise
  the current directory, built as `D:\PATH\` — the code `HOMEINIT` already
  runs for `CFGLOC`, extracted into a shared `CURDIR` routine.
- Drives: `_LOGIN` (18H) gives the vector of available drives. They are listed
  at the end as `A:` .. `H:`; choosing one sets `BRWPATH` to that drive's current
  directory (`_GETCD` with `B` = drive).

### 2.2 Modals are sequential, never nested

A confirmation ("Overwrite NOTES.TXT?", "Discard unsaved changes?") **does not
open on top of the browser**. On both targets a second window would overwrite
the first one's saved background (S6: the `Y + 512` save rect and the
`Y = 768` composition buffer; S2: the single `WSVBUF`). Instead:

1. the browser closes and returns `(mode, full path)` to page 1;
2. page 1 asks the question with `DOASK`;
3. on **No** it reopens the browser with its state intact — `BRWPATH`, listing,
   selection and scroll live in page 3 — so reopening costs a repaint, not a
   rescan.

### 2.3 How the browser window closes

| | S6ED | S2ED |
|---|---|---|
| Background save | `WINSAV` to `Y + 512` has no size limit (a full 212-line page) | `WSVBUF` holds `WSVMAX / 9` = 170 cells; `WINOPEN` **shrinks** a larger window without warning (`.SZLP`). The browser needs ~600 |
| Close | `WINCLOS`, as every dialog | new flag **`WINNOSV`**: `WINOPEN` skips `WSAVE` and the size clamp, `WINCLOS` skips `WRSTOR`; the page-1 caller repaints with `REDRAW` + `DRWMENU` + a forced `DRWSTAT` (`STATPRV` invalidated) |

Open needs a full `REDRAW` anyway, so on S2 only Save As and Cancel pay for the
repaint.

### 2.4 Where the code lives

- `DOBRW` (dialog, key loop, painting) goes in **FTRSEG** on both targets, next
  to the other dialogs, and is reached through `FCALL`.
- Scanning, sorting and path editing are target-agnostic and also go in
  FTRSEG, in a CORE file included into both containers (`CORE/BROWSE.Z8A`).
  BDOS calls from FTRSEG code are already proven: `CFGLOAD` does them.
- What happens after the dialog (confirm, `FILELOAD`, `FILESAVE`, `REDRAW`)
  goes in **page 1** (`ACTION.Z8A`), because it needs the text segments banked —
  the `DOMNU` / `GOTOLN` rule.

---

## 3. Geometry per target — the column difference

The list shows entries in a **grid of slots**. A slot is **14 character
columns**: a 13-character field plus a 1-character gap. That fits the longest
entry, `12345678.123`, and a directory's trailing `\`.

- On **S2** 14 characters are **exactly 7 cells**. As long as the list starts on
  a cell boundary, every slot owns whole cells, so the selection bar is a
  colour-byte change (`VCOLBSEL`) with no half cell hanging off. That is the
  same constraint `DOQIT`'s buttons already follow (`S2ED Status`, W2).
- On **S6** a slot is `14 × 6 = 84 px`. The window `X` is a multiple of 4 and
  84 is too, so every slot stays byte-aligned for `HMMV` / `WINUPD`.

| | S6ED | S2ED |
|---|---|---|
| Screen | 80 × 24 (text band 24 rows), 6 px glyphs | 64 × 24 (text band 22 rows), 4 px glyphs, 2 per cell |
| Grid | **5 columns × 14 rows = 70 slots** | **4 columns × 12 rows = 48 slots** |
| List width | 70 chars = 420 px | 56 chars = 28 cells |
| Window | `WINW` ≈ 436 px, centred (`WINX` ≈ 36) | `WINNC` = 30 cells (28 + 2 border), `WINC` = 1 |
| Height | title + 14 list + separator + info + field + buttons + frame ≈ 20 char rows (160 px + frame), within `WINH ≤ 208` | title + 12 list + separator + info + field + buttons + bottom = `WINNR` 18, `WINR` = 2 |

These come from per-target constants (`BRWCOLS`, `BRWROWS`, `BRWSLOT = 14` in
`CONST_S6.Z8A` / `CONST_S2.Z8A`), never from literals in CORE. The T0 check
`target-params` already bans S6 geometry in CORE, and gets one more pattern.

### 3.1 Layout

The path moves into the title bar, and the row it frees becomes an
**information line** for the selected entry under a separator. The grid itself
shows names only, so it keeps its density.

S6ED (80 columns):
```
+- Open  A:\DEV\*.* -----------------------------------------------------+
| ..\           SUB\          TOOLS\        ASM\          AUTOEXEC.BAT   |
| MSXDOS2.SYS~  COMMAND2.COM [NOTES.TXT]    TEST.TXT      TODO.MD        |
| S6ED.CFG      LONGNAME.ASM  README        A:            B:             |
|                                                                        |
+------------------------------------------------------------------------+
| NOTES.TXT         1,234 bytes     29-09-26 11:52a       ---A    15/160 |
| Name: [NOTES.TXT______________________________________]                |
|                                                   [ Open ]   [Cancel]  |
+------------------------------------------------------------------------+
```

S2ED (64 columns), Save As with a directory selected:
```
+- Save As  A:\DEV\*.* ------------------------------------+
| ..\          [SUB\]         TOOLS\        ASM\           |
| AUTOEXEC.BAT  MSXDOS2.SYS~  COMMAND2.COM  NOTES.TXT      |
| TEST.TXT      TODO.MD       S6ED.CFG      LONGNAME.ASM   |
| README        A:            B:                           |
+----------------------------------------------------------+
| SUB\         <DIR>  29-09-26 11:51a  ----  15/96         |
| Name: [NEWFILE.TXT_______________________]               |
|                                       [ Save ] [Cancel]  |
+----------------------------------------------------------+
```
(`[ ]` is the selection bar, `~` is drawn in the hidden/system style of §3.2,
and the date is shown the way `DIR` shows it — here with `SET DATE=DD/MM/YY` and `TIME=12`.)

- Order: **`..\` first** whenever `BRWPATH` is not a root, then directories,
  then files, then drives. Directories and files are each sorted by name.
  `..\` is synthesised by the browser (bit 5 in the flags), not taken from the
  `..` directory entry: the root has none and `_FFIRST` would list `.` too, so
  both real entries are skipped.
- Navigation: `RETURN` on a directory appends `NAME\` to `BRWPATH` and rescans;
  `RETURN` on `..\` (or `BS` anywhere in the list) strips the last item. After
  going up, the selection lands on the directory just left, so walking up and
  down a tree does not lose the place. `BRWPATH` is bounded by `FNAMMAX`:
  entering a directory whose path would not fit is refused with a status
  message.
- The list is **row-major** (left to right, then down). It scrolls **one row**
  at a time, so a scroll repaints `BRWROWS` rows of slots and a cursor move
  repaints two slots plus the information line.

### 3.2 Marks

The name itself carries no marker character, because a 12-character name plus
`\` already fills 13 of the 14 columns. The attribute is shown by **style**,
which both targets already have:

| Entry | S6ED | S2ED |
|---|---|---|
| directory | trailing `\` | trailing `\` |
| hidden or system | **italic** glyphs (`FITAL_SY`, the italic block of `S6ED.FNT`) | a distinct colour for the slot's 7 cells |
| read-only | italic too (it is also "not a plain file") — or left plain, decided in F2 | same as S6 |
| drive | `A:` .. `H:` | same |

On S2 the colour cannot simply be `VCOLITAL`, which is a *document* colour
(foreground on the document background); on the window body it may not
contrast. F3 picks the role and asserts per theme that it differs from
`VCOLWIN` — the rule that a role a mutation swaps must differ.

### 3.3 Selection

S6 paints the slot in `COL_HI` in the composition buffer and
  `WINUPD`s just that rect, like the button focus. S2 sets the slot's 7 colour
  bytes to `VCOLBSEL` and dumps that one row (`WDUMPR`).

---

### 3.4 Information line

What it shows for the selected entry:

| Entry | Content |
|---|---|
| file | name, size in bytes, date and time, attributes `RHSA` (`-` when clear), count `n/BRWMAX` |
| directory | name, `<DIR>`, date and time, attributes |
| `..\` | the parent path |
| drive | `Drive B:` |

- **Read on selection, not while listing.** When the selection settles, the
  browser runs `_FFIRST` on the exact name and takes the size (21..24), date
  (17..18), time (15..16) and attributes (14) from the File Info Block. Nothing
  extra is stored per entry, so `BRWMAX` is not affected. Storing size and date
  per entry would cost 7 B each, which S2ED's page 3 cannot pay at 96 entries.
- **Not on every repeat of a held key.** The line is refreshed only when the
  key queue is empty (`CHSNS` / `GETPNT`, the `KEYRUN` mechanism), so holding a
  cursor key does not issue one DOS search per entry it passes. DOS 2 normally
  holds the directory sector just scanned in its buffers. F2 measures the
  refresh cost on the 128 kB NMS 8250 floppy.
- **The date and time format belong to the system, not to us.** COMMAND2 sets up
  two environment items (`command.txt` §7) and `DIR` honours both:
  - `DATE`: three letters or letter pairs separated by one date separator
    (`yy-mm-dd`, the Japanese default; `DD/MM/YY`; `MM/DD/YY`). The default
    comes from the country of the machine, and the user changes it with
    `SET DATE=`.
  - `TIME`: `24` means a 24-hour clock; anything else means 12-hour with an
    am/pm mark.

  The browser reads both with `_GENV` when it opens and formats the date and
  time **exactly as `DIR` does**. The rules were **measured** on 2026-09-29 by
  running `SET` and `DIR` with redirected output on four machines — MSX-DOS 2
  on the NMS 8250 and on the Japanese MSX2+, Nextor on the NMS 8250 and on the
  HB-20P — with two files stamped 29-Sep-2026 09:05 and 05-Jan-2026 21:07, plus
  31-Dec-1999 00:30 and 03-Feb-2000 12:45 for the 12-hour edges. All four
  machines agree:

  | Rule | Measured |
  |---|---|
  | Field order | the first letter of each of the three `DATE` items, case-insensitive: `mm-dd-yy`, `DD/MM/YY`, `Y-M-D`, `YY MM DD` all work |
  | Separator printed | **always `-`**, whatever separator `DATE` uses (`DD/MM/YY` prints `29-09-26`, `MM.DD.YY` prints `09-29-26`) |
  | Year | **always 2 digits**, even with `Y-M-D` (`26-09-29`, `99`, `00`) |
  | Day and month | 2 digits, zero-padded |
  | `TIME=12` (and any value other than `24`) | hour right-aligned in 2 columns, then `:mm` and `a`/`p`: ` 9:05a`, ` 9:07p`, `12:30a` for 00:30, `12:45p` for 12:45 |
  | `TIME=24` | hour right-aligned in 2 columns, then `:mm` and a **space** where the mark would be: ` 9:05 `, `21:07`, ` 0:30 ` |
  | Defaults | `DATE=mm-dd-yy` on the NMS 8250 and on the HB-20P (both kernels), `DATE=yy-mm-dd` on the Japanese MSX2+; `TIME=12` everywhere |

  A full `DIR` line reads `AM       TXT         1 09-29-26  9:05a`. The
  information line prints the date and time in the same 15 characters
  (`09-29-26  9:05a`). A `DATE` that cannot be parsed falls back to
  `yy-mm-dd`, the documented default. The F2 gate case sets two `DATE` values
  and both `TIME` values and compares the information line with these strings.

## 4. Data (page 3, unbanked)

The listing is too big for FTRSEG on S2 (1,216 B … 4,374 B free) and must not
use `CLIPBUF` — **that would throw away the clipboard each time the browser
opens**, which is what the roadmap proposed. It lives in page 3, above the
existing buffers:

| Item | Size | Notes |
|---|---|---|
| `BRWENT[BRWMAX]` | 12 B each | 11-char padded 8.3 name + flags (bit 7 = directory, bit 6 = drive, bit 5 = `..`, bit 1 = hidden, bit 2 = system, bit 0 = read-only — the DOS attribute bits kept in place) |
| `BRWIDX[BRWMAX]` | 1 B each | sort order, so insertion sort moves bytes rather than 12-byte records |
| `BRWFIB` | 64 | the DOS 2 File Info Block |
| `BRWPATH` | 64 | `D:\PATH\`, DOS 2 maximum |
| `BRWMASK` | 13 | `*.*` or what the user typed |
| state | ~8 | count, top row, selection, focus, mode |

| | S6ED | S2ED |
|---|---|---|
| Base | `PAGE3_TOP` `#C600` | `WSVTOP` `#CC00` |
| `BRWMAX` | 160 → 2,080 + 149 = 2,229 B | 96 → 1,248 + 149 = 1,397 B |
| New `TP3MIN` (1 KB of stack kept) | `#D2B5` | `#D575` |
| Against `(#0006)` = `#D706` | 1,105 B of headroom | 401 B (**tight**, see §9) |

A directory with more than `BRWMAX` entries lists the first `BRWMAX`, shows
`+more` in the count and stays fully usable: a name or a mask typed in the
field reaches any file. A 720 kB root directory holds at most 112 entries.

---

## 5. Interaction

Focus ring (`TAB` / `SHIFT+TAB`): **list → name field → [Open|Save] →
[Cancel]**. SPACE activates only the focused control, which is the `WINEDIT`
rule.

| Key | In the list |
|---|---|
| cursors | move the selection, scrolling a row at the edges |
| `RETURN` | directory: enter it and rescan. Drive: switch to it. File: accept |
| `BS` | parent directory (same as `..\`) |
| a letter | jump to the next entry starting with it |
| `ESC` | cancel from any focus |

**Name field** (`WINEDIT` with `ED_FILE`, which is declared and not
implemented yet): 8.3 characters plus `\ : . * ?`, forced to upper case.

- Moving the selection onto a file copies its name into the field.
- `RETURN` in the field:
  - with `*` or `?`: the text becomes `BRWMASK` and the directory is rescanned;
  - with `\` or `:`: a path, relative to `BRWPATH` or absolute;
  - otherwise: accept `BRWPATH + field`.
- **Open** accepts a name that is not in the list: it simply fails to open.
- **Save As** requires a non-empty name, and the field has focus when the
  dialog opens.

---

## 6. Flows

- **New** (`Ctrl+N`, File > New): if `MODIFIED`, `DOASK "Discard changes?"`
  (default No). Then `FILENEW`, clear `FILENAME`, `REDRAW`, `DRWMENU`.
- **Open** (`Ctrl+O`, File > Open, Vi `:e` with no argument):
  1. if `MODIFIED`, ask first;
  2. browser in Open mode;
  3. `FILELOAD` **reordered**: open the file first and reset the buffer only once
     the open has succeeded, so a failed open keeps the document;
  4. on failure, `[OPEN ERROR]` in the status bar.
- **Save As** (File > Save As, `Ctrl+Shift+S` in STD, Vi `:w` with no name and
  no `FILENAME`):
  1. browser in Save mode;
  2. if the name exists (`_FFIRST` on the exact path), `DOASK "Overwrite?"`, and on
     No reopen the browser;
  3. set `FILENAME`, then `FILESAVE`.
- **Save** (`Ctrl+S`) with an empty `FILENAME` goes to Save As instead of
  returning silently.
- **`DOASK`**: `DOQIT` generalised to a message pointer (Yes / No, default No,
  `Y` / `N` accelerators). `DOQIT` becomes a call to it, which saves bytes on both
  targets.

### 6.1 Key bindings

| Profile | New | Open | Save As |
|---|---|---|---|
| STD | `Ctrl+N` | `Ctrl+O` | `Ctrl+Shift+S` |
| WS | menu (`^N` / `^O` are WordStar prefixes) | menu | menu |
| Emacs | menu (`C-n` is down) | menu | `Ctrl+Shift+S` |
| Vi | `:enew` (optional) | `:e` without argument | `:w` without a name |

---

## 7. `FILENAME` becomes a path

- `FNAMMAX EQU 64` in `CONST_CORE`; `FILENAME DEFS FNAMMAX + HOMENAM` leaves
  room for a directory plus a name while it is being built.
- Every writer is bounded by it: `.CPYFNAM` (`B, 38` today), `PARAMS` /
  `CHKFILE`, and the browser.
- Row 0 shows **only the last item** (`FNBASE`: scan back to `\` or `:`), at
  most 12 characters. S6 `DRWFNAM` caps at 30 today and S2 at 20, so a path
  would overflow the menu bar.

---

## 8. Phases

Each phase ends with `make testall` green, and every new case comes with a
mutation.

| Phase | Content | Gate |
|---|---|---|
| **F0** | Bind `Ctrl+N` / `Ctrl+O`, `DOASK` (with `DOQIT` rewritten on it), New asks first, `FILELOAD` opens before resetting, `FILESAVE` with no name reports it | case: New with `MODIFIED` asks and No keeps the document; `:e NOEXIST` keeps the document (disk read-back) |
| **F1** | `FNAMMAX`, `FNBASE`, `CURDIR` extracted from `HOMEINIT`, `ED_FILE` in `WINEDIT` (both targets) | a 50-character path on the command line is loaded, saved back to the same path and shown as its last item |
| **F2a** | **Done 2026-09-29**: what `DIR` prints, measured on four machines (§3.4) | the F2 case compares against these strings |
| **F2** | `CORE/BROWSE.Z8A` scan, sort and path editing; S6 `DOBRW`; Open wired to the menu, `Ctrl+O` and `:e` | fixture disk with subdirectories built by `dskfat`: navigate into `SUB\`, open a file there, `FILENAME` = full path; `..\` present below the root and absent at it, `BS` up lands on the directory left; a hidden and a system file listed and drawn italic; drive entry; mask; more than `BRWMAX` entries |
| **F3** | S2: `WINNOSV`, S2 `DOBRW` on the 4 × 12 grid | the same cases on S2, plus the `VCOLBSEL` bar owning whole cells (computed pattern table) |
| **F4** | Save As on both targets: overwrite confirmation, reopen on No | save into a subdirectory; overwrite No and then Yes; the file is read back off the disk with `dskfat get` |

The harness gains **subdirectory fixtures**: `Case.disk_files` accepts
`DIR\NAME` keys and `Session.build_disk` writes them with `dskfat.py`. That
replaces the `MD` / `COPY` in `AUTOEXEC.BAT` that H29 uses.

---

## 9. Budget and risks

| | S6ED | S2ED |
|---|---|---|
| `FTRFREE` today | 9,744 B | **4,374 B** |
| Browser (estimate) | ~2.0–2.5 KB | ~1.5–2.2 KB |
| Information line (on-demand `_FFIRST`, `DATE`/`TIME` parsing, 32-bit decimal) | ~250–350 B | ~250–350 B |
| `DOASK` generalisation | ≈ 0 (it replaces `DOQIT`'s body) | ≈ 0 |
| Page 1 (actions, dispatch, `FNBASE`, `CURDIR`) | ~300 B of 4,256 | ~300 B of **512** |
| Left for Settings (the last core feature) | ~7 KB | **~2.0–2.8 KB** |

- **S2 page 1 (512 B free):** if F0 + F1 do not fit, move `HOMEPTH` (80 B) and
  `BRWPATH` to page 3 first.
- **S2 page 3:** 401 B above the 1 KB stack reserve is tight. Measure `(#0006)`
  under Nextor on `m1d2` before F3 — the `#D706` figure was measured under
  MSX-DOS 2 on the NMS 8250, not on the MSX1. If it is lower, cut `BRWMAX` to 64.
- An `ASSERT FTRFREE >= 1024` on S2 from F2 on, so the room kept for Settings
  cannot be spent by accident.
- The overlay mechanism (on-demand `S2ED.DAT` blocks) stays **plan B**, used only
  if the measured size after F3 leaves Settings no room.

---

## 10. Decisions taken (2026-09-29)

1. Grids: **names only**, 5 columns on S6ED and 4 on S2ED. Size, date, time and
   attributes of the **selected** entry go on an information line under the grid
   (§3.4), read on demand. **14 rows on S6ED, 12 on S2ED** (70 / 48 visible).
2. Drives: **listed** in the grid, after the files.
3. Hidden / system files: **shown**, marked by style (§3.2).
4. `BRWMAX`: **160 / 96**, at the page-3 limit (§4), subject to the `(#0006)`
   measurement under Nextor before F3.
5. Navigation: `..\` at the top whenever not at a root, `RETURN` enters a
   directory, `BS` goes up, the selection returns to the directory left (§3.1).
6. Date and time: **the format is not ours** — it comes from the `DATE` and
   `TIME` environment items, formatted by the rules measured from `DIR` (§3.4).
