# FTRBASE Budget Guard — Companion to SPEC_S2ED_WINDOW_MENU.md

> **Status:** Approved 2026-09-21. Guards implemented in Phase W1 (branch `feat/s2ed-window-engine`). Updated 2026-09-22: the window save buffer left the container for the TPA, and a fourth guard (`tpa-chain`) covers the TPA the same way.

## The Asymmetry

| Target | `FTRBASE` | `FTRTOP` | Total |
|---|---|---|---|
| S6ED | `#8000` | `#C000` | 16,384 B |
| S2ED | `#9C00` | `#B000` | 5,120 B |

Measured from `.sym` (2026-09-22, after W1 and the save-buffer move):

| Target | `FTRBLEN` (used) | `DATBLEN` (budget) | `FTRFREE` | `TPAFREE` |
|---|---|---|---|---|
| S6ED | 4,782 B (`#12AE`) | 16,384 B (`#4000`) | 11,602 B | 4,266 B |
| S2ED | 2,138 B (`#085A`) | 5,120 B (`#1400`) | 2,982 B | 3,237 B |

S2ED's figure includes the 1,536 B the window background save buffer returned
to the container on 2026-09-22 when it moved to the TPA chain. The menu
subsystem (~1,200 B) still has to fit, and now does with room to spare.

## Protection: Three Layers, Plus One for the TPA

### Layer 1: Assembly-Time Guard (`ASSERT`)

```asm
; IN BOTH S2ED.Z8A AND S6ED.Z8A (AFTER BLK0END):
FTRFREE         EQU     DATBLEN - BLK0LEN
                ASSERT  FTRFREE >= 128, "FTRBASE HEADROOM < 128 BYTES"
```

- `FTRFREE` appears in both `.sym` files → `grep FTRFREE *.sym` shows both budgets.
- The `>= 128` threshold makes the build **fail** before someone discovers the
  overflow at runtime.

### Layer 2: Static Test Guard (`TEST/static.py`)

`ftr-budget`: Fail if any `CORE/*.Z8A` file contains `FCALL` without a
`FTR-BUDGET` comment within ±5 lines. Comment convention:

```asm
; FTR-BUDGET: S6ED 11,602 B FREE, S2ED 2,982 B (2026-09-22)
```

Forces the developer to **look** at both targets' budgets before adding shared
feature code.

### Layer 2b: The TPA Has the Same Problem, and the Same Kind of Guard

The container is not the only place where one target's allocation looks like
free space to the other. The TPA does too — `WSVBUF` is declared `IFDEF S2ED`,
so on S6ED those 1,536 bytes are simply not there. The difference is that TPA
allocations are **additive**: they chain off `ENDVARS` and off each other, so
nothing needs to know an address and a target that does not declare a buffer
just gets a shorter chain.

`tpa-chain` (`TEST/static.py`) keeps it that way. It reads the block below
`ENDVARS` in `VARS.Z8A` and fails if any `EQU` there names a literal address
instead of building on the chain, if `TPATOP` / `TPAFREE` go missing, if the
`ASSERT TPATOP <= TXPAGE` disappears, or if either `.sym` reports a `TPAFREE`
outside `(0, #4000)`.

It cannot prove two buffers do not overlap — that is a runtime property.
Gate case `S2-12-dialog-undo` measures it: it types a burst, opens and closes
the About dialog, and undoes. Mutation `s2-wsvbuf-undo` puts `WSVBUF` back on
top of the undo ring and the case goes red, while the dialog itself still
opens and restores byte for byte.

### Layer 3: Documentation

#### In `CLAUDE.md`:

```
- **FTRBASE budget is target-dependent and radically different.**
  S6ED (FTRBASE=#8000, FTRTOP=#C000): 16,384 B total, 11,602 B free.
  S2ED (FTRBASE=#9C00, FTRTOP=#B000): 5,120 B total, 2,982 B free.
  Any new FTRBASE passenger MUST verify it fits on BOTH targets.
  The build enforces FTRFREE >= 128; check FTRFREE in the .sym files.
  Runtime buffers belong in the TPA chain at the foot of VARS.Z8A, not in
  the container: extend the chain, never name an address.
```

#### In `.memory/project_s2ed.md`:

```
### FTRBASE is nearly full (after window/menu system)

After the window engine, menu subsystem, and dialogs, S2ED's FTRBASE has
~200 bytes free out of 5,120. This is not a bug — it is the cost of sharing
VIDSEG with the video shadows on a machine with zero spare mapper segments.
Any new FTRBASE passenger must fit within this budget, or one of these must
give:
1. The save buffer moves to the TPA (done 2026-09-22, freed 1,536 B)
2. The feature moves to a second block in S2ED.DAT (loaded on demand)
3. The feature is S6ED-only (wrapped in IFNDEF S2ED)

The build guard ASSERT FTRFREE >= 128 will catch an overflow before it ships.
```

## Why Layers

| When | What catches it |
|---|---|
| Writing code | `FTR-BUDGET` comment requirement (Layer 2 + Layer 3) |
| Building | `ASSERT FTRFREE >= 128` (Layer 1 — hard fail) |
| Review | `FTRFREE` in `.sym` (Layer 1 — visible to grep) |
| After the fact | `ftr-budget` static test (Layer 2 — CI-level) |
| Placing a runtime buffer | `tpa-chain` static test (Layer 2b) |
| Two buffers overlapping | `S2-12-dialog-undo` gate case (runtime) |

The comment-based guard is the weakest but the earliest. The ASSERT is the
strongest. Together they form a net.
