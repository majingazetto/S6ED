# S6ED — Inter-Segment Infrastructure & Container Architecture

Date: 2026-09-17 · Status: **IMPLEMENTED & EMPIRICALLY VERIFIED (Fase 1a, Fase 1b & Fase 2 complete)**
Scope: Fase 1a (boot-time segment budget, mandatory minimum) + Fase 1b (inter-segment
call machinery + first resident feature) + Fase 2 (`S6ED.DAT` standalone multi-segment container loader).
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
  Overflow is a design error: `BRK` in DEBUG builds.

### 4.2 Core → feature: only through `FCALL`

`FCALL`: `A` = segment, `HL` = entry address (`#8000`-relative label).
Pushes `{TXSEG, HOMESEG}`, banks the feature (`PUTP2`, `TXSEG` follows), sets
`HOMESEG`, `CALL` the entry, and on return **restores the previous page-2 segment**
and pops the pair.

### 4.3 Feature → core: only through stubs

One stub per core routine, living **in the core** (one copy serves every feature):

```
STB_X   CALL  X
        LD    A, (HOMESEG)
        LD    (TXSEG), A
        CALL  PUTP2
        RET
```

The re-bank is **unconditional**: BDOS page-2 behaviour across calls is not assumed
(this is also the defence for the Fase 2 .DAT loader). Stub cost ≈ 150 T-states,
irrelevant against any paint path.

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

## 9. Fase 2 — `S6ED.DAT` Standalone Multi-Segment Container Loader (Implemented 2026-09-17)

Fase 2 physically decouples feature modules from the executable `S6ED.COM` into an
external container file **`S6ED.DAT`**. The `.COM` image drops down to 14,239 bytes,
freeing precious TPA RAM while allowing future features to grow up to 16 KB per segment.

### 9.1 Container File Layout (`S6ED.DAT`)

The container consists of a 16-byte global header, a variable-length Block
Descriptor Table, and contiguous binary payloads. All multi-byte numeric fields
are 16-bit Little-Endian.

```
+-------------------------------------------------------------+
| Global Header (16 bytes)                                    |
|   0..3:   Magic identifier ASCII "S6ED"                     |
|   4..5:   Format version (0x0001, 2 bytes reserved)         |
|   6:      MSX-DOS / CP/M EOF marker (0x1A)                  |
|   7:      Global flags (0x00)                               |
|   8..9:   Block count (0x0001)                              |
|   10..11: Offset pointer to Block Table (0x0010 = 16 bytes) |
|   12..15: Reserved (0x00000000)                             |
+-------------------------------------------------------------+
| Block Descriptor Table (Entry 0: 8 bytes)                   |
|   0..1:   BLKID (0x0001: Configuration Engine)              |
|   2..3:   FLAGS (0x0001: Mandatory boot-load)              |
|   4..5:   LOADADDR (0x8000: Base address in Page 2)         |
|   6..7:   LENGTH (Payload byte length, e.g. 1,082 bytes)    |
|   8..9:   DATAOFF (File offset to payload = 24 bytes)       |
+-------------------------------------------------------------+
| Binary Payload Block 0 (CFG.Z8A assembled at #8000)         |
|   Size: 1,082 bytes                                         |
+-------------------------------------------------------------+
```

Total container size for Fase 2: **1,106 bytes** (16B header + 8B descriptor 0 + 1,082B CFG payload).

### 9.2 Build Pipeline

The container is emitted directly by `sjasmplus` using rotating `OUTPUT` directives:
1. `CODE/SRC/S6ED.Z8A` emits `S6ED.COM` up to `OUTEND` and `VARS.Z8A`.
2. Directives switch output:
   ```z80
   OUTPUT "S6ED.DAT"
   ; Emit 16-byte header
   ; Emit 8-byte block descriptor 0
   ; PHASE #8000 -> INCLUDE CFG.Z8A -> DEPHASE
   ```
3. `CODE/Makefile` declares `S6ED.DAT` as a primary build artifact and package target.

### 9.3 Loader Mechanics (`CHKDAT` & `DATLOAD` in `CODE/SRC/XSEG.Z8A`)

1. **Text-Mode Pre-Check (`CHKDAT`):**
   - Called in `INIT` immediately after `SEGRESV` while still in text mode (SCREEN 0).
   - Attempts `DSKOPEN` on `S6ED.DAT`. If missing (`CY=1`), branches to `.ERRDAT`
     and exits cleanly to DOS via `ERRMSG` / `TERM` without ever entering Screen 6
     or uploading fonts to VRAM, eliminating screen flicker.
   - If present, closes file via `DSKCLOSE` and proceeds with normal initialization.
2. **Handle Safety:** `DATHAND DEFB 0` in `VARS.Z8A` stores the file handle across
   calls to `DSKREAD`, which clobbers register `B` under MSX-DOS 2.
3. **Header Ingestion:** In `DATLOAD`, reads 16-byte header into `DATHDR`; validates:
   - Exactly 16 bytes read.
   - Magic ID == `"S6ED"`.
   - Version == 1 (`#0001`).
   - Block count $\ge 1$.
4. **Block Ingestion:** Reads 8-byte descriptor 0 into `DATBLK`; validates:
   - Exactly 8 bytes read.
   - Block length $> 0$ and $\le 16384$.
5. **Direct Page 2 Mapping & Load:**
   - Maps `(FTRSEG)` into page 2 (`#8000-#BFFF`) via `PUTP2`.
   - Reads payload directly into `LOADADDR` (`#8000`) using `LENGTH` bytes.
   - Closes handle via `(DATHAND)` and `DSKCLOSE`.
   - Restores `DEFSEG2` into page 2 via `PUTP2`.
6. **Error Abort Path:**
   - `.ERRDAT`: If `S6ED.DAT` is missing, prints `"S6ED.DAT not found."` and exits.
   - `.ERRCOR`: If corrupted (bad magic, truncated read), prints `"S6ED.DAT is corrupted."` and exits.
   - Both paths call `ERRMSG`, which drops back to Screen 0 with `PUSH DE`/`POP DE`
     around BIOS `CHGMOD` to ensure the error string pointer in `DE` is preserved.

### 9.4 Empirical Verification & Testing Suite

- **T0 Static (`TEST/static.py`):**
  - Enhanced `check_feature_discipline`: audits `S6ED.DAT` existence, file size,
    16-byte magic `"S6ED"`, version 1, EOF marker `0x1A`, table pointer, block 0
    fields, and guarantees `filesize == dataoff + length`.
- **Gate Regression (`TEST/gate.py`):**
  - `H6DatMissing`: Validates clean text-mode error exit to DOS (`SCRRDY=0`) with
    error message when `S6ED.DAT` is missing from disk.
  - `D8Accents`: Calibrated `GRAPH_GAP = 0.053` ensuring deterministic drift across
    all 20ms frame phases during keystroke bursts.
- **Selftest Mutations (`TEST/mutations.py`):**
  - `mut/f2-datload`: Alters load target from `#8000` to `#9000` (caught by `G13/cfg-applied`).
  - `mut/f2-datmagic`: Corrupts header magic `"S6XX"` (caught by static `feature-discipline`).
  - `mut/d8-double`: Drops repeat claim in `TRNGRPH` (caught by `D8/content`).
- **Suite Metrics (2026-09-17):**
  - **T0 Static:** 13/13 PASS.
  - **Gate T1/T2:** 186/186 checks across 45 sessions, 0 failed.
  - **Selftest:** 39/39 mutations caught on green baseline (100% detection rate).
  - **Total:** **238 checks, 0 failed (133.8s)**.

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

### 11.1 VRAM Architecture in Screen 6 (G5, 512x212, 4 colors / 2bpp, 128 KB VRAM)

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
  - `WINPRN` / `WINPRN3`: Relative character coordinate printing into off-screen composition buffer.
  - `WINBTN`: Renders button with Color 3 border ($58 \times 14$), Color 2 body ($56 \times 12$), and centered text in Bold + Color 3 (`TOR`).
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


