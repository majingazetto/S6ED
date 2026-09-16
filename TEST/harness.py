"""S6ED test harness -- one openMSX session, headless.

The loop is always the same: build a fixture disk, generate the .tcl from the
.sym the build just produced, launch openMSX silently with -script, let the
script log and exit, then read the log and the dumps from the shell.

Two rules are load-bearing and both were learned the expensive way:

  * The schedule is relative to T0, the first time the editor reaches MAINLOOP
    with its own opcodes still in place -- never to an absolute boot time.
  * Every sample is taken inside a breakpoint in our own code.  A timer sample
    catches the DOS 2 kernel over page 0 or the Disk ROM over page 1 and
    returns phantom values that look exactly like corruption.
"""

import hashlib
import os
import shutil
import subprocess

TEXT_VRAM_ADDR = 8 * 128          # display line 8: first text row
TEXT_VRAM_LEN = 192 * 128         # 24 rows x 8 scanlines x 128 bytes/line
SEGSIZE = 16384

MACH_128K = ('Philips_NMS_8250', 'msxdos2')
MACH_2MB = ('Boosted_MSX2_EN', 'msxdos2')

# Variables every snapshot carries.  Cheap, and having them on a failing run is
# the difference between a diagnosis and another session.
DEFAULT_VARS = [
    ('TOTLINES', 2), ('DOCLINE', 2), ('TOPLINE', 2), ('CURX', 1), ('CURY', 1),
    ('MODIFIED', 1), ('SEGCNT', 1), ('LINEOFF', 2), ('FREEHD', 1),
    ('FREEOF', 2), ('TXSEG', 1), ('APPSEG', 1), ('DIRSEG', 1), ('TXSEG0', 1),
    ('SELACT', 1), ('SELDRAWN', 1), ('CLIPLEN', 2), ('WRAPMODE', 1),
    ('TABWIDTH', 1), ('AUTOALGN', 1), ('KMAPID', 1), ('MKUPMD', 1),
    ('SAVEEOL', 1), ('CLKPH', 1), ('CLKHZ', 1), ('SCRRDY', 1),
    ('SHOWCLK', 1), ('CLKMIN', 1), ('KMAPID', 1), ('VIMODE', 1),
    ('FNTOK', 1), ('FNTROMD', 1),
    ('SAVSCRMD', 1), ('SAVL40', 1), ('SAVLLEN', 1),
    ('SAVFORC', 1), ('SAVBAKC', 1), ('SAVBDRC', 1),
    ('SCRMOD', 1), ('LINLEN', 1), ('LINL40', 1),
    ('FORCLR', 1), ('BAKCLR', 1), ('BDRCLR', 1),
]

# Byte ranges worth having whole.  The selection records are here because a
# range addressed by IX+n is a layout contract: seeing all six bytes of both is
# what tells a corrupted painted range from an honest one.
BYTE_VARS = [
    ('SELSTRL', 6), ('DRWSTRL', 6), ('CLKBUF', 6), ('PALDATA', 8),
    ('STATBUF', 80),
]

HOOK_ADDR = 0xFD9F      # H.TIMI: nothing of ours may ever live behind it


class Run(object):
    """What one session produced: log keys, snapshots and dumped files."""

    def __init__(self, case, out_dir):
        self.case = case
        self.out_dir = out_dir
        self.snaps = {}        # label -> {var: value}
        self.files = {}        # (label, kind) -> path
        self.lines = []
        self.timed_out = False
        self.returncode = None

    def var(self, label, name):
        return self.snaps.get(label, {}).get(name)

    def blob(self, label, kind):
        path = self.files.get((label, kind))
        if not path or not os.path.exists(path):
            return None
        with open(path, 'rb') as fh:
            return fh.read()

    def md5(self, label, kind):
        b = self.blob(label, kind)
        return hashlib.md5(b).hexdigest() if b is not None else None


class Session(object):
    def __init__(self, ctx, case, variant=None):
        self.ctx = ctx
        self.case = case
        self.variant = variant
        self.dir = os.path.join(ctx.out_dir,
                                case.name + ('-' + variant if variant else ''))
        shutil.rmtree(self.dir, ignore_errors=True)
        os.makedirs(self.dir)

    # - disk -----------------------------------------------------------

    def build_disk(self):
        """Fresh DOS2 base every time, so a run can never inherit the last one."""
        ctx, case = self.ctx, self.case
        dsk = os.path.join(self.dir, 'T.DSK')
        shutil.copy(os.path.join(ctx.res_dir, 'DOS2.DSK'), dsk)

        staged = []
        for name, data in case.disk_files(ctx, self.variant).items():
            path = os.path.join(self.dir, name)
            mode = 'wb' if isinstance(data, bytes) else 'w'
            with open(path, mode) as fh:
                fh.write(data)
            staged.append(path)
        for src in case.disk_copies(ctx):  # noqa: E501
            dst = os.path.join(self.dir, os.path.basename(src))
            if os.path.abspath(src) != os.path.abspath(dst):
                shutil.copy(src, dst)
            staged.append(dst)

        subprocess.run([ctx.dsktool, 'D', dsk] +
                       [os.path.basename(p) for p in staged],
                       cwd=self.dir, capture_output=True)
        r = subprocess.run([ctx.dsktool, 'A', dsk] + staged,
                           cwd=self.dir, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError('dsktool A failed: %s' % (r.stdout + r.stderr))
        return dsk

    def extract(self, dsk, name):
        """The end-to-end verdict is read back off the disk, not off the screen."""
        r = subprocess.run([self.ctx.dsktool, 'E', dsk, name],
                           cwd=self.dir, capture_output=True, text=True)
        path = os.path.join(self.dir, name)
        if r.returncode != 0 or not os.path.exists(path):
            return None
        with open(path, 'rb') as fh:
            return fh.read()

    # - tcl ------------------------------------------------------------

    def _signature(self, addr, count=4):
        """The opcodes at `addr` as built, for gating breakpoints.

        A plausible gate on a variable is not enough: one false hit reported
        TOTLINES = 7109 with a garbage SEGTBL.  The gate has to assert that the
        bytes at the breakpoint address are still ours.
        """
        com = os.path.join(self.ctx.code_dir, 'S6ED.COM')
        with open(com, 'rb') as fh:
            image = fh.read()
        off = addr - 0x100
        return list(image[off:off + count])

    def tcl(self, timeline):
        ctx, sym = self.ctx, self.ctx.sym
        main = sym['MAINLOOP']
        sig = self._signature(main)
        out = self.dir.replace('\\', '/')

        L = []
        a = L.append
        a('# generated by the S6ED test harness -- regenerated on every build,')
        a('# because a rebuild moves every symbol and a stale script reads zeros.')
        a('set OUT "%s"' % out)
        a('set LOGF [open "$OUT/run.log" w]')
        a('# No video output at all.  This is not only the fastest mode')
        a('# (measured: ~380 emulated seconds per wall-clock second, against')
        a('# ~2 with a window) -- with a window openMSX simply STOPS when it')
        a('# is not the foreground app, and a frozen emulator looks exactly')
        a('# like a program that never booted.  Nothing here needs a picture:')
        a('# every verdict is taken from VRAM, RAM or the disk.')
        a('set renderer none')
        a('proc p {m} { global LOGF; puts $LOGF $m; flush $LOGF }')
        a('proc rb {a} { return [debug read memory $a] }')
        a('proc rw {a} { return [expr {[debug read memory $a] +'
          ' 256 * [debug read memory [expr {$a + 1}]]}] }')
        a('proc dump {dbg addr len name} {')
        a('    global OUT')
        a('    set blk [debug read_block $dbg $addr $len]')
        a('    set f [open "$OUT/$name" w]')
        a('    fconfigure $f -translation binary')
        a('    puts -nonewline $f $blk')
        a('    close $f')
        a('}')
        a('')
        a('set MAIN %d' % main)
        a('set SIG {%s}' % ' '.join(str(b) for b in sig))
        a('set SCRRDY %d' % sym['SCRRDY'])
        a('# The editor is "ours" only when its own opcodes are still at MAINLOOP')
        a('# and it has finished initialising.')
        a('proc ready {} {')
        a('    set i 0')
        a('    foreach b $::SIG {')
        a('        if {[rb [expr {$::MAIN + $i}]] != $b} { return 0 }')
        a('        incr i')
        a('    }')
        a('    return [expr {[rb $::SCRRDY] == 255}]')
        a('}')
        a('')
        a('set ::t0 0')
        a('set ::pending 0')
        a('set ::finished 0')
        a('')

        # snapshot bodies
        for i, (off, label, spec) in enumerate(timeline.snaps):
            a(self._snap_proc(i, label, spec))

        a('proc finish {} {')
        a('    if {$::pending > 0} { after time 0.2 finish; return }')
        a('    p "DONE"')
        a('    close $::LOGF')
        a('    exit 0')
        a('}')
        a('')
        a('proc schedule {} {')
        for off, cmd in sorted(timeline.events, key=lambda e: e[0]):
            a('    after time [expr {$::t0 + %.3f}] {%s}' % (off, cmd))
        for i, (off, label, spec) in enumerate(timeline.snaps):
            a('    after time [expr {$::t0 + %.3f}] {arm_snap%d}' % (off, i))
        a('    after time [expr {$::t0 + %.3f}] {finish}'
          % (timeline.t + 1.0))
        a('}')
        a('')
        a('set ::bpid [debug set_bp $MAIN {} {')
        a('    if {$::t0 != 0} return')
        a('    if {![ready]} return')
        a('    set ::t0 [machine_info time]')
        a('    p [format "T0 %.3f" $::t0]')
        a('    debug remove_bp $::bpid')
        a('    schedule')
        a('}]')
        a('')
        a('# Always arm an own timeout: a hung emulator killed from outside')
        a('# leaves no log, which is indistinguishable from a broken program.')
        a('after time %.1f { p "TIMEOUT"; close $::LOGF; exit 1 }'
          % (timeline.t + 400.0))
        a('set throttle off')
        return '\n'.join(L) + '\n'

    def _snap_proc(self, i, label, spec):
        sym = self.ctx.sym
        varlist = spec['vars'] or DEFAULT_VARS
        L = []
        a = L.append
        a('set ::snapdone%d 0' % i)
        a('proc take_snap%d {} {' % i)
        for name, size in varlist:
            if name not in sym.addr:
                continue
            fn = 'rb' if size == 1 else 'rw'
            a('    p "KV %s %s [%s %d]"' % (label, name, fn, sym[name]))
        for name, count in BYTE_VARS:
            if name not in sym.addr:
                continue
            a('    set t ""')
            a('    for {set i 0} {$i < %d} {incr i} {'
              ' append t "[rb [expr {%d + $i}]] " }' % (count, sym[name]))
            a('    p "KB %s %s $t"' % (label, name))
        # The stack, and the interrupt hook that must never point into page 1.
        a('    p "KV %s SP [reg SP]"' % label)
        a('    set t ""')
        a('    for {set i 0} {$i < 5} {incr i} {'
          ' append t "[rb [expr {%d + $i}]] " }' % HOOK_ADDR)
        a('    p "KB %s HTIMI $t"' % label)
        # SEGTBL as a whole, so segment accounting can be checked
        a('    set t ""')
        a('    for {set i 0} {$i < %d} {incr i} {'
          ' append t "[rb [expr {%d + $i}]] " }' % (32, sym['SEGTBL']))
        a('    p "KV %s SEGTBL $t"' % label)
        if spec.get('palette'):
            a('    dump "VDP palette" 0 32 %s.pal' % label)
        if spec['image']:
            # The whole emitted image: nothing may ever write into it.
            a('    dump memory 256 %d %s.image' % (sym['VARS'] - 0x100, label))
        if spec['dirseg']:
            # Main RAM exposes every mapper segment at once, so the directory
            # can be walked with the machine untouched -- no banking, no side
            # effects, even though DIRSEG is not currently in the window.
            a('    set seg [rb %d]' % sym['DIRSEG'])
            a('    dump "Main RAM" [expr {$seg * %d}] %d %s.dir'
              % (SEGSIZE, SEGSIZE, label))
            a('    for {set s 0} {$s < [rb %d]} {incr s} {' % sym['SEGCNT'])
            a('        set n [rb [expr {%d + $s}]]' % sym['SEGTBL'])
            a('        dump "Main RAM" [expr {$n * %d}] %d %s.seg$s'
              % (SEGSIZE, SEGSIZE, label))
            a('    }')
        a('    p "SNAP %s"' % label)
        if spec['vram']:
            # DRWCUR returns while the VDP is still painting the cursor cell,
            # so let a couple of milliseconds of emulated time pass first.
            if spec['vram'] == 'menu':
                addr, length, kind = 0, 8 * 128, 'menu'
            elif spec['vram'] == 'font':
                addr, length, kind = 0x8000, 32768, 'font'
            else:
                addr, length, kind = TEXT_VRAM_ADDR, TEXT_VRAM_LEN, 'vram'
            a('    after time 0.002 {')
            a('        dump VRAM %d %d %s.%s' % (addr, length, label, kind))
            a('        incr ::pending -1')
            a('    }')
        else:
            a('    incr ::pending -1')
        a('}')
        target = spec.get('at')
        if target:
            target_addr = sym[target]
            a('proc arm_snap%d {} {' % i)
            a('    incr ::pending')
            a('    set ::sbp%d [debug set_bp %d {} {' % (i, target_addr))
            a('        debug remove_bp $::sbp%d' % i)
            a('        take_snap%d' % i)
            a('    }]')
            a('}')
        else:
            a('proc arm_snap%d {} {' % i)
            a('    incr ::pending')
            a('    set ::sbp%d [debug set_bp $::MAIN {} {' % i)
            a('        if {![ready]} return')
            a('        debug remove_bp $::sbp%d' % i)
            a('        take_snap%d' % i)
            a('    }]')
            a('}')
        return '\n'.join(L) + '\n'

    # - run ------------------------------------------------------------

    def run(self, timeline, timeout=900):
        dsk = self.build_disk()
        script = os.path.join(self.dir, 'run.tcl')
        with open(script, 'w') as fh:
            fh.write(self.tcl(timeline))

        machine, ext = self.case.machine
        cmd = ['openmsx', '-machine', machine, '-ext', ext,
               '-diska', dsk, '-script', script]
        run = Run(self.case, self.dir)
        # openMSX's own output goes to FILES, never to pipes: with a pipe it
        # stalls before the machine boots (measured: 0% CPU, empty log, looks
        # exactly like a program that never started).  The files are worth
        # keeping anyway -- that is where a failed -testconfig shows up.
        with open(os.path.join(self.dir, 'openmsx.out'), 'w') as so, \
                open(os.path.join(self.dir, 'openmsx.err'), 'w') as se:
            try:
                proc = subprocess.run(cmd, stdout=so, stderr=se,
                                      stdin=subprocess.DEVNULL, timeout=timeout)
                run.returncode = proc.returncode
            except subprocess.TimeoutExpired:
                run.timed_out = True

        log = os.path.join(self.dir, 'run.log')
        if os.path.exists(log):
            with open(log) as fh:
                run.lines = fh.read().splitlines()
        for line in run.lines:
            if line.startswith('KV '):
                _, label, name, value = line.split(' ', 3)
                store = run.snaps.setdefault(label, {})
                store[name] = (value.strip() if name == 'SEGTBL'
                               else int(value))
            elif line.startswith('KB '):
                _, label, name, value = line.split(' ', 3)
                run.snaps.setdefault(label, {})[name] = [
                    int(v) for v in value.split()]
        for (_, label, spec) in timeline.snaps:
            for kind in ('vram', 'menu', 'dir', 'image', 'pal', 'font'):
                path = os.path.join(self.dir, '%s.%s' % (label, kind))
                if os.path.exists(path):
                    run.files[(label, kind)] = path
        run.dsk = dsk
        run.session = self
        return run
