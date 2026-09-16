"""MSX key matrix and the input timeline.

Two mechanisms and they are not interchangeable.  `type` goes through the BIOS
keyboard buffer and is fine for plain ASCII; anything else -- cursors, chords,
function keys, and any code that polls the PPI directly, which is most of
S6ED's modifier handling -- has to drive the real matrix.

Hold times matter and short holds fail SILENTLY: 0.10 s dropped keystrokes and
lost every CTRL combination.  0.25 s down / 0.35 s gap is the measured floor.
"""

# (row, bit mask) from the standard QWERTY matrix.
KEY = {
    'SHIFT': (6, 0x01), 'CTRL': (6, 0x02), 'GRAPH': (6, 0x04),
    'CAPS': (6, 0x08), 'CODE': (6, 0x10), 'KANA': (6, 0x10),
    'F1': (6, 0x20), 'F2': (6, 0x40), 'F3': (6, 0x80),
    'F4': (7, 0x01), 'F5': (7, 0x02), 'ESC': (7, 0x04), 'TAB': (7, 0x08),
    'STOP': (7, 0x10), 'BS': (7, 0x20), 'SELECT': (7, 0x40),
    'RETURN': (7, 0x80),
    'SPACE': (8, 0x01), 'HOME': (8, 0x02), 'INS': (8, 0x04), 'DEL': (8, 0x08),
    'LEFT': (8, 0x10), 'UP': (8, 0x20), 'DOWN': (8, 0x40), 'RIGHT': (8, 0x80),
}
for _i, _c in enumerate('01234567'):
    KEY[_c] = (0, 1 << _i)
for _i, _c in enumerate("89-=\\[];"):
    KEY[_c] = (1, 1 << _i)
KEY.update({"'": (2, 0x01), '`': (2, 0x02), ',': (2, 0x04), '.': (2, 0x08),
            '/': (2, 0x10), '?': (2, 0x10), 'ACCENT': (2, 0x20), 'A': (2, 0x40),
            'B': (2, 0x80)})
for _i, _c in enumerate('CDEFGHIJ'):
    KEY[_c] = (3, 1 << _i)
for _i, _c in enumerate('KLMNOPQR'):
    KEY[_c] = (4, 1 << _i)
for _i, _c in enumerate('STUVWXYZ'):
    KEY[_c] = (5, 1 << _i)

HOLD = 0.25          # key held down
GAP = 0.35           # between keystrokes
MODLEAD = 0.25       # modifier down before the key
MODTAIL = 0.45       # after the modifier comes back up
TYPE_PER_CHAR = 0.16  # emulated seconds `type` needs per character


class Timeline(object):
    """Events at offsets from T0, the moment the editor first reaches MAINLOOP.

    Absolute times are never written down: T0 is measured at run time from a
    gated breakpoint, so the schedule survives a fixture that takes longer to
    load or a machine that boots at a different speed.
    """

    def __init__(self, start=1.0):
        self.t = start
        self.events = []      # (offset, tcl command)
        self.snaps = []       # (offset, label, spec)

    # - raw ------------------------------------------------------------

    def at(self, cmd, dt=0.0):
        self.events.append((self.t + dt, cmd))
        return self

    def wait(self, seconds):
        self.t += seconds
        return self

    # - input ----------------------------------------------------------

    def press(self, key, mods=(), repeat=1, tail=None):
        """One keystroke, optionally under SHIFT / CTRL / GRAPH.

        `tail` overrides the pause after the modifier comes back up.  A short
        one lands the next key-down inside the work MAINLOOP does after a
        keystroke, which is where the window between its CHKACNT poll and its
        CHSNS poll is widest -- D8 needs that to provoke the GRAPH double.
        """
        for _ in range(repeat):
            for m in mods:
                self.at('keymatrixdown %d 0x%02X' % KEY[m])
            if mods:
                self.t += MODLEAD
            row, mask = KEY[key]
            self.at('keymatrixdown %d 0x%02X' % (row, mask))
            self.t += HOLD
            self.at('keymatrixup %d 0x%02X' % (row, mask))
            self.t += MODLEAD if mods else 0.0
            for m in mods:
                self.at('keymatrixup %d 0x%02X' % KEY[m])
            if mods:
                self.t += MODTAIL if tail is None else tail
            else:
                self.t += GAP if tail is None else tail
        return self

    def text(self, s):
        """Plain ASCII through the BIOS buffer -- much faster than the matrix."""
        self.at('type %s' % _tcl_str(s))
        self.t += TYPE_PER_CHAR * len(s) + 0.4
        return self

    # - observation ----------------------------------------------------

    def snap(self, label, vram=False, dirseg=False, image=False,
             palette=False, vars_=None, at=None):
        """Sample state at a breakpoint inside our own code.

        Never asynchronously from a timer: a timer sample catches the DOS 2
        kernel in page 0 or the Disk ROM in page 1 and hands back 16 kB of
        phantom corruption.
        """
        self.snaps.append((self.t, label, {
            'vram': vram, 'dirseg': dirseg, 'image': image,
            'palette': palette, 'vars': list(vars_) if vars_ else None,
            'at': at}))
        self.t += 0.6
        return self


def _tcl_str(s):
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"').replace(
        '[', '\\[').replace('$', '\\$') + '"'
