# FTRBASE Budget Guard — Companion to SPEC_S2ED_WINDOW_MENU.md

> **Status:** Approved 2026-09-21. Guards implemented in Phase W1 (branch `feat/s2ed-window-engine`).

## The Asymmetry

| Target | `FTRBASE` | `FTRTOP` | Total | After windows |
|---|---|---|---|---|
| S6ED | `#8000` | `#C000` | 16,384 B | ~9,600 B free |
| S2ED | `#9C00` | `#B000` | 5,120 B | ~200 B free |

Measured from `.sym` (2026-09-21):

| Target | `FTRBLEN` (used) | `DATBLEN` (budget) | Free |
|---|---|---|---|
| S6ED | 4,782 B (`#12AE`) | 16,384 B (`#4000`) | 11,602 B |
| S2ED | 1,007 B (`#03EF`) | 5,120 B (`#1400`) | 4,113 B |

## Protection: Three Layers

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
; FTR-BUDGET: S6ED ~9,600 FREE, S2ED ~200 FREE (2026-09-21)
```

Forces the developer to **look** at both targets' budgets before adding shared
feature code.

### Layer 3: Documentation

#### In `CLAUDE.md`:

```
- **FTRBASE budget is target-dependent and radically different.**
  S6ED (FTRBASE=#8000, FTRTOP=#C000): 16,384 B total, ~9,600 B free.
  S2ED (FTRBASE=#9C00, FTRTOP=#B000): 5,120 B total, ~200 B free.
  Any new FTRBASE passenger MUST verify it fits on BOTH targets.
  The build enforces FTRFREE >= 128; check FTRFREE in the .sym files.
```

#### In `.memory/project_s2ed.md`:

```
### FTRBASE is nearly full (after window/menu system)

After the window engine, menu subsystem, and dialogs, S2ED's FTRBASE has
~200 bytes free out of 5,120. This is not a bug — it is the cost of sharing
VIDSEG with the video shadows on a machine with zero spare mapper segments.
Any new FTRBASE passenger must fit within this budget, or one of these must
give:
1. The save buffer moves to page 3 RAM (frees ~1,600 B but adds complexity)
2. The feature moves to a second block in S2ED.DAT (loaded on demand)
3. The feature is S6ED-only (wrapped in IFNDEF S2ED)

The build guard ASSERT FTRFREE >= 128 will catch an overflow before it ships.
```

## Why Three Layers

| When | What catches it |
|---|---|
| Writing code | `FTR-BUDGET` comment requirement (Layer 2 + Layer 3) |
| Building | `ASSERT FTRFREE >= 128` (Layer 1 — hard fail) |
| Review | `FTRFREE` in `.sym` (Layer 1 — visible to grep) |
| After the fact | `ftr-budget` static test (Layer 2 — CI-level) |

The comment-based guard is the weakest but the earliest. The ASSERT is the
strongest. Together they form a net.
