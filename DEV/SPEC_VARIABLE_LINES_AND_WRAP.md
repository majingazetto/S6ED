# Architectural Specification: Variable-Length Line Storage, Segment Compaction & Horizontal Viewport Engine

**Date:** 2026-09-24  
**Status:** Approved Roadmap & Architectural Specification (Phase 1 SDD)  
**Authors:** Armando Pérez Abad & Claude / Antigravity  
**Target Systems:** MSX2 Screen 6 (S6ED, 80 cols) & MSX1 Screen 2 (S2ED, 64 cols)  

---

## 1. Executive Summary & Design Pivot

### 1.1 The Fixed-Record Bottleneck
The SXED core currently allocates fixed-width records in 16 KB mapper segments (`TXPAGE = #8000`):
* **S6ED (80 columns):** `LINEREC = 161 bytes` (`1 LEN + 80 TEXT + 80 ATTR`). Capacity: **101 lines per 16 KB segment**.
* **S2ED (64 columns):** `LINEREC = 129 bytes` (`1 LEN + 64 TEXT + 64 ATTR`). Capacity: **127 lines per 16 KB segment**.

### 1.2 Pathologies Identified
1. **Severe Memory Waste:** An empty line (`\n`) consumes 161 (or 129) bytes. A 300-line document wastes ~48 KB of mapped text RAM (~3 segments) even if the raw payload is under 3 KB.
2. **Early OOM on Stock 128 kB:** Machines with only 3 free text segments exhaust memory at ~303 lines.
3. **Cross-Resolution Truncation:** Loading an 80-column file in S2ED silently discards characters past column 64.
4. **Redundant 80-byte Attribute Array:** 50% of the allocated record is a raw attribute array (`ATRFMSK`), even though 99% of text is plain and styling is dynamically parsed at render time via `SCANMKUP`.

### 1.3 User Requirement: No Truncation in DEV Mode
Direct user feedback confirms that in developer/code editing mode (`WRAP=DEV`), code lines must **never be truncated or artificially broken**:
* Long lines (e.g. 100+ columns) must be preserved in full.
* The viewport must provide **horizontal scrolling** (`LEFTCOL`) to reveal columns beyond screen bounds.
* Word wrap / soft wrap remains reserved for text/prose editing (`WRAP=TXT`).

---

## 2. Core Storage Architecture: Variable-Length Records

### 2.1 The Two-Level Pointer Model
The pointer-to-pointer model (`DIRSEG` $\to$ `(SEG, OFFSET)`) is preserved:
* **Line Directory (`DIRSEG`):**
  * Flat 3-byte directory entry per line: `[SEG (1B)] [OFFSET (2B Word, low/high)]`.
  * Preserved in its dedicated 16 KB mapper segment (`DIRWIN = #8000`).
  * Directory capacity: $16,384 / 3 = \mathbf{5,461\text{ lines}}$.
* **Dynamic Record Format (4-Byte Header):**
  * To enable fast, linear single-pass compaction without directory rescans, each record in mapped RAM carries a 4-byte header:

```
+----------------+----------------+-------------------------------+
| LINE_ID (2B)   | LEN (2B)       | TEXT (LEN bytes)              |
| 16-bit word    | 16-bit word    | Raw ASCII characters          |
+----------------+----------------+-------------------------------+
```

* **`LINE_ID` (Bytes 0..1):** The logical line index (0..5460) owning this record.
  * When a line is deleted or relocated, its slot is marked as dead with `LINE_ID = #FFFF` (tombstone).
* **`LEN` (Bytes 2..3):** Exact text length (0..65535, bounded by buffer size).
* **`TEXT` (Bytes 4..4+LEN-1):** Raw ASCII text. Zero trailing space padding. Zero redundant attribute array.

### 2.2 Storage Footprint Impact

| Line Content | Current Fixed Size | Proposed Variable Size | Net Memory Reduction |
| :--- | :--- | :--- | :--- |
| Empty line (`\n`) | 161 bytes | **4 bytes** | **-97.5%** |
| Short line (20 chars) | 161 bytes | **24 bytes** | **-85.1%** |
| Code line (40 chars) | 161 bytes | **44 bytes** | **-72.7%** |
| Full 80-col line | 161 bytes | **84 bytes** | **-47.8%** |

*A 128 kB MSX machine expands capacity from ~303 lines to **1,500–2,000+ real lines**.*

---

## 3. Segment Compactor & Memory Lifecycle

### 3.1 Allocation & Modification Policy
1. **Append Cursor:** Each 16 KB segment tracks an allocation offset (`#0000..#3FFF`). New records append at the tail.
2. **In-Place Modification:**
   * If $\text{NewLen} \le \text{OldLen}$: overwrite in place. Excess bytes (if shrinking) are padded or tombstoned.
   * If $\text{NewLen} > \text{OldLen}$: the old slot is invalidated (`LINE_ID = #FFFF`), the expanded line is appended to the segment tail, and `DIRSEG[LINE_ID].OFFSET` is updated.

### 3.2 Segment-Local Compaction Engine (`COMPACT.Z8A`)
When an allocation exceeds the 16 KB segment boundary and the segment contains tombstoned bytes:
1. **UI Notification:** Display non-intrusive modal/status text: `"Compacting..."` (blocking input, preserving screen state).
2. **Linear Compaction Pass:**
   * Scans sequentially from offset `#0000` to segment tail.
   * Skips records with `LINE_ID == #FFFF`.
   * Slides active records downward using `LDIR` to eliminate gaps.
   * Updates `DIRSEG[LINE_ID].OFFSET` immediately for each relocated record.
3. **Execution Time on Z80 (3.58 MHz):**
   * Moving a full 16 KB block via `LDIR` requires:
     $$16,384\text{ bytes} \times 21\text{ T-states} \approx 344,064\text{ cycles} \approx \mathbf{96\text{ ms}}$$
   * Compaction completes in under 1/10th of a second.
4. **Segment Overflow:** If the segment remains full after compaction, a fresh 16 KB segment is claimed via `ALL_SEG`.

---

## 4. Undo Subsystem Adaptation

### 4.1 Current Fixed Model vs Variable-Length Undo
* **Current:** Each modified/deleted line stores a fixed snapshot:
  $$\text{UNDOMOD\_SZ} = 10\text{ bytes (header)} + 161\text{ bytes (record)} = \mathbf{171\text{ bytes}}$$
* **Proposed Variable Model:**
  ```
  +------------------+----------------+-------------------------------+
  | UNDOHDR (10B)    | LEN (2B)       | TEXT (LEN bytes)              |
  | Action/Line/Col  | 16-bit word    | Exact snapshot text           |
  +------------------+----------------+-------------------------------+
  ```
* **Impact:** Modifying a 20-character line consumes only $10 + 2 + 20 = \mathbf{32\text{ bytes}}$ instead of 171 bytes. The existing Undo ring buffer in TPA RAM gains **3x to 5x more undo history steps**.

---

## 5. Visual Selection & Clipping

* Selection range coordinates remain logical: `(SELSTA_L, SELSTA_C)` to `(SELEND_L, SELEND_C)`.
* Memory operations (Cut, Copy, Delete Selection) operate directly on logical character offsets.
* Screen rendering clips the selection highlight to the visible window:
  $$\text{Visible Span} = [\text{LEFTCOL} \;..\; \text{LEFTCOL} + \text{TEXTCOLS} - 1]$$

---

## 6. Phased Implementation Roadmap

To maintain strict quality gating and keep all 555 tests green, development is divided into three isolated, sequential phases:

```
+-------------------------------------------------------------------------------+
| PHASE A: Dynamic Storage, Segment Compaction & Undo Refactoring               |
|   - Implement 4-byte record header: [LINE_ID (2B)] [LEN (2B)] [TEXT]          |
|   - Eliminate 80-byte attribute array from mapper storage                     |
|   - Implement segment-local compactor (COMPACT.Z8A) with "Compacting..." UI   |
|   - Refactor LINEREAD, LINEWRT, FILELOAD, and FILESAVE for variable lengths   |
|   - Refactor UNDO subsystem to store variable-length line snapshots           |
|   - SCREEN/VIEWPORT UNCHANGED: Renders up to TEXTCOLS (80 in S6, 64 in S2)    |
|   - Verification: 100% test pass on both S6 and S2 suites (555+ checks)       |
+-------------------------------------------------------------------------------+
                                      |
                                      v
+-------------------------------------------------------------------------------+
| PHASE B: Long Lines in Memory & Editing Operations                            |
|   - Expand WORKBUF capacity (to 256 or 512 bytes) for long-line manipulation  |
|   - Adapt edit primitives: SPLIT, JOIN, INSERT, DELETE, BACKSPACE, CLIPBOARD   |
|   - Verify that lines > 80 columns do not overflow buffers or corrupt Undo    |
|   - Full empirical validation of multi-line selection with arbitrary lengths  |
+-------------------------------------------------------------------------------+
                                      |
                                      v
+-------------------------------------------------------------------------------+
| PHASE C: Horizontal Viewport & Scrolling Engine                               |
|   - Introduce LEFTCOL viewport horizontal offset variable                     |
|   - Update RENDEROW and RENDIFF to blit text sliced from LEFTCOL              |
|   - Update DRWCUR: SCREEN_X = CURX - LEFTCOL with auto-scroll at screen edges |
|   - Configure modes: WRAP=DEV (zero wrap, horizontal scroll) vs WRAP=TXT     |
|   - End-to-end regression audit across S6ED and S2ED                          |
+-------------------------------------------------------------------------------+
```

---

## 7. Next Actions

1. Review and freeze Phase A technical specification.
2. Verify all test harnesses before implementing `COMPACT.Z8A`.
3. Proceed with Phase A upon explicit user confirmation.
