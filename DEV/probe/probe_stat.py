#!/usr/bin/env python3
# Per-keystroke probe: what repaints the status bar, and when.
# Anchors on the harness MAINLOOP breakpoint + code-signature gate, then
# schedules relative to the real boot time.
import os, re, subprocess, sys

SP = os.path.dirname(os.path.abspath(__file__))
CODE = os.path.dirname(os.path.dirname(SP)) + '/CODE'
LOG = '/tmp/s6ed_probe.log'

sym = {m.group(1): int(m.group(2), 16)
       for m in (re.match(r'([\w.]+):\s*EQU\s*0x([0-9A-Fa-f]+)', l.strip())
                 for l in open(CODE + '/S6ED.sym')) if m}

need = ['MAINLOOP', 'DISPKEY', 'DRWSTAT', 'STATCEL', 'DRWCUR', 'VDPCMD',
        'BLDSTAT', 'SCRRDY', 'VDP_DX', 'VDP_DY']
for n in need:
    assert n in sym, n

image = open(CODE + '/S6ED.COM', 'rb').read()
off = sym['MAINLOOP'] - 0x100
sig = ' '.join(str(b) for b in image[off:off + 4])

# fixture disk
subprocess.run(['cp', CODE + '/../RES/DOS2.DSK', SP + '/probe.dsk'],
               check=True)
open(SP + '/TEST.TXT', 'wb').write(
    b'\r\n'.join(b'LINE %05d ABCDEFGHIJ' % i for i in range(1, 51)) + b'\r\n')
open(SP + '/AUTOEXEC.BAT', 'wb').write(b's6ed TEST.TXT\r\n')
staged = [CODE + '/S6ED.COM', CODE + '/S6ED.FNT', CODE + '/S6ED.DAT',
          SP + '/TEST.TXT', SP + '/AUTOEXEC.BAT']
subprocess.run([CODE + '/../../msxtools/bin/dsktool', 'D', SP + '/probe.dsk'] +
               [os.path.basename(p) for p in staged], cwd=SP,
               capture_output=True)
r = subprocess.run([CODE + '/../../msxtools/bin/dsktool', 'A',
                    SP + '/probe.dsk'] + staged, cwd=SP,
                   capture_output=True, text=True)
if r.returncode != 0:
    sys.exit('dsktool: ' + r.stdout + r.stderr)

tcl = '''
set LOGF [open "@LOG@" w]
proc p {m} { global LOGF; puts $LOGF $m; flush $LOGF }
proc ts {} { return [format "%.3f" [expr {[machine_info time]*1000.0}]] }
proc rb {a} { return [debug read memory $a] }
proc rw {a} { return [expr {[debug read memory $a] + 256*[debug read memory [expr {$a+1}]]}] }

set MAIN @MAINLOOP@
set SIG {@SIG@}
set RDY @SCRRDY@
proc ready {} {
    set i 0
    foreach b $::SIG {
        if {[rb [expr {$::MAIN + $i}]] != $b} { return 0 }
        incr i
    }
    return [expr {[rb $::RDY] == 255}]
}

set ::t0 0
proc schedule {} {
    after time [expr {$::t0 + 2.00}] { p "KEY X down"; keymatrixdown 5 0x20 }
    after time [expr {$::t0 + 2.25}] { keymatrixup 5 0x20 }
    after time [expr {$::t0 + 3.00}] { p "KEY X down2"; keymatrixdown 5 0x20 }
    after time [expr {$::t0 + 3.25}] { keymatrixup 5 0x20 }
    after time [expr {$::t0 + 4.50}] { p "DONE"; close $::LOGF; exit 0 }
}

proc arm {} {
    debug set_bp 0x@DISPKEY@ {} { p "[ts] DISPKEY" }
    debug set_bp 0x@VDPCMD@ {} {
        p "[ts]   VDPCMD DX=[rw 0x@VDP_DX@] DY=[rw 0x@VDP_DY@]"
    }
    debug set_bp 0x@BLDSTAT@ {} { p "[ts]   BLDSTAT" }
    debug set_bp 0x@STATCEL@ {} { p "[ts]     STATCEL col=[reg C] ch=[reg A]" }
    debug set_bp 0x@DRWCUR@ {} { p "[ts]   DRWCUR" }
}

set ::bpid [debug set_bp $MAIN {} {
    if {$::t0 != 0} return
    if {![ready]} return
    set ::t0 [machine_info time]
    p [format "T0 %.3f" $::t0]
    debug remove_bp $::bpid
    arm
    schedule
}]

after time 240 { p "TIMEOUT"; close $::LOGF; exit 1 }
set renderer none
set throttle off
'''
for k, v in {'LOG': LOG, 'MAINLOOP': '%d' % sym['MAINLOOP'],
             'SIG': sig, 'SCRRDY': '%d' % sym['SCRRDY'],
             'DISPKEY': '%04X' % sym['DISPKEY'],
             'VDPCMD': '%04X' % sym['VDPCMD'],
             'BLDSTAT': '%04X' % sym['BLDSTAT'],
             'STATCEL': '%04X' % sym['STATCEL'],
             'DRWCUR': '%04X' % sym['DRWCUR'],
             'VDP_DX': '%04X' % sym['VDP_DX'],
             'VDP_DY': '%04X' % sym['VDP_DY']}.items():
    tcl = tcl.replace('@' + k + '@', v)

open(SP + '/probe.tcl', 'w').write(tcl)
print('symbols ok, fixture ok, tcl written')
