# SXED — Technical & Development Documentation

Design documents, architectural specifications, phase plans, and investigation reports produced
during the development of the SXED editor family (S6ED, S61ED, S2ED). The user-facing documentation
(manuals, keybinding references, etc.) belongs in `../DOC/`.

### Architecture & Design
- `DESIGN.md` — Core editor design document: screen/VRAM layout, character grid, font subsystem, memory model, keybinding engine.
- `INTERSEG.md` — Inter-segment infrastructure and the `S6ED.DAT` multi-segment container specification.
- `SPEC_VARIABLE_LINES_AND_WRAP.md` — Variable-length line storage, segment compaction, and word wrap engine.
- `SPEC_HORIZONTAL_VIEWPORT_AND_TEXTWIDTH.md` — Universal horizontal viewport (`LEFTCOL`) and parametric text width.
- `SPEC_GOTOLINE.md` — Go to Line dialog and window widget specification.
- `SPEC_FILE_BROWSER.md` — Zero-extra-segment file browser (Open / Save As).
- `SPEC_S2ED_WINDOW_MENU.md` — MSX1 Screen 2 window engine, dropdown menus, and color architecture.
- `SPEC_S2ED_FTRBASE_GUARD.md` — Feature container memory budgeting and guard architecture.
- `SPEC_S62ED.md` — MSX2 Screen 6 61-column (8x8 font) geometry specification.

### Fonts & Resources
- `FONT_BRIEF.md` — Font asset brief: `S6ED.FNT` variants and glyph sheet.
- `FONT_BRIEF_S64.md` — 8x8 font asset brief and glyph sheet.

### Roadmaps & Plans
- `PLAN_CORRECCIONES.md` — Post-Fase-3a correction plan with closing notes per completed phase.
- `PLAN_ROADMAP_V1.md` — Architecture roadmap (status bar, VI console, unified Settings, browser).
- `PLAN_SETTINGS_FEEDBACK_AND_BROWSER_SELECTION.md` — Real-time settings feedback and browser focus polish plan.
