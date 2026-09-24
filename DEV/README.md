# S6ED — Development Documentation

Design documents, phase/correction plans, and investigation reports produced
during the development of S6ED. The documentation *of the editor* (user
manuals, keybinding references, etc.) belongs in `../DOC/`.

- `DESIGN.md` — editor design document: screen/VRAM layout, character grid,
  font subsystem, memory model, keybinding engine. Dated annotations mark
  superseded designs where the text has not been rewritten yet.
- `INTERSEG.md` — inter-segment infrastructure and the `S6ED.DAT`
  multi-segment container specification (Fases 1a, 1b, 2, 3a and C1).
- `PLAN_CORRECCIONES.md` — post-Fase-3a correction plan (Fases C1–C4) with a
  closing note per completed phase.
- `PLAN_ROADMAP_V1.md` — post-Find & Replace architecture roadmap: right-justified
  status bar, VI command console (:), unified Settings dialog, zero-extra-segment
  file browser, and TED keymap profile.
- `FONT_BRIEF.md` — font asset brief: `S6ED.FNT` variants and glyph sheet.
- `informe_directorio_segmento_s6ed.md` — line-directory / mapper-segment
  investigation report.
- `informe_optimizacion_s6ed.md` — render and scroll optimization report.
