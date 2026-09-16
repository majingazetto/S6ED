# S6ED Development Guidelines & Testing Framework

This document outlines the architectural conventions, testing standards, and anti-regression rules for S6ED. All contributors and AI assistants working on this codebase must adhere strictly to these principles.

---

## 1. The Four Anti-Regression Rules

The S6ED test suite (`TEST/`) is built on historical defects. To prevent past failures (such as the duplicate GRAPH accent delivery and silent test pass-throughs) from recurring, follow these four cardinal rules:

### Rule 1: Mandatory Green Baseline for Mutation Testing
* **The Rule:** A mutation only proves test efficacy if the check it targets was **100% GREEN on the clean build**.
* **Why:** A mutation that triggers a check which was already failing provides a false positive (`PASS`), masking regressions.
* **Practice:**
  - `TEST/selftest.py` automatically enforces this via baseline verdicts before running mutated builds.
  - Never run mutations in isolation without establishing a clean baseline.
  - Always run `make testall` before declaring an integration or refactoring complete.

### Rule 2: Deterministic Testing of Race Conditions & Timing Windows
* **The Rule:** Tests covering interrupt timing, matrix scans, or buffer concurrency must be completely deterministic.
* **Why:** The emulator CPU is cycle-accurate, but dependencies on the host machine (e.g. host RTC clock) introduce arbitrary phase drift between runs, causing intermittent test results.
* **Practice:**
  - In timing-sensitive test cases (like `D8`), **disable host clock timers** in the test configuration: `CLOCK=0`.
  - **Never test a race window with a single isolated keystroke.** A single press rarely lands in a microsecond ISR window. Use phase-sweeping bursts (e.g., repeating the key sequence 4 times at 50 ms intervals) to walk through the entire phase range of the main loop and ISR.
  - Use the `tail=` override in `press()` to micro-adjust post-release delays when targeting precise timing windows.

### Rule 3: Dual-Path Delivery Arbitration (First-Come, First-Served)
* **The Rule:** When supporting regional hardware differences with parallel input delivery mechanisms (e.g., direct keyboard matrix polling vs. BIOS keyboard buffer ISR), delivery must follow a strict **First-Come, First-Served** claim mechanism.
* **Why:** In MSX, Japanese machines drop certain `GRAPH` keys (requiring direct matrix polling via `CHKACNT`), whereas European/international BIOSes queue them into the system buffer. Without active cross-path silencing, a single physical keypress fires both paths and types characters twice.
* **Practice:**
  - Whichever delivery path detects the keypress first must immediately claim ownership in the repeat state (`LASTGRP` / `GRPTIM`).
  - The secondary path must check this claim and quietly discard (`SCF` / drop) the redundant event until the key is released.
  - Ensure any hardware-specific BIOS scan codes (e.g. `#CF` for `GRAPH+W` on Philips NMS 8250) are mapped in dispatch tables.

### Rule 4: Full Lifecycle Verification (Init, Steady-State, Teardown)
* **The Rule:** Tests must verify the complete lifecycle of the editor, not just document editing in steady-state.
* **Why:** In-editor tests do not reveal state corruption occurring during boot degradation or during teardown back to MSX-DOS (e.g. corrupted VDP palettes or un-restored screen modes).
* **Practice:**
  - Verify initialization edge cases: missing assets (fallback to BIOS ROM charset in `B3`), corrupted config files, and memory exhaustion.
  - Verify teardown at exit (`TERM.TERMDON` in `G12`): ensure screen mode (`SCRMOD`), line width (`LINLEN`), text colors (`FORCLR`, `BAKCLR`, `BDRCLR`), and all 16 VDP palette registers (32 bytes) are restored byte-for-byte to their pre-entry state.

---

## 2. Assembly & Code Standards

All Z80 assembly code for S6ED is built with the **Glass** assembler.

* **Label formatting:** Maximum 8 characters, UPPERCASE, alphanumeric only. No underscores (`_`).
* **Numeric notation:** Use `#` prefix for hexadecimal values (e.g. `#A0`, `#3758`). Never use `0x...` or `...h`.
* **DEFB width:** Maximum 8 byte values per `DEFB` line.
* **Variable placement:** All variables must reside strictly in `VARS.Z8A` within the allocated window `[#3758, #44D0)`.
* **Page 1 Hook Protection:** Never install hooks (such as `H.TIMI` or `H.KEYI`) pointing into Page 1 (`#4000-#7FFF`), as mapper banking can page out the target code and crash the machine.

---

## 3. Verification Workflow

Run all tests from the `CODE/` directory:

```bash
make check       # T0 static invariant checks (~0.2s, no emulator)
make gate        # T1/T2 Headless openMSX test suite (~30s)
make test        # T0 static + Gate (~30s)
make selftest    # Mutation test against green baseline (~35s)
make testall     # Full suite: T0 + Gate + Selftest (~75s, 200+ checks)
```

No test short-circuits. Every check must pass with an exit code of `0`.
