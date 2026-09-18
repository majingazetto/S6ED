# S6ED — Plan de correcciones post-Fase 3a

Fecha: 2026-09-17 · Estado: **C1, C2 IMPLEMENTADAS (2026-09-17) · C4 IMPLEMENTADA (2026-09-18) · C3 EN CURSO (rama `feature/c3-window-painting`)**
Origen: revisión cruzada de las Fases 1b (maquinaria inter-segmento), 2 (contenedor
`S6ED.DAT`) y 3a (window engine, fuentes multi-peso, color 3, diálogo About).

Este documento agrupa los fallos encontrados en cuatro fases de corrección,
ordenadas por riesgo. Cada fase es independiente y cerrable con `make testall`
en verde (Regla 1 de AGENTS.md: baseline verde antes de mutar).

Resumen de la revisión: `make check` 13/13 PASS; mapa VRAM sin solapes; esperas
de CE correctas en todos los caminos; teardown (Regla 4) completo; sin fugas de
segmentos ni hooks prohibidos. Los fallos vivos son de validación (cargador DAT)
y de robustez del motor de ventanas, no del camino feliz.

---

## Fase C1 — Blindaje y generalización del cargador `S6ED.DAT`

**Estado: IMPLEMENTADA 2026-09-17** — ver nota de cierre al final de la sección.

**Por qué primero:** es el único fallo con corrupción de memoria directa, y la
generalización multi-bloque es la base para meter más features en el contenedor
(tokenizer, menús, keymaps) sin volver a tocar el loader.

### Diseño objetivo

Sustituir la carga lineal actual (cabecera → 1 descriptor → payload secuencial)
por un bucle dirigido por la tabla de descriptores:

```
1. Leer cabecera (16 B). Validar magic, versión, NUMBLKS en [1..8].
2. Leer la tabla completa de descriptores (NUMBLKS × 8 B) a un buffer RAM
   (DATTBL en VARS; 8 × 8 = 64 B máx).
3. Para cada descriptor, en orden:
   a. Validar: BLKID reconocido (tabla BLKID → segmento destino),
      LENGTH en [1..16384]          <- nunca escribir fuera de la ventana
      LOADADDR dentro de #8000..#BFFF y LOADADDR + LENGTH <= #C000,
      DATAOFF + LENGTH <= tamaño real del fichero.
   b. DSEEK a DATAOFF (el orden en disco ya no importa).
   c. Mapear el segmento destino en página 2 (PUTP2) — FTRSEG hoy,
      ALLSEG por bloque cuando crezca el contenedor.
   d. DSKREAD de LENGTH bytes a LOADADDR.
   e. Verificar bytes leídos == LENGTH y carry de BDOS limpio.
4. Cerrar handle. Restaurar página 2 a TXSEG0 (no DEFSEG2).
```

"Sin pasarnos de la TPA": la cota dura es la ventana de página 2
(`#8000-#BFFF`, 16384 B). La validación (3a) la hace imposible de violar aunque
el fichero mienta.

### Cambios concretos

- `CODE/SRC/XSEG.Z8A`
  - `DATLOAD` (líneas 109-211): reescribir como el bucle anterior. Hoy solo se
    lee `DATBLK+4` y se carga secuencial en `#8000`; se ignoran BLKID, FLAGS,
    LOADADDR y DATAOFF.
  - Añadir clamp `LENGTH <= 16384` **antes** de mapear/leer — el fallo
    crítico: un `LENGTH > 16384` escribe en página 3 (área DOS, pila) → cuelgue.
    El `ASSERT BLK0LEN <= 16384` (`S6ED.Z8A:466`) solo protege el build.
  - Comprobar carry (`JR C, .ERRCOR`) tras los tres `DSKREAD` (hoy líneas
    116, 161, 187).
  - Cierre: restaurar `TXSEG0` en vez de `DEFSEG2` (líneas 199-202) para
    romper el acoplamiento implícito DATLOAD↔BUFINIT.
  - Nueva rutina `DSEEK` en `BDOS.Z8A` si no existe (BDOS fn `_SEEK` #49H en
    DOS2; en DOS1 `_RDBLK` con registro aleatorio).
  - `CHKDAT` (líneas 89-96): validar cabecera completa (magic + versión +
    NUMBLKS) en modo texto, no solo existencia → abortar antes de entrar en
    SCREEN 6 con un DAT corrupto. Reutilizar el handle abierto si es sencillo.
  - `FCALL`: chequeo de overflow de `SEGSTK` (líneas 24-27) — la spec §4.1 lo
    prometía; hoy un 5º nivel pisaría `DATHAND` (`VARS.Z8A:46-47`).
- `CODE/SRC/VARS.Z8A`: buffer `DATTBL` (64 B) + contador de bloque actual.
- `CODE/SRC/CONST.Z8A`: tabla BLKID → segmento destino (hoy: 1 → FTRSEG).

### Tests (TEST/)

- Gate: magic malo, versión mala, fichero truncado en cabecera/descriptor/
  payload, `LENGTH = 0`, `LENGTH = 16385` (debe abortar limpio, sin tocar
  página 3), BLKID desconocido, `DATAOFF` desplazado con padding (el bucle
  debe hacer seek y cargar bien).
- Mutaciones: quitar el clamp de LENGTH, quitar la validación de BLKID,
  cargar secuencial sin seek → cada una debe tumbar su check.
- Hoy las ramas `.ERRCOR` no tienen cobertura de emulador (`mut/f2-datmagic`
  se caza en el check estático del artefacto, no en el loader).

### Criterio de salida

`make testall` verde con los nuevos casos; un `S6ED.DAT` corrupto en cualquiera
de las formas anteriores aborta con mensaje y sin corrupción; el contenedor
actual (1 bloque) sigue cargando idéntico.

### Nota de cierre (2026-09-17)

Implementada completa. `DATLOAD` es ahora un bucle dirigido por la tabla de
descriptores (`DATTBL` en VARS, máx. `DATMAX=8` bloques): valida cabecera
(magic, versión, `NUMBLKS` en [1..8], tabla dentro del fichero) vía la rutina
compartida `DATHCHK` — también usada por `CHKDAT` en modo texto antes de
`SCRINIT` — y por cada bloque valida `BLKID` (tabla `BLKTBL`: 1 → `FTRSEG`),
`LENGTH` en [1..16384], `LOADADDR` en [#8000,#C000) con `LOADADDR+LENGTH <=
#C000`, `DATAOFF` tras la tabla y `DATAOFF+LENGTH <=` tamaño real del fichero
(el tamaño lo da `DSKOPEN`). Nueva rutina `DSKSEEK` en `BDOS.Z8A` (`_SEEK` #4A
en DOS2; en DOS1 escribe el registro aleatorio del FCB — camino hoy
inalcanzable porque `DOSVER` ya exige DOS2/Nextor, documentado en la rutina).
Página 2 se restaura a `TXSEG0`. `FCALL` aborta vía `ERRMSG` si `SEGSP >= 8`.
Tests: casos Gate H8–H17 (9 formas de contenedor corrupto abortando limpio +
contenedor con padding que carga bien vía seek) y mutaciones `c1-datlen`,
`c1-datblkid`, `c1-datseek` (`f2-datload` actualizada al nuevo loader).
`make testall`: **262 checks, 0 failed** (T0 13/13, Gate 207/207, Selftest
42/42). Formato real documentado en `INTERSEG.md` §9.

---

## Fase C2 — Robustez del window engine

**Estado: IMPLEMENTADA 2026-09-17** — ver nota de cierre al final de la sección.

Fallos vivos o latentes en `WINDOW.Z8A`/`VDP.Z8A`/`UI.Z8A`. Todos pequeños y
aislados; ninguno cambia el diseño.

- **Fix carry en `WINOPEN`** (`WINDOW.Z8A:510-517`): `AND %11111100` mata el
  carry antes del `JR NC`, así que el `INC H` es código muerto y un
  `WINW ≥ 253` redondearía mal. Reordenar: capturar el carry del `ADD A,3`
  antes del `AND`.
- **Clamp/ASSERT de geometría en `WINOPEN`**: `WINX+WINW ≤ 512`,
  `WINY+WINH ≤ 212` (y buffer: `512+WINY+WINH ≤ 768`, `768+WINH ≤ 1024`).
  Hoy una ventana fuera de rango envuelve el HMMM a la línea siguiente o
  colisiona los buffers de banco 1. El About es seguro; el motor se anuncia
  como reusable y debe defenderse.
- **Contratos de clobber**: `VDPCMD` (`VDP.Z8A:72-84`) dice "CLOBBERS: NONE"
  y destruye BC (15 × OUTI); corregir cabecera y wrappers. `WINSTR/WINSTR3`
  (`WINDOW.Z8A:187-225`) usan IXL/IXH sin documentarlo — documentar o mover a
  variable en VARS (el subsistema de selección usa IX, `ACTION.Z8A:1125`).
- **Purgar teclado al abrir diálogo**: `KILBUF` al entrar en `DOABT`, para que
  un ENTER/ESC pendiente del BIOS no cierre el diálogo al instante.
- **Inhibir el reloj en modales**: flag `WINACTV` que `CHKCLK` (`UI.Z8A:360`)
  consulte. Hoy `WINPOLL`→`UPDMCLK` pinta el reloj en la fila 0 con la ventana
  abierta — inocuo para el About (Y=52), incorrecto en general.
- **Versión del About dinámica**: `DOABT` hardcodea `"Version 0.1 "`
  (`WINDOW.Z8A:646`); componer desde `VERSION.MAJOR/.MINOR` de `CONST.Z8A`.
- Documentar que `WINCLOS` no restaura el cursor (lo repinta el main loop).

### Tests

- Gate: ventana con geometría clampeada, apertura con tecla pendiente en el
  buffer, reloj inhibido durante modal (H nuevo).
- Mutaciones: reintroducir el `AND` antes del `JR NC`, quitar el clamp.

### Criterio de salida

`make testall` verde; el motor rechaza o clampa geometría inválida sin manchar
pantalla ni buffers.

### Nota de cierre (2026-09-17)

Implementada completa.
1. `WINOPEN` reordena la captura de carry de `ADD A, 3` en `L` antes de aplicar la
   máscara `AND %11111100`, redondeando anchos $\ge 253$ correctamente.
2. Clamps defensivos en `WINOPEN`: $WINX \le 508$, $WINW \in [4, 512 - WINX]$,
   $WINY \le 211$, $WINH \in [1, 212 - WINY]$, garantizando matemáticamente
   $X+W \le 512$ e $Y+H \le 212$ (con buffers de guardado $\le 724 < 768$ y composición
   $\le 980 \le 1024$ en Banco 1).
3. Cabeceras de `VDP.Z8A` corregidas: `VDPCMD` (`CLOBBERS: AF, BC, HL`), wrappers `HMMM`,
   `HMMV`, `YMMM`, `LMMM`, `LMMV` (`CLOBBERS: BC, DE`).
4. `WINSTR` / `WINSTR3` migrados a variables de trabajo en `VARS.Z8A` (`WINVAR`, `WINOP`),
   eliminando cualquier uso de `IX` y preservándolo intacto para el subsistema de selección.
5. `WINKIL` en `UI.Z8A` ejecuta `KILBUF` (`#0156`) vía `BIOSCALL`; invocado en `WINOPEN`
   para purgar cualquier pulsación de teclado residual antes de presentar el diálogo.
6. Flag `WINACTV` en `VARS.Z8A`: activado a 1 en `WINOPEN`, reseteado a 0 en `WINCLOS`.
   `CHKCLK` comprueba `(WINACTV)` inmediatamente y suspende el parpadeo de reloj en Fila 0
   mientras el diálogo esté activo.
7. `WINSTR` en `WINDOW.Z8A`: preservación estricta de `A` mediante `PUSH AF` / `POP AF`
   al cargar `(WINVAR)` y `(WINOP)`, corrigiendo la corrupción de glifos donde todos los
   caracteres del diálogo se convertían en tramas de control (`#03`/`#08`).
8. `.STRVER` en `DOABT` compone dinámicamente la versión desde `VERSION.MAJOR` y `VERSION.MINOR`.
9. Cabecera de `WINCLOS` documenta que la celda del cursor no se repinta en el cierre.
10. Tests añadidos y blindados:
    - Chequeo estático `check_window_discipline` en `TEST/static.py` (14/14 checks).
    - Hardening de `H7AboutDialog` con verificación óptica/píxel a píxel de los glifos de
      título (`"About S6ED"` en Negrita/Ámbar), cuerpo (`"S6ED"` en Negrita+Cursiva/Blanco)
      y botón (`"[  OK  ]"` en Negrita/Ámbar) comparados contra `vram.glyph_mask`.
    - Nuevo caso `H18WindowRobustness` en `TEST/gate.py`.
    - 5 mutaciones nuevas (`mut/c2-wincarry`, `mut/c2-winactv`, `mut/c2-winkil`, `mut/c2-winclamp`, `mut/c2-winchtr-char`).
`make testall`: **276 checks, 0 failed (114.4s)** (T0 14/14, Gate 215/215, Selftest 47/47).

---

## Fase C3 — Mejora del pintado de ventanas

**Estado: DISEÑO AMPLIADO 2026-09-18 (rama `feature/c3-window-painting`)** —
la propuesta original quedó revisada con las medidas reales de
`informe_optimizacion_s6ed.md` y salió una versión mucho más ambiciosa.
Ver "Estudio C3 ampliado" más abajo; la lista de trabajo es la del estudio.

### Propuesta original (2026-09-17, SUPERSEDED)

El diseño actual (composición oculta en Y=768 + 2 HMMM visibles de ~7,5 KB) es
correcto: sin flicker y bajo un frame. Estas mejoras son de pulido, no de
arquitectura. Orden de ataque sugerido:

1. **Sincronizar `WINSHOW`/`WINRST` con VBLANK** (flag F de S#0 o flanco de
   JIFFY antes del HMMM visible): elimina el tearing teórico por ≤1 frame de
   latencia. Es el único defecto visible que queda.
2. **Borde y acento con HMMV en vez de LMMV** (`WINBOX`, `WINDOW.Z8A:287-319`):
   WINX/WINW ya son múltiplos de 4 precisamente para esto; HMMV rinde ~2× por
   byte. Ahorra ~3-5 ms de composición (oculta → mejora latencia de apertura).
   El relleno interior (DX=WINX+1) no es alineable y se queda en LMMV.
3. **Drop shadow (opcional, decisión estética)**: 2 HMMV extra en composición
   (barra derecha e inferior de 2 px) y ampliar `WINSAV`/`WINSHOW` a
   `WINW+2 × WINH+2` — hay margen de buffer (salvado acaba en 724 < 768).
   ~1 ms oculto.
4. **Recorte de texto a WINW** en `WINPRN` si se quiere el motor cerrado
   (hoy un string largo pinta sobre el borde derecho).

Descartado tras el análisis: dirty-rectangles (el rectángulo completo ya es un
solo comando de coste fijo; subdividir solo añade esperas CE), y escritura
parcial de registros VDP (~5 ms offscreen, complejidad innecesaria). Guardar la
idea de repaint por líneas para ventanas con contenido dinámico futuro (un
HMMM de 1 línea ≈ 50 µs).

### Estudio C3 ampliado (2026-09-18)

La propuesta original subestimó los costes casi un orden de magnitud: usaba el
"~3,2 ms por blit" de la cabecera de `WINDOW.Z8A`, que es ~10× optimista a los
tamaños reales de diálogo. Con las medidas del informe de optimización
(`Philips_NMS_8250`, display on):

| Primitiva | Coste medido |
|---|---|
| HMMV (relleno por bytes) | 3,8 µs/byte |
| HMMM (copia) | ~5,0 µs/byte |
| LMMV (relleno por dots) | ~9,4 µs/byte-equivalente (2,5× HMMV) |
| LMMM glifo 6×8 | ~550 µs (~450 overhead fijo VDP + ~100 CPU + ~46 píxeles) |

Coste actual de abrir el diálogo About (288×104 px = 7.488 B):

| Parte | Hoy |
|---|---|
| `WINSAV` (HMMM) | ~37 ms |
| Rellenos `WINBOX` en LMMV (borde + interior + barra título + separador, con triple overdraw) | ~146 ms |
| Texto (~170 glifos × 550 µs; ~30 son espacios que no pintan nada) | ~94 ms |
| Botón | ~8 ms |
| `WINSHOW` (HMMM) | ~37 ms |
| **Total** | **~320 ms** |

Los rellenos LMMV — no el texto — son el mayor coste de composición, y el
ítem 2 original ("ahorra ~3-5 ms") arañaba solo el borde. Lista de trabajo
ampliada, ordenada por impacto:

1. **Descomposición por bandas HMMV (nueva, la estrella).** Sustituir borde +
   relleno interior + barra de título LMMV (triple overdraw) por bandas
   horizontales a ancho completo en HMMV — WINX/WINW ya son múltiplos de 4 por
   el clamp de C2: acento (COL_HI, 1 px), título (COL_UI, 10 px), separador
   (COL_HI, 1 px), cuerpo (COL_BG), borde inferior; más dos slivers LMMV de
   1 px para los bordes laterales. Cero overdraw, todo el grueso en modo byte.
   About: ~146 → ~29 ms; Quit: ~64 → ~12 ms. Subsume el ítem 2 original.
   Ojo: las bandas con alto ≤ 0 se saltan (NY=0 en un comando VDP es peligroso).
2. **Skip de espacios en `WINSTR`/`WINSTR3` (nueva).** El glifo de espacio es
   todo ceros: con TIMP/TOR pintarlo es un no-op garantizado (las T-ops no
   transfieren dots de color 0). Saltarlo es píxel-idéntico y ahorra ~550 µs
   por espacio (~17 ms en About; cada botón `"[  YES  ]"` lleva 4).
3. **Re-blit parcial `WINUPD` (nueva).** Generalizar `WINSHOW` a un
   sub-rectángulo (relX múltiplo de 4, NX múltiplo de 4): la navegación YES/NO
   de `DOQIT` re-blittea solo los dos botones (~450 B ≈ 2,3 ms) en vez de la
   ventana entera (3.200 B ≈ 16 ms) por flecha. Es la mejora más perceptible
   (interactiva) y la primitiva que necesitarán los menús de Fase 4 —
   resucita la idea aplazada de repaint por líneas, generalizada a rects.
4. **Sincronía VBLANK en `WINSHOW`/`WINRST`/`WINUPD` (ítem 1 original).**
   Espera de flanco de JIFFY (el ISR del BIOS está vivo: WINPOLL usa
   CHSNS/CHGET y el blink usa JIFFY; seguro y determinista en openMSX).
   Matiz que el plan original no veía: un blit >1 frame (About ≈ 37 ms) no
   puede ser 100% tear-free solo sincronizando el inicio; el residual es un
   wipe top-down determinista de un frame en lugar de tearing aleatorio.
   Quit (~16 ms) queda limpio.
5. **Cuerpos de botón en HMMV (nueva, menor).** Rel-X múltiplos de 4
   (nudge 106→108 en DOQIT; 36 y 116 ya lo son) y el cuerpo 56×12 pasa a
   HMMV con patrón de byte (`CLR_UI`/`CLR_HI`). El borde 58×14 se queda LMMV.
6. **Recorte de texto a WINW (ítem 4 original).** `WINOPEN` fija
   `WINCLIPX = WINX + WINW - 1`; `WINSTR` corta el string cuando el siguiente
   glifo lo superaría. Cero = sin clip (escape para usos futuros).
7. **Sombra 4 px (ítem 3 original, APROBADA).** En 4 px, no 2: mantiene
   WINX+WINW múltiplo de 4 y todas las barras en HMMV alineado (barra derecha
   4×WINH en X+WINW/Y+4; inferior WINW×4 en X+4/Y+WINH, COL_BG). Los rects de
   `WINSAV`/`WINSHOW`/`WINRST` crecen a `(WINW+4)×(WINH+4)` y los clamps de
   `WINOPEN` reservan esos 4 px (WINX+WINW ≤ 508, WINY+WINH ≤ 208). Margen de
   VRAM: salvado acaba en 512+216=728 < 768; composición en 768+216=984 ≤ 1024.
8. **Errata doc:** la cabecera de `WINDOW.Z8A` decía "pop-up takes ~3.2 ms";
   a tamaños reales es `NX/4 × NY × 5 µs` (About ≈ 37 ms, Quit ≈ 16 ms).

Proyección: About ~320 → ~190 ms; Quit ~125 → ~65 ms; navegación 16 → ~2,4 ms;
tearing aleatorio eliminado.

Descartadas en esta revisión (con las medidas en la mano): glifos por HMMM en
columnas alineadas (el overhead de ~450 µs es *por comando*, no por byte: no
gana nada y ensucia el borde derecho del string); caché de diálogos compuestos
(no cabe en banco 1: WINCOMP+216=984 y quedan 40 líneas); slim de VDPCMD a
R#32-37+R#46 (recorta solo los ~100 µs CPU de los 550 µs por glifo — ~17 ms en
About — a cambio del cambio más arriesgado del lote; fuera de C3).

### Tests

- Gate: verificación de píxeles de borde tras el cambio HMMV (el caso H7
  existente de highlight >500 px debería seguir pasando), screenshot-diff del
  About antes/después para detectar regresiones visuales.

---

## Fase C4 — Deuda sistémica y documentación

**Estado: IMPLEMENTADA 2026-09-18** — ver nota de cierre al final de la sección.

Sin urgencia; hacer cuando toque cada archivo.

- **AGENTS.md**: la ventana de variables `[#3758, #44D0)` ya no se cumplía
  (`ENDVARS=#48A2` tras C2) y `check_vars_block` usa límites dinámicos, así que
  crecía en silencio. Resuelto: §2 documenta ahora el modelo real (bloque
  `VARS`..`ENDVARS` en RAM tras la imagen `.COM`, puesto a cero por `INIT`,
  verificado por `check_vars_block`). Además: el ensamblador real es
  **sjasmplus** (Makefile), no Glass — corregido en §2.
- **`INTERSEG.md` §9**: verificada contra el código — ya quedó correcta con el
  cierre de C1 (offset 7 = `NUMBLKS`, tabla en 8..9, descriptores de 8 B). Los
  tamaños citados se actualizan al build actual (`FTRBLEN` = 2.402 B, fichero
  2.426 B); los anteriores provenían de un artefacto local anterior a las
  fuentes finales de C2 (el `.DAT` no está versionado).
- **`INTERSEG.md` §4.3 (stubs `STB_`)**: la disciplina feature→core con
  re-banco incondicional nunca se implementó y el código llama a BDOS/core
  directamente desde el FTRSEG (`CFG.Z8A`, `WINPOLL`→`UPDMCLK`→`CALL DOS`).
  Resuelto documentando el invariante verificado empíricamente con
  `TEST/PROBE2.Z8A`: ni BDOS (DOS 2 / Nextor) ni el core re-banquean la
  página 2 entre llamadas. La sección conserva el diseño de stubs como defensa
  documentada si el invariante se rompe algún día.
- **`DESIGN.md`**: §Screen Layout, §VRAM Layout, §Character Grid, §Font y
  §Build System reescritos al estado real (márgenes de 16 px, filas
  menú/texto/estado, fuentes de 8 KB en `#08000-#0FFFF`, buffers de ventana en
  banco 1, asset `S6ED.FNT` con fallback ROM, sjasmplus sin preprocesador).
- **Reorganización documental**: `DOC/` queda reservado para la documentación
  *del editor* (manuales de usuario, referencias de teclas). La documentación
  de desarrollo se mueve a `DEV/` (`DESIGN.md`, `INTERSEG.md`,
  `PLAN_CORRECCIONES.md`, `FONT_BRIEF.md`, los dos `informe_*.md`), con
  `README.md` de índice en ambos directorios y referencias actualizadas en
  `RES/mkfontsheet.py`, `TEST/README.md` y los comentarios de `CONST.Z8A`,
  `RENDER.Z8A`, `SCROLL.Z8A` y `XSEG.Z8A`. La referencia muerta a
  `informe_test_plan_s6ed.md` en `TEST/README.md` queda eliminada.
- **Erratas**: "GRAPHIC 5"/"G5" → Screen 6 en `CONST.Z8A`, `FONT.Z8A`,
  `RENDER.Z8A`, `TEST/vram.py` e `INTERSEG.md` §11.1. Los nombres de caso de
  test (`G5Clock`, filtros `G5/*`) se conservan: allí `G5` es el identificador
  del caso, no el modo de vídeo.
- **Makefile**: `$(DATFILE)` tenía dependencia sin receta — si se borraba
  `S6ED.DAT` con el `.COM` al día, no se regeneraba. Ahora tiene receta que
  re-ensambla solo si el `.DAT` no existe.

### Nota de cierre (2026-09-18)

Fase puramente documental salvo el Makefile; ningún cambio toca código
ejecutable (solo comentarios). `make testall`: **276 checks, 0 failed**.

---

## Orden recomendado

```
C1 (seguridad + multi-bloque DAT)  → riesgo real de corrupción
C2 (robustez window engine)        → fixes aislados, bajo riesgo
C3 (pintado)                       → pulido visual, sin urgencia
C4 (docs/deuda)                    → cuando toque cada archivo
```

C1 y C2 son independientes entre sí. C3 conviene hacerlo después de C2 (toca
las mismas rutinas de `WINDOW.Z8A`; el clamp de geometría de C2 simplifica la
sombra de C3). Antes de cada fase: `make testall` para fijar el baseline verde
(Regla 1).
