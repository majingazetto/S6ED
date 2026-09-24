# S6ED / S2ED — Roadmap de Desarrollo Post-Find & Replace

Fecha: 2026-09-24  
Estado: **FASES 1 Y 2 COMPLETADAS & VERIFICADAS (555 checks PASS, 0 fallos)**  
Objetivo: Transformación integral de la interfaz de usuario, incorporación de la consola de comandos de VI, diálogo unificado de configuración y navegador de ficheros, preservando estrictamente el presupuesto de memoria de un único segmento para features (`FTRSEG`).

---

## 1. Visión General del Roadmap

El proyecto evoluciona desde las bases del editor básico hacia un entorno completo de productividad MSX2/MSX1.

```
+-------------------------------------------------------------------------------+
| Fase 1: Barra de Estado Derecha & Indicadores Compactos                       |
|   - Telemetría (Ln/Col/Clock) justificada a la derecha                        |
|   - Tira de flags compacta [W|A|M|I]                                          |
|   - Mitad izquierda reservada para mensajes de estado y consola de comandos   |
+-------------------------------------------------------------------------------+
                                      |
                                      v
+-------------------------------------------------------------------------------+
| Fase 2: Consola de Comandos de VI (: ex mode)                                 |
|   - Activación con ':' en modo Normal (KMAPVIN) en la barra inferior          |
|   - Intérprete residente de comandos: :w, :q, :wq, :q!, :<line>, :e, :set     |
|   - Mensajería efímera del editor a la izquierda de la barra de estado        |
+-------------------------------------------------------------------------------+
                                      |
                                      v
+-------------------------------------------------------------------------------+
| Fase 3: Reorganización de Menús y Diálogo Unificado 'Settings...'             |
|   - Reducción de la barra superior a 4 menús: File · Edit · Settings · Help   |
|   - Eliminación de la dispersión de opciones en 'View' y 'Options'            |
|   - Diálogo modal Settings... con guardado persistente en S6ED.CFG / S2ED.CFG |
+-------------------------------------------------------------------------------+
                                      |
                                      v
+-------------------------------------------------------------------------------+
| Fase 4: Navegador de Ficheros (Open... / Save As...)                          |
|   - Diálogo modal con explorador de ficheros 8.3 y cambio de directorio       |
|   - Escáner BDOS ultra-compacto (_FFIRST / _FNEXT) sin desbordar FTRSEG       |
|   - Presupuesto estricto: cero segmentos adicionales (S2ED <= 4.5 KB)         |
+-------------------------------------------------------------------------------+
                                      |
                                      v
+-------------------------------------------------------------------------------+
| Fase 5: Perfil de Teclado TED (KMAPTED)                                       |
|   - Sustitución del histórico y desusado WordStar (KMAPWS) por TED de MSX-DOS|
|   - Adopción de atajos clásicos de navegación, bloques y comandos de TED      |
+-------------------------------------------------------------------------------+
                                      |
                                      v
+-------------------------------------------------------------------------------+
| Fase 6: Resaltado de Sintaxis (Highlighting) [Al final del ciclo]             |
+-------------------------------------------------------------------------------+
```

---

## 2. Especificación Técnica por Fases

### Fase 1: Barra de Estado Derecha & Indicadores Compactos

#### 1.1 Diagnóstico Actual
Actualmente, la barra de estado en la fila 25 (S6ED, Y=200..207) y fila 23 (S2ED, Y=184..191) dibuja de izquierda a derecha:
`Ln 00001/00030  Col 01  [VI-N]  12:34:56` etc.
Ocupa la zona izquierda, dejando la derecha parcialmente vacía o con tags largos.

#### 1.2 Diseño Objetivo
- **Lado Izquierdo (Columnas 0..44 en S6ED, 0..34 en S2ED):**
  - Espacio limpio y en reposo para mensajes del sistema:
    - `"TEST.TXT" 30 lines, 1024 bytes`
    - Mensajes de error/aviso temporales (`[FILE TOO LARGE]`, `Search: pattern not found`, etc.).
    - Área de trabajo para el prompt y la entrada de texto de la consola de comandos de VI (`:w`, etc.).
- **Lado Derecho (Columnas 45..79 en S6ED, 35..63 en S2ED):**
  - **Tira de estado compacta `[W|A|M|I]`:**
    - `W`: Wrap mode (`D` = Dev, `T` = Text).
    - `A`: Autoalign (`-` = Off, `A` = Autoalign Dev/On).
    - `M`: Markup mode (`-` = Off, `M` = Markdown, `L` = Lite).
    - `I`: Insert mode (`I` = Insert, `O` = Overwrite).
  - **Modo VI:** `[N]` (Normal), `[I]` (Insert), `[V]` (Visual) únicamente cuando el perfil activo sea Vi.
  - **Posición del cursor:** `Ln 00123/00500 Col 24`.
  - **Reloj (si CLOCK=1):** `12:34` en el extremo final.

#### 1.3 Módulos Afectados
- `CODE/SRC/S6/UI.Z8A` y `CODE/SRC/S2/UI.Z8A` (`DRWSTAT`, `STATPRV`).
- Mantenimiento estricto del renderizado diferencial (`STATCEL`) para que la barra de estado continúe costando $\le 11$ ms por frame.

---

### Fase 2: Consola de Comandos de VI (`: ex mode`)

#### 2.1 Activación y UX
- En perfil Vi (`KMAPVIN`), al pulsar `:` en Modo Normal:
  - El cursor abandona el área de texto y salta a la Fila de Estado (columna 0).
  - Se pinta el prompt `:` en color invertido o resaltado.
  - Se entra en un bucle modal de línea de comandos (`EXLINE` en `CODE/SRC/CORE/` o `ACTION.Z8A`).
  - Soporta edición elemental: caracteres imprimibles, `Backspace` para borrar, `ESC` para cancelar y volver a Normal mode sin ejecutar nada, y `ENTER` para parsear y ejecutar.

#### 2.2 Conjunto de Comandos Iniciales
1. `:w` — Guarda el archivo actual (`FILESAVE`).
2. `:w <nombre>` — Guarda con nuevo nombre (`FILESAVE` con parámetro).
3. `:q` — Sale del editor si no está modificado (`MODIFIED == 0`), o rechaza con mensaje de error `"No write since last change (add ! to override)"`.
4. `:q!` — Fuerza la salida descartando cambios sin confirmación.
5. `:wq` o `:x` — Guarda y sale.
6. `:<numero>` — Salto inmediato a la línea especificada (reutilizando la rutina residente `GOTOLN`).
7. `:e <nombre>` — Carga un nuevo archivo (`FILELOAD`).
8. `:set <opcion>` — Ajuste rápido de flags (`:set wrap=dev`, `:set nu`, etc.).

---

### Fase 3: Reorganización de Menús y Diálogo Unificado 'Settings...'

#### 3.1 Estructura de la Barra Superior (Fila 0)
- De 5 menús dispersos a 4 menús limpios y ordenados:
  ```
  S6ED | File    Edit    Settings    Help
  ```
- Accesos rápidos directos por teclado:
  - `F1` / `Alt+F`: Menú **File** (`New`, `Open...`, `Save`, `Save As...`, `Quit`).
  - `F2` / `Alt+E`: Menú **Edit** (`Cut`, `Copy`, `Paste`, `Delete Line`, `Select All`, `Deselect`, `Go to Line...`, `Find...`).
  - `F3` / `Alt+S`: Menú **Settings** (`Settings...`, `Save to CFG`, `Reload CFG`).
  - `F4` / `Alt+H`: Menú **Help** (`Keyboard Help...`, `About S6ED...`).

#### 3.2 Diálogo Modal `Settings...`
Un único diálogo integral con navegación por teclado (`TAB`, `Cursores`, `Espacio`, `Enter`, `ESC`):
- **Editing:**
  - Wrap Mode: `( ) Dev ( ) Text`
  - Autoalign: `( ) Off ( ) On`
  - Tab Width: `( ) 2  ( ) 4  ( ) 8`
  - Insert Mode: `( ) Insert ( ) Overwrite`
- **Format & Display:**
  - Line Endings: `( ) DOS (CRLF) ( ) UNIX (LF)`
  - Markup: `( ) Off ( ) Markdown ( ) Lite`
  - Show Clock: `[X] Enabled`
  - Keymap Profile: `( ) Standard ( ) Vi ( ) TED ( ) Emacs`
- **Actions:**
  - `[  OK  ]` (Aplica los cambios en la sesión activa).
  - `[ SAVE ]` (Aplica y persiste inmediatamente en `S6ED.CFG` / `S2ED.CFG`).
  - `[CANCEL]` (Descarta cambios).

---

### Fase 4: Navegador de Ficheros (Open... / Save As...)

#### 4.1 Presupuesto de Memoria Estricto (`FTRSEG`)
- **Premisa Irrenunciable:** **NO consumir un nuevo segmento del Memory Mapper.**
- **Presupuesto disponible en `FTRSEG`:**
  - En S6ED: **10,110 bytes libres**.
  - En S2ED: **4,575 bytes libres**.
- **Estrategia de Optimización:**
  1. **Buffer de Entrada/Directorio:**
     - En lugar de reservar arrays estáticos en RAM de variables, se reutiliza temporalmente `CLIPBUF` (2,048 bytes en TPA RAM) o el área libre de Page 1 mientras el diálogo modal está activo.
     - Cada entrada de fichero ocupa 13 bytes (`NAME8` + `EXT3` + `ATTR1` + flags). Con 64 ficheros en el buffer de vista son solo 832 bytes.
  2. **Escáner BDOS:**
     - Uso de llamadas BDOS DOS 2 `_FFIRST` (`#40`) y `_FNEXT` (`#41`) con máscara `*.*`.
     - Soporte para subdirectorios (`..` para subir de nivel, carpetas marcadas con `<DIR>`).
  3. **Interfaz de Ventana:**
     - Reutiliza la maquinaria `WINBOX`, `WINPRN`, `WINLIST` con dos flechas de scroll, una lista de ficheros seleccionable con cursores/Enter, un campo de texto para nombre editable y botones `[Open]`/`[Save]` y `[Cancel]`.

---

### Fase 5: Perfil de Teclado TED (`KMAPTED`)

- Sustitución de `KMAPWS` (WordStar) por **`KMAPTED`**.
- Incorporación de los atajos y paradigmas ergonómicos clásicos de TED (MSX-DOS 2 Tools):
  - `Home`: Reflow de párrafo / Indentación.
  - `Shift+Del`: Borrar hasta el fin de línea.
  - `Ctrl+Del`: Borrar línea completa.
  - `Shift+Cursores`: Mover palabra por palabra o salto de página.
  - `Select`: Selector de comandos especiales.

---

## 3. Estado de Ejecución

1. **Fase 1: Barra de Estado Derecha & Indicadores Compactos — COMPLETADA (100% Green)**
   - `DRWSTAT` rediseñado en S6ED y S2ED con telemetría fija a la derecha y tira compacta de flags `[W|A|M|I]*`.
   - Canal izquierdo (cols 0..42 en S6ED, 0..27 en S2ED) reservado para mensajes efímeros (`STATMSG`), aviso `[ROM]` y consola de comandos.
   - Rendimiento diferencial por celda preservado sin regresiones de rendimiento ni artefactos OCR.

2. **Fase 2: Consola de Comandos de VI (`: ex mode`) — COMPLETADA (100% Green)**
   - Tecla `:` despacha a `ACEXMOD` en Modo Normal VI (`KMAPVIN`).
   - Entrada de comandos interactiva sobre la fila de estado: soporta edición con caracteres imprimibles, `BS`/`DEL` (cancelación al borrar `:` inicial), `ESC` (cancelación limpia) y `RETURN` (ejecución).
   - Intérprete residente soporta:
     - `:<line>` -> salto a línea vía `GOTOLN`.
     - `:w` / `:w <file>` -> guardado / guardar como vía `FILESAVE`.
     - `:q` -> comprobación de buffer sucio (`MODIFIED`); si está sucio avisa `"No write since last change (! overrides)"`; si está limpio sale vía `TERM`.
     - `:q!` -> salida forzada inmediata vía `TERM`.
     - `:wq` / `:x` -> guardado y salida.
     - `:e <file>` / `:e!` -> carga de fichero vía `FILELOAD`.
   - Cobertura completa de verificación mediante la nueva suite `H27ViEx` en `TEST/gate.py` (6 checks PASS).

3. **Próximo Paso: Fase 3 (Reorganización de Menús y Diálogo Unificado 'Settings...')**
   - Presentar especificación técnica detallada y solicitar aprobación de usuario antes de proceder.
