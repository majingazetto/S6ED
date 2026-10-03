# S6ED / S2ED — Settings Feedback & Browser Focus Polish Plan

Date: 2026-10-03  
Status: **APPROVED BY USER — PENDING IMPLEMENTATION**  
Scope: Both targets (MSX2 S6ED & MSX1 S2ED)

---

## 1. Executive Summary

This plan details two targeted UI polish improvements for the SXED editor family:
1. **Real-time Save Feedback for Settings:** Mirroring the `FILESAVE` workflow, show `"Saving..."` on the status bar before `CFGSAVE` and `"[SAVED]"` (or `"[SAVE ERROR]"`) upon completion, while strictly preserving S2ED's `FTRSEG` memory headroom (`ASSERT FTRFREE >= 128`).
2. **High-Contrast Multi-Theme File Browser Selection in S6ED:** Eliminating the white-on-yellow illegibility trap in S6ED's file browser grid by utilizing `VDP_TXOR` transparent XOR font blitting (`WINSTRX`), achieving 100% visual parity with S2ED's `#4B` inverted palette across all 6 themes.

---

## 2. Feature 1: Settings Save Feedback Subsystem

### 2.1 Problem & Motivation
In `FILESAVE` (`CODE/SRC/CORE/FILEIO.Z8A`), when the user saves a document:
1. The status bar immediately displays `"Saving..."` via `DRWSTAT` before disk I/O starts.
2. The file is created and written.
3. Upon success, the status bar displays `"[SAVED]"`; on disk error, `"[SAVE ERROR]"`.
4. The message automatically clears on the next user keystroke (`INPUT.Z8A:94`).

In contrast, accepting changes in `DOSETT` (`[  OK  ]` in `S6/WINDOW.Z8A` and `S2/WINDOW.Z8A`) invokes `CFGSAVE` silently, with no indication on the status bar.

### 2.2 Architecture & Flow
```
User presses [ OK ] in DOSETT
           │
           ▼
Commit settings to live variables (APPLYTHM, SHDWCLR, etc.)
           │
           ▼
Set STATMSG = "Saving..." and CALL DRWSTAT (visible below dialog)
           │
           ▼
CALL CFGSAVE (Disk I/O: _CREATE, serialize keys, _CLOSE)
           │
     ┌─────┴─────┐
  CY = 0       CY = 1
     │           │
     ▼           ▼
STATMSG =     STATMSG =
"[SAVED]"   "[SAVE ERROR]"
     │           │
     └─────┬─────┘
           ▼
CALL WINCLOS (Restores text canvas underneath)
           │
           ▼
Return to ACTSETT in ACTION.Z8A (Page 1)
           │
           ▼
CALL DRWMENU & CALL DRWSTAT (Commits status bar message)
```

### 2.3 Memory Budget Discipline (S2ED `FTRSEG` Guard)
- **Constraint:** In S2ED, `FTRFREE` is currently **154 bytes** (`ASSERT FTRFREE >= 128`). We only have **26 bytes** of headroom before hitting the hard assertion.
- **Solution:**
  - Share the strings (`STRSAVG = "Saving..."`, `STRSAVD = "[SAVED]"`, `STRSERR = "[SAVE ERROR]"`) and `SETMSG` from **resident Page 1** (`XSEG.Z8A` / `FILEIO.Z8A`), where S2ED has **1,526 bytes free** (`TPAFREE`).
  - In `DOSETT`, the call sequence takes only ~16 net bytes in `FTRSEG`, keeping S2ED's `FTRFREE` at **~138 bytes ($\ge 128$)**.
  - In `ACTSETT` (`ACTION.Z8A`), `CALL DRWSTAT` is already present and will paint the outcome message onto the screen.

---

## 3. Feature 2: High-Contrast Multi-Theme Browser Selection in S6ED

### 3.1 Problem & Root Cause Analysis
- **S2ED (MSX1 SCREEN 2):**
  - Unselected slot: `VCOLWIN = #F4` (White text on Dark Blue paper).
  - Selected slot: `VCOLBSEL = #4B` (**Dark Blue text on Light Yellow paper**).
  - The foreground ink switches to dark blue, providing sharp, comfortable contrast.
- **S6ED (MSX2 SCREEN 6):**
  - Unselected slot: `COL_UI` background (Dark Blue) + `WINSTR` in `COL_FG` (White).
  - Selected slot: Background changes to `COL_HI` (Color 3, Yellow).
  - **The Bug:** `WINSTR` uses `VDP_TIMP`, which draws glyph ink in `COL_FG` (Color 1, **White**).
  - **Result:** White text (7,7,7) on Yellow paper (7,7,0). Near-zero luminance contrast, rendering the selected filename almost completely illegible on CRT and LCD.

### 3.2 Technical Solution: `WINSTRX` via `VDP_TXOR`
Introduce `WINSTRX` in `CODE/SRC/S6/WINDOW.Z8A`:
```z80
WINSTRX         PUSH    AF
                LD      A, VDP_TXOR     ; #0B: TRANSPARENT XOR
                LD      (WINOP), A
                POP     AF
                JR      WINSTR.DOSTR
```

When rendering a selected slot in `CODE/SRC/S6/BROWSER.Z8A`:
1. The background box is filled with `COL_HI` (`%11`) via `.RECT`.
2. The filename is blitted using `WINSTRX` (`VDP_TXOR`):
   - Transparent glyph pixels (`%00`): $\%11 \oplus \%00 = \%11$ (`COL_HI` background stays intact).
   - Opaque glyph ink (`%01`): $\%11 \oplus \%01 = \mathbf{\%10}$ (**`COL_UI`, Dark Blue**).

### 3.3 Multi-Theme Behavior Verification
Because every theme in S6ED configures Color 2 (`COL_UI`) and Color 3 (`COL_HI`) as complementary contrasting pairs, `VDP_TXOR` produces optimal contrast across all 6 themes:

| Theme | Background (`COL_HI`, `%11`) | Glyph Ink (`%11 \oplus \%01 = \%10`) | Visual Result |
|---|---|---|---|
| **DEFAULT** | Bright Yellow (`#70, #07`) | Dark Blue (`#17, #02`) | Dark blue text on bright yellow paper (matches S2ED `#4B`) |
| **AMBER** | Bright Amber (`#70, #06`) | Dark Amber (`#20, #01`) | Dark amber text on bright amber paper |
| **GREEN** | Bright Green (`#40, #07`) | Dark Green (`#00, #02`) | Dark green text on bright neon green paper |
| **MSX** | Bright Yellow (`#70, #07`) | Light Blue (`#27, #04`) | Blue text on bright yellow paper |
| **MONO** | Light Grey (`#77, #07`) | Dark Grey (`#44, #04`) | Dark grey text on light grey paper |
| **LIGHT** | Dark Blue (`#06, #02`) | Grey (`#55, #05`) | Grey text on dark blue paper |

---

## 4. Test & Verification Plan

1. **Static Quality Gates (`make check`):**
   - Assert all 19 static invariant checks pass (labels $\le 8$ chars, uppercase mnemonics, `statbuf-term`, `ftr-budget`).
   - S2ED `FTRFREE >= 128` explicitly confirmed.
2. **Headless openMSX Gate Suite:**
   - Case `H34-browse-open` (`H34/drawn`): Verifies `sel_px == vram.COL_HI` is preserved.
   - Case `H37-settings`: Verifies status bar receives `"[SAVED]"` post-commit.
   - S2 Gate Suite: `make test-s2` (251 checks).
   - Full regression suite: `make testall` (951 checks, 200/200 mutations caught).
3. **Empirical Visual Audit:**
   - Screenshot / VRAM dump of S6ED file browser in Default, Amber, and Green themes confirming razor-sharp legibility of selected files.
