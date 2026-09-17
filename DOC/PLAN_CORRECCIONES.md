# S6ED — Plan de correcciones post-Fase 3a

Fecha: 2026-09-17 · Estado: **C1 IMPLEMENTADA (2026-09-17) · C2-C4 PROPUESTAS**
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
42/42). Formato real documentado en `DOC/INTERSEG.md` §9.

---

## Fase C2 — Robustez del window engine

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

---

## Fase C3 — Mejora del pintado de ventanas

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

### Tests

- Gate: verificación de píxeles de borde tras el cambio HMMV (el caso H7
  existente de highlight >500 px debería seguir pasando), screenshot-diff del
  About antes/después para detectar regresiones visuales.

---

## Fase C4 — Deuda sistémica y documentación

Sin urgencia; hacer cuando toque cada archivo.

- **AGENTS.md**: la ventana de variables `[#3758, #44D0)` ya no se cumple
  (`ENDVARS=#46C6` en el build actual, +502 B) y `check_vars_block` usa límites
  dinámicos, así que crece en silencio. Decidir: actualizar el límite
  documentado al modelo actual (VARS..ENDVARS + assert contra el directorio)
  o reponer un `ASSERT` duro. Además: el ensamblador real es **sjasmplus**
  (Makefile), no Glass — corregir §2.
- **`DOC/INTERSEG.md` §9**: la especificación del formato DAT está desplazada
  +2 bytes respecto al código (offset 7 = NUMBLKS, no "global flags") y cita
  tamaños obsoletos. Reescribirla cuando C1 fije el formato definitivo.
- **`DOC/INTERSEG.md` §4.3 (stubs `STB_`)**: la disciplina feature→core con
  re-banco incondicional nunca se implementó y el código ya llama a BDOS/core
  directamente desde el FTRSEG (`CFG.Z8A`, `WINPOLL`→`UPDMCLK`→`CALL DOS`).
  Funciona porque se verificó empíricamente que BDOS no rebanquea página 2.
  Decidir: implementar los stubs (defensa real para futuros diálogos con I/O
  de disco) o reescribir la sección documentando el invariante verificado.
- **DESIGN.md**: §VRAM Layout y §Startup Expansion describen el diseño antiguo
  (fuentes en #07000 de 4 KB, expansión por OR-shift rechazada el 2026-09-12,
  gutter de 24 px). Actualizar al mapa real (fuentes #08000-#0FFFF de 8 KB,
  buffers de ventana en banco 1, márgenes de 16 px) o delegar en INTERSEG.md.
- **Erratas**: "GRAPHIC 5"/"G5" → Screen 6 en `VDP.Z8A:127`, `CONST.Z8A`.
- **Makefile**: `$(DATFILE): $(OUTPUT)` sin receta — si se borra `S6ED.DAT`
  con el `.COM` al día, no se regenera. Darle regla explícita.

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
