# S6ED — Inter-Segment Infrastructure & Container Architecture

Date: 2026-09-17 · Status: **IMPLEMENTED & EMPIRICALLY VERIFIED (Fase 1a, Fase 1b, Fase 2, Fase 3a, Fase 3b, Fase C1 & Fase C2 complete)**
Scope: Fase 1a (boot-time segment budget, mandatory minimum) + Fase 1b (inter-segment
call machinery + first resident feature) + Fase 2 (`S6ED.DAT` standalone multi-segment container loader) + Fase C1 (loader hardening: table-driven multi-block load, full descriptor validation, FCALL stack guard).
Roadmap context: `informe_directorio_segmento_s6ed.md` §6.

---

## 1. Directive (agreed 2026-09-16)

**The editor requires a minimum of 2 free mapper segments at boot. If they are not
there, the editor does not start.** No silent degradation, no optional features:
the feature segment is resident and mandatory because everything queued next
(tokenizer, menus, Vi command line, keymap bundles) will live in it.

## 2. Measured segment budget

Measured 2026-09-16 with `PROBE.COM` (EXTBIO mapper manager, `ALL_SEG` loop until
carry, count, free back), validated two ways: DOS 2 on 128 kB reports the known 2,
and Nextor on 256 kB emulation reports 9 — identical to the same probe on real
hardware (256K → 112K reserved, 144K free).

| Machine | DOS 2 free | Nextor free |
|---|---|---|
| 128 kB | **2** | **1** |
| 256 kB | ~10 (est.) | **9** |
| 512 kB | ~26 (est.) | **25** |
| 2 MB | 122 (est.) | — |

**DOS 2 reserves 6 segments; Nextor reserves 7 (112 kB), constant across mapper
sizes.** Consequence: a stock 128 kB machine running Nextor has exactly 1 free
segment and **cannot boot S6ED under this directive**. Minimum spec is therefore:
**128 kB with MSX-DOS 2, or 256 kB with Nextor.**

Reservations at boot, in priority order:

| # | Segment | If unavailable | Lifetime |
|---|---|---|---|
| 1 | `DIRSEG` — line directory | **Fatal** (existing `ERRMEM` path) | Permanent |
| 2 | `FTRSEG` — feature code | **Fatal** (new message) | Permanent |

Text needs no free segment to start: `TXSEG0 = DEFSEG2` is the TPA's own page-2
segment and holds the first 101 lines (`LINEPSEG`). Grown text segments are claimed
on demand from whatever remains, exactly as today.

Resulting text ceilings (lines = (1 + grown text segments) × 101):

| Configuration | Free | Text ceiling |
|---|---|---|
| 128 kB DOS 2 | 2 | **101** (was 202 before FTRSEG — visible regression, reported at boot) |
| 128 kB Nextor | 1 | does not boot |
| 256 kB Nextor | 9 | 808 |
| 512 kB Nextor | 25 | 2,424 |
| 2 MB DOS 2 | 122 | 3,131 (`MAXSEGS` = 32 binds: DIR + FTR + 30 grown + DEFSEG2) |

## 3. Fase 1a — boot accounting

New order in `INIT`, all in text mode **before** `SCRINIT` so messages are visible:

1. `MAPINIT` (fatal: no mapper — existing).
2. `SEGRESV` (new, core, in `MAPPER.Z8A` or new `XSEG.Z8A`):
   - Claim `DIRSEG` → on carry, fatal (existing `ERRMEM`).
   - Claim `FTRSEG` → on carry, fatal with its own message
     (`ENO2SEG DEFM "S6ED requires 2 free mapper segments.$"`).
   - Probe the remainder: `SEGGET` until carry, count `N`, free them all back.
     The probe **knows, it does not hold** — text segments are re-claimed on demand.
   - Compute and print the text ceiling: `(1 + N) × 101` lines.
   - If the ceiling < `WARNLNS` (500) → warning + wait for a key (`CHGET`),
     otherwise a single info line and continue. On the 128 kB min-spec machine the
     warning always fires (101 lines) — that is intended: the FTRSEG price is stated
     up front, per the "never reduce capacity silently" directive.
3. `SCRINIT`, `FONTINIT` as today.
4. `BUFINIT` no longer claims `DIRSEG` — it uses the one `SEGRESV` already claimed.

`SEGTBL` discipline changes: entry 0 = `DIRSEG`, entry 1 = `FTRSEG`; `SEGTRIM`'s
floor becomes **2** (a `BUFRESET` must return neither). `SEGFREE` still frees
everything on exit. `MAXSEGS` budget comment becomes "1 DIRECTORY + 1 FEATURE + 30 TEXT".

## 4. Fase 1b — inter-segment machinery

New core module `SRC/XSEG.Z8A`, always mapped (pages 0+1). The page-2 window
(`#8000-#BFFF`) is shared between text segments, `DIRSEG` and feature segments.

### 4.1 State (`VARS.Z8A`, inside the block `INIT` zeroes)

- `HOMESEG` — segment of the feature currently executing. Written only by `FCALL`.
- `SEGSTK` — 4-deep stack of `{prev TXSEG, prev HOMESEG}` pairs; `SEGSP` pointer.
  Overflow is a design error: fatal abort via `ERRMSG` (Fase C1 added the guard;
  before it, a 5th level silently overwrote `DATHAND`).

### 4.2 Core → feature: only through `FCALL`

`FCALL`: `A` = segment, `HL` = entry address (`#8000`-relative label).
Pushes `{TXSEG, HOMESEG}`, banks the feature (`PUTP2`, `TXSEG` follows), sets
`HOMESEG`, `CALL` the entry, and on return **restores the previous page-2 segment**
and pops the pair.

### 4.3 Feature → core: direct calls under a verified invariant

The original design routed every feature→core call through re-banking stubs
(`STB_X`, one per core routine, living in the core). **The stubs were never
implemented.** Feature code in `FTRSEG` calls core routines and BDOS directly
(e.g. `CFG.Z8A`, `WINPOLL`→`UPDMCLK`→`CALL DOS`), which is safe under an
empirically verified invariant:

> **Neither BDOS (MSX-DOS 2 / Nextor) nor the S6ED core re-banks page 2 across
> a call.** The feature segment stays mapped for the whole call, so no
> re-bank on return is needed.

Verified with `TEST/PROBE2.Z8A` (page-2 BDOS caller probe, §10). The invariant
must be re-verified before any future feature performs disk I/O from inside
`FTRSEG`; if it ever breaks, the defence is the original stub design — an
unconditional re-bank on return, ≈ 150 T-states per call:

```
STB_X   CALL  X
        LD    A, (HOMESEG)
        LD    (TXSEG), A
        CALL  PUTP2
        RET
```

### 4.4 Rules

- `TXSEG` follows every bank — extends the existing `RECBANK`/`DIRBANK` discipline.
- **Feature → feature calls are forbidden.** The mailbox mechanism (fixed area in
  page 0/1, routed through the core) is specified for Fase 3, not built now.
- **No ISRs or hooks in pages 1/2** (existing rule, restated).
- Features never call `PUTP2` / `RECBANK` / `DIRBANK` / `GETP2` / `SEGGET` /
  `FRESEG` directly. Build-time lint enforces it (§6).

### 4.5 How code reaches the segment in Fase 1 (no loader yet)

In Fase 1b, the feature modules were assembled inside the `.COM` image wrapped in a
single global `PHASE #8000` / `DEPHASE` container block (`FTRBLOB`) and LDIR-copied
via `F1COPY`. In Fase 2, this copy has been completely replaced by the external
container loader `DATLOAD` described below.

---

## 9. Fase 2 + C1 — `S6ED.DAT` Standalone Multi-Segment Container Loader (hardened 2026-09-17)

Fase 2 physically decouples feature modules from the executable `S6ED.COM` into an
external container file **`S6ED.DAT`**. Fase C1 replaced the original linear
loader (header → one descriptor → sequential payload) with a table-driven
multi-block loader that validates every field before a single byte is written.

### 9.1 Container File Layout (`S6ED.DAT`)

The container consists of a 16-byte global header, a Block Descriptor Table of
`NUMBLKS` 8-byte entries, and the binary payloads anywhere past the table (the
on-disk order is irrelevant: the loader seeks to each `DATAOFF`). All
multi-byte numeric fields are 16-bit Little-Endian.

```
+-------------------------------------------------------------+
| Global Header (16 bytes)                                    |
|   0..3:   Magic identifier ASCII "S6ED"                     |
|   4..5:   Format version (#0001, 16-bit LE)                 |
|   6:      MSX-DOS / CP/M EOF marker (#1A)                   |
|   7:      NUMBLKS: block count, 1..8 (DATMAX)               |
|   8..9:   Offset pointer to Block Table (16-bit LE, >= 16)  |
|   10..15: Reserved (#00)                                    |
+-------------------------------------------------------------+
| Block Descriptor Table (NUMBLKS entries of 8 bytes each)    |
|   0:      BLKID (1 = FTRSEG feature segment)                |
|   1:      FLAGS (1 = mandatory boot-load; reserved)         |
|   2..3:   LOADADDR (16-bit LE, inside #8000..#BFFF)         |
|   4..5:   LENGTH  (16-bit LE, 1..16384)                     |
|   6..7:   DATAOFF (16-bit LE, absolute file offset)         |
+-------------------------------------------------------------+
| Binary payload blocks, anywhere at/after end of table       |
+-------------------------------------------------------------+
```

Current container (1 block): header 16 B + one descriptor 8 B + FTRSEG payload
(`CFG.Z8A` + `WINDOW.Z8A`, phased at `#8000`) at `DATAOFF` = 24. `LENGTH` =
`FTRBLEN` (2,402 bytes as of 2026-09-18); total file 2,426 bytes. The build
enforces `ASSERT BLK0LEN <= 16384`; the loader re-enforces it at run time, so a
patched or corrupted file cannot defeat it.

### 9.2 Build Pipeline

Unchanged: the container is emitted directly by `sjasmplus` via the rotating
`OUTPUT` directive at the end of `CODE/SRC/S6ED.Z8A` (header, descriptor table,
`PHASE #8000` payload). `CODE/Makefile` declares `S6ED.DAT` as a primary build
artifact.

### 9.3 Loader Mechanics (`CHKDAT`, `DATHCHK`, `DATLOAD`, `BLKSEG` in `XSEG.Z8A`)

1. **Text-Mode Pre-Check (`CHKDAT`):**
   - Called in `INIT` after `SEGRESV`, before `SCRINIT`, in plain text mode.
   - `DSKOPEN` on `S6ED.DAT` (failure → `.ERRDAT`, exit via `ERRMSG`/`TERM`).
     The file size returned by `DSKOPEN` is kept in `DATSIZE`/`DATSZH`.
   - Reads the 16-byte header and runs **`DATHCHK`**: exactly 16 bytes read,
     carry from BDOS clean, magic `"S6ED"`, version 1, `NUMBLKS` in
     `[1..DATMAX]`, table offset >= 16, and the whole descriptor table
     (`TBLOFF + NUMBLKS*8`) inside the file. Any failure → `.ERRCOR`
     (`"S6ED.DAT corrupt."`) without ever entering Screen 6.
2. **Table-Driven Load (`DATLOAD`, run from `CFGRUN` after `SCRINIT`):**
   - Reopens the file, re-reads and re-validates the header with `DATHCHK`.
   - `DSKSEEK` to the table offset; reads all `NUMBLKS * 8` descriptor bytes
     into `DATTBL` (VARS, 64 B max), verifying carry and byte count.
   - For each descriptor, copied to `DATBLK` for fixed-field access:
     - `BLKID` must be known: `BLKSEG` walks `BLKTBL` (BLKID → segment
       variable pairs; today only `1 → FTRSEG`). Unknown → abort.
     - `LENGTH` in `[1..DATBLEN]` (16384) — the critical clamp: a larger
       length would write past `#C000` into the DOS area and the stack.
     - `LOADADDR` in `[#8000,#C000)` and `LOADADDR + LENGTH <= #C000`.
     - `DATAOFF >= TBLOFF + NUMBLKS*8` (payloads never overlap the table) and
       `DATAOFF + LENGTH <= filesize` (the size `DSKOPEN` reported; files
       >= 64 KB pass trivially since offsets are 16-bit).
     - `DSKSEEK` to `DATAOFF` — DOS 2 via BDOS `_SEEK` (#4A); the DOS 1 path
       writes the FCB random-record field (record size is 1, so it is a byte
       offset), though DOS 1 never reaches this code (`INIT` rejects it in
       `DOSVER`). Documented in `BDOS.Z8A`.
     - Maps the target segment into page 2 (`PUTP2` + `TXSEG` follows),
       `DSKREAD` of `LENGTH` bytes at `LOADADDR`, verifying carry after every
       read and bytes read == `LENGTH`.
   - Closes the handle and restores page 2 to **`TXSEG0`** (not `DEFSEG2`),
     breaking the implicit DATLOAD↔BUFINIT coupling.
3. **Error Abort Path:** `.ERRDAT` / `.ERRCOR` print and exit via `ERRMSG`,
   which drops back to Screen 0 first, so descriptor-level failures detected
   after `SCRINIT` are still reported as visible text.
4. **FCALL stack guard:** `FCALL` now checks `SEGSP >= 8` (4 frames of 2
   bytes) before pushing; overflow is a design error (§4.1) and aborts via
   `ERRMSG` (`"S6ED internal: segment stack overflow."`) instead of silently
   overwriting `DATHAND`.

### 9.4 Empirical Verification & Testing Suite

- **T0 Static (`TEST/static.py`):**
  - `check_feature_discipline`: audits `S6ED.DAT` existence, file size, magic,
    version 1, EOF marker, table pointer, block 0 fields, and
    `filesize == dataoff + length`.
- **Gate Regression (`TEST/gate.py`):**
  - `H6DatMissing`: missing container aborts clean in text mode.
  - `H8`–`H16` (Fase C1, corrupt container must abort with message, never
    hang): `H8` bad magic, `H9` bad version, `H10` `NUMBLKS=0`, `H11` truncated
    header, `H12` truncated descriptor table, `H13` `LENGTH=0`, `H14`
    `LENGTH=16385` with a real 16,385-byte payload (only the length/window
    clamp rejects it), `H15` unknown `BLKID`, `H16` truncated payload.
  - `H17DatPadded`: payload moved behind 64 bytes of padding with `DATAOFF`
    updated — proves the loader seeks instead of reading sequentially.
  - `D8Accents`: Calibrated `GRAPH_GAP = 0.053` ensuring deterministic drift
    across all 20 ms frame phases during keystroke bursts.
- **Selftest Mutations (`TEST/mutations.py`):**
  - `mut/c1-datlen`: removes the LENGTH/window bounds (caught by
    `H14/corrupt-printed`).
  - `mut/c1-datblkid`: unknown IDs load into FTRSEG (caught by
    `H15/corrupt-printed`).
  - `mut/c1-datseek`: sequential payload read without seek (caught by
    `H17/cfg-applied` or a session crash).
  - `mut/f2-datload`: loads the payload at `#9000` instead of the descriptor's
    `LOADADDR` (caught by `G13/cfg-applied`).
  - `mut/f2-datmagic`: corrupts header magic `"S6XX"` (caught by static
    `feature-discipline`).
  - `mut/d8-double`: Drops repeat claim in `TRNGRPH` (caught by `D8/content`).
- **Suite Metrics (2026-09-17, post-C1):**
  - **T0 Static:** 13/13 PASS.
  - **Gate T1/T2:** 207/207 checks across 55 sessions, 0 failed.
  - **Selftest:** 42/42 mutations caught on green baseline (100% detection rate).
  - **Total:** **262 checks, 0 failed (166.6s)**.

---

## 10. Harness notes from the probe session (reusable)

- openMSX 21: `after time N` **requires a command argument** — bare sleeps error
  out and the emulator keeps running; `clock` does not exist in its Tcl.
- DebugDevice is the reliable output channel for headless probes: `OUT (#2E),#63`,
  bytes to `#2F`, capture openMSX stdout. Reading text VRAM after a boot was
  flaky; don't.
- Nextor test machines now exist: `Tides_Rider_MSX2P_128K` / `_256K` in
  `~/.openMSX/share/machines/` (Tides-Rider XML with the mapper sized down),
  booting Nextor 2.1.1 from the SPI-emulated SD in `msx_dma_sw/openmsx/`.
- `PROBE.COM` source lives at `/tmp/probe/PROBE.Z8A`; if it proves useful again,
  promote it into `TEST/` rather than rediscovering it.
- `PROBE2.Z8A` (page-2 BDOS caller probe) saved to `TEST/PROBE2.Z8A`.
  - openMSX stdout pipes stall before machine boot without redirection (`> out 2> err`).
  - MSX-DOS 2 requires ~12.25 emulated seconds to complete boot and execute `AUTOEXEC.BAT` (`set throttle off` completes this in ~40ms wall clock).
  - `AUTOEXEC.BAT` strictly requires DOS CRLF (`\r\n`).
  - Gated breakpoints must verify opcode byte signatures after entry (`0x0100`) to avoid premature hits by COMMAND2/kernel code.

---

## 11. Fase 3a — Window Drawing & Background VRAM Buffer Subsystem

Implemented and verified on 2026-09-17 on branch `feature/window-engine`.

### 11.1 VRAM Architecture in Screen 6 (GRAPHIC 5, 512x212, 4 colors / 2bpp, 128 KB VRAM)

- Scanlines 0..211: Visible screen area (27,136 bytes, Bank 0).
- Scanlines 212..255: Free / reserved for R#23 scroll offset.
- Scanlines 256..511: 4 font tables (Normal, Bold, Italic, Bold+Italic; 32 KB, Bank 0).
- Scanlines 512..1023: **64 KB off-screen VRAM in Bank 1**:
  - Scanlines 512..723: Visible screen background save buffer (`WINBUF_Y EQU 512`).
  - Scanlines 768..979: Off-screen window composition buffer (`WINCOMP_Y EQU 768`).

### 11.2 Instant Hardware Save, Off-Screen Composition & Fast Blit via `HMMM`

- `HMMM` (opcode `#D0`) performs unformatted byte-transfer VRAM-to-VRAM copy.
- In Screen 6, 1 byte = 4 pixels. Coordinates `WINX` and `WINW` are byte-aligned (`WINX & ~3`, `(WINW + 3) & ~3`).
- **Save (`WINSAV`):** `HMMM` from $(X, Y)$ to $(X, 512 + Y)$ with $(W, H)$.
- **Compose:** Frame, backgrounds, separator lines, multi-weight text, and buttons are composed entirely off-screen at $(X, 768)$ in Bank 1. Eliminates progressive cell-by-cell drawing artifacts.
- **Instant Pop-Up (`WINSHOW`):** Single `HMMM` from $(X, 768)$ to visible $(X, Y)$ with $(W, H)$ followed by `VDPWAIT` (~3.2 ms).
- **Restore (`WINRST`):** `HMMM` from $(X, 512 + Y)$ to $(X, Y)$ with $(W, H)$, followed by `VDPWAIT` (~3.2 ms).
- **Zero RAM footprint:** Preserves text, selection, and cursor underneath without CPU copy loops or RAM allocation.

### 11.3 Multi-Weight Typography & Color 3 Highlights

- **4 Font Weights:** `WINCHTR` selects source VRAM scanline via `.SYTBL` (`FNORM_SY=256`, `FBOLD_SY=320`, `FITAL_SY=384`, `FBI_SY=448`) from variant index (0..3).
- **Color 3 (Amber/Gold Highlight) via `TOR` LOGOP:**
  - Screen 6 2bpp pixel encoding: Color 0=`%00`, Color 1=`%01`, Color 2=`%10`, Color 3=`%11`.
  - Font glyphs have `%01` pixels. When blitted over Color 2 (`COL_UI`, `%10`) with `TOR` (Transparent OR):
    $\%01 \mid \%10 = \mathbf{\%11}$ (Color 3).
  - Title and Button text blitted via `WINSTR3` render in Color 3 highlight with zero runtime palette alteration.
  - Top window highlight, title separator bar, and button outer border drawn in Color 3 (`COL_HI`).

### 11.4 Window Engine (`WINDOW.Z8A` in `FTRSEG`)

- `WINDOW.Z8A` packaged into `S6ED.DAT` Block 0 (`FTRSEG`), phased at `#8000` right after `CFG.Z8A`.
- Routines:
  - `WINSAV`: Sets up `VDPCMBLK` and issues `HMMM` to Bank 1 save buffer ($Y=512$).
  - `WINSHOW`: Blits completed window from Bank 1 composition buffer ($Y=768$) to visible screen ($Y=WINY$).
  - `WINRST`: Sets up `VDPCMBLK` and issues `HMMM` back to visible VRAM from save buffer.
  - `WINBOX`: Draws outer frame in Color 2, top accent highlight in Color 3, title bar in Color 2, bottom accent separator in Color 3, and title text in Bold + Color 3 (`TOR`).
  - `WINCHTR`: Blits single glyph with variant lookup and configurable LOGOP (`TIMP` vs `TOR`).
  - `WINSTR` / `WINSTR3`: Blits string with variant index in `TIMP` or `TOR`, advancing `DE` past the last character for chained inline styles.
  - `WINPRN`: Relative character coordinate printing into off-screen composition buffer.
  - `WINBTN` / `WINBTS`: Renders a button ($58 \times 14$ border, $56 \times 12$ body, centered bold text). `WINBTN` is the normal style (Color 3 border, Color 2 body, text in `TOR`); `WINBTS` takes a style in `A` (0=normal, 1=selected: Color 3 body, text in `TIMP`), kept in `WINBST`. Used for option selection since Fase 3b.
  - `WINOPEN`: Enforces byte alignment, saves visible background, and initializes window box in composition buffer.
  - `WINCLOS`: Restores background via `WINRST`.
  - `DOABT`: Composes About dialog off-screen using mixed typographic styles:
    - `"S6ED"` in Bold+Italic + `" - MSX2 Screen 6 Text Editor"` in Normal.
    - `"Version 0.1 "` in Bold + `"(Experimental)"` in Italic.
    - `"Display: "`, `"Fonts:   "`, `"Memory:  "` in Bold with values in Normal.
    - Centered `[  OK  ]` button in Color 3 / Color 2.
    - Calls `WINSHOW` for instant ~3.2 ms popup, handles modal loop (`ENTER`, `SPACE`, `ESC`), and calls `WINCLOS`.

### 11.5 Action Wiring (`ACTION.Z8A`)

- `ACTHELP` (action 24, bound to `F1`) wired to `LD A, (FTRSEG); LD HL, DOABT; JP FCALL`.
- Added `WINPOLL` subroutine to `UI.Z8A` in Core (Page 1) to poll `CHKCLK`, `CHSNS`, and `CHGET` for modal dialogs.
- Total added to `S6ED.COM`: 32 bytes (`HMMM` + `WINPOLL` + `ACTHELP` dispatch). Everything else resides in `S6ED.DAT` (`FTRSEG`).

### 11.6 Empirical Read-Back Verification

- Added `H7AboutDialog` to `TEST/gate.py`:
  - Opens About dialog with `F1`.
  - Asserts VRAM was modified while dialog is open (`H7/dialog-displayed`).
  - Asserts Color 3 (amber) highlights are present in VRAM during display (`H7/color-highlight`, $> 1,000$ px).
  - Dismisses with `RETURN` and asserts VRAM is byte-for-byte restored (`H7/restore-return`).
  - Opens with `F1`, dismisses with `SPACE`, asserts byte-for-byte restore (`H7/restore-space`).
  - Opens with `F1`, dismisses with `ESC`, asserts byte-for-byte restore (`H7/restore-escape`).

### 11.7 Fase 3b — Quit Confirmation Dialog: Selectable Options (2026-09-18)

The first multi-option modal dialog, and the foundation of the future menu
system: option selection with two visual button states.

- `DOQIT` (in `WINDOW.Z8A`, FTRSEG): modal 200×64 dialog at (156,74), title
  `"Quit S6ED"`, message `"Exit to MSX-DOS?"`, and a bold
  `"Unsaved changes!"` line shown only when `MODIFIED` is set.
- **Two selectable options** rendered as buttons (`[  YES  ]` / `[  NO  ]`).
  Selection state lives in `WINSEL` (0=YES, 1=NO; default NO — an accidental
  ESC never drops the document), the dialog result in `WINRES` (0=cancel,
  1=confirm). Both live in `VARS.Z8A` with `WINBST`.
- Button styles via `WINBTS` (§11.4): normal = Color 3 border / Color 2 body /
  bold `TOR` text; selected = Color 3 body / bold `TIMP` text.
- Keys: `LEFT`/`RIGHT` move the selection (only the two buttons are repainted
  in the composition buffer, then `WINSHOW` re-blits — no tearing),
  `ENTER`/`SPACE` activate the selected option, `Y`/`N` are accelerators,
  `ESC` cancels.
- `ACTQUIT` (ESC / Ctrl+Q in every keymap) now `CALL FCALL`s `DOQIT` and only
  falls through to `TERM` when `WINRES` = 1. With an active selection, ESC
  still just drops it (`ACTDSEL`), as before.
- Tests: `H19QuitDialog` (dialog displayed, default-NO button pixels, LEFT
  navigation repaint, ESC cancel with byte-for-byte restore, warning band
  clean on a clean buffer, Y exits to Screen 0, `WINRES` on both paths),
  `H20QuitDirty` (`MODIFIED` set, warning rendered glyph-for-glyph in bold,
  N cancels). `G12` updated to confirm the dialog with `Y`. Mutations
  `wq-direct`, `wq-defsel`, `wq-nav`, `wq-yes`. `make testall`: **290 checks,
  0 failed (260 s)**.


