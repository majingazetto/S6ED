# S6ED — Fase 1: Boot Segment Accounting & Inter-Segment Infrastructure

Date: 2026-09-16 · Status: **SPEC, agreed — not yet implemented**
Scope: Fase 1a (boot-time segment budget, mandatory minimum) + Fase 1b (inter-segment
call machinery + first resident feature). Roadmap context: `informe_directorio_segmento_s6ed.md` §6.

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

The feature modules are assembled inside the `.COM` image wrapped in a
**single global `PHASE #8000` / `DEPHASE` container block** (`FTRBLOB`):

```z80
FTRBLOB:
        PHASE   #8000
FTRSTART:
        INCLUDE CFG.Z8A
        ; Future passengers appended here sequentially:
        ; INCLUDE TOKEN.Z8A
        ; INCLUDE MENU.Z8A
        ; INCLUDE VI.Z8A
FTREND:
        DEPHASE
FTRBLEN EQU     FTREND - FTRSTART
        ASSERT  FTRBLEN <= 16384        ; Total feature segment budget
```

**Critical architecture rule (agreed 2026-09-16):** Do **not** use per-module
`PHASE #8000` / `DEPHASE` wrappers. A per-module wrapper would reset the logical
assembly counter to `#8000` for each file, causing multiple modules in `FTRSEG`
to collide and overwrite each other's addresses. A single container block ensures
all feature modules assemble sequentially into the `#8000`–`#BFFF` address space.

At boot, a single routine `F1COPY` LDIRs the entire container blob (`FTRBLEN` bytes)
into `FTRSEG` through the page-2 window. Fase 2 replaces this copy with the
`S6ED.DAT` loader without touching the modules themselves.

## 5. First passenger: `CFG.Z8A` (resident in `FTRSEG`)

Why CFG: cold path (runs once at boot), self-contained (~1,082 bytes).

### 5.1 Empirical Verification: BDOS file I/O from Page 2 (2026-09-16)

Before restructuring, the hypothesis that MSX-DOS 2 supports BDOS file operations
from page 2 was **verified empirically** with `TEST/PROBE2.Z8A` on both
`Boosted_MSX2_EN` (2 MB) and the reference stock 128 kB `Philips_NMS_8250`:
- Code running at `#8000` (in a mapper segment).
- Filename string located at `#80xx` (inside the page-2 mapper segment).
- DMA target located in page 1 (`#0277`).
- Operations: `_OPEN` (#43), `_READ` (#48), `_CLOSE` (#45) — read self and
  verified byte 0 = `#C3` (JP).
- **Result: 100% PASS** on both machines.

### 5.2 Module Relocation without Stubs

Because page 1 code is always mapped, any routine in `FTRSEG` (`#8000+`) can
call core routines in page 1 (`DSKOPEN`, `DSKREAD`, `DSKCLOSE`, `SETPAL`,
`KMAPSW`) via standard direct Z80 `CALL` / `JP`. Intermediate core stubs
are not required for the first passenger.

Changes:
- `CFG.Z8A` included inside the global `FTRBLOB` (`PHASE #8000` block).
- `INIT` change: `CALL CFGLOAD` → `CALL CFGRUN` (core wrapper in `XSEG.Z8A`:
  `F1COPY` + `FCALL CFGLOAD`). `FTRSEG` stays resident (§1).

## 6. Tests (per AGENTS.md rules)

**T0 static (`TEST/static.py`):**
- Lint: no reference to `PUTP2` / `RECBANK` / `DIRBANK` / `GETP2` / `SEGGET` /
  `FRESEG` in a feature module; every `CALL`/`JP` target from `CFG.Z8A` resolves
  inside the module or to a `STB_*` symbol (checked against `S6ED.sym`).
- `ASSERT` blob ≤ 16 KB present; `CFGSEG` phased at `#8000`.

**Gate (`TEST/gate.py`):**
- **G13 (new)** — feature residency: at a `MAINLOOP` breakpoint gated on the code
  signature, `SEGCNT == 2` and `SEGTBL[0..1] == [DIRSEG, FTRSEG]` on the 128 kB
  machine; config values from a spaced-keys fixture are applied (overlaps G8, kept).
- **G3 updated** — 128 kB capacity 202 → **101** lines. Documented consequence of
  the resident `FTRSEG`, not a regression to fix.
- G1/G2/G8/G9 stay green: banking discipline did not break text integrity, saving
  or CFG parsing.

**Selftest (`TEST/mutations.py`):**
- `mut/f1-stub-norebank` — a stub that skips the re-bank (`CALL PUTP2` removed):
  the `RET` lands in the wrong segment → G8/G13 must go red. Green baseline first
  (Rule 1).
- `mut/f1a-probe-leak` — the boot probe forgets to free its extras: 128 kB
  capacity collapses → G3 red.

## 7. Explicitly out of scope

- `S6ED.DAT` loader, `.DAT` header format, per-priority feature accounting (Fase 2).
- Feature migrations: tokenizer, Vi command line, menus, keymap bundles (Fase 3).
- Tabs / two documents (Fase 4).
- Mailbox implementation (contract only, §4.4).
- Status-bar user messaging for refused edits (still unwired; boot messages in §3
  are text-mode and unrelated).

## 8. Harness notes from the probe session (reusable)

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

