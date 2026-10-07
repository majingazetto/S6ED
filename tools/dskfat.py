#!/usr/bin/env python3
"""dskfat -- FAT12 .DSK images with subdirectories (MSX-DOS 2 / Nextor).

dsktool only knows the root directory.  This adds, lists and extracts files in
any directory of a FAT12 floppy image, creating the directories it needs, so a
disk can be laid out the way it is used: the program in A:\\TOOLS on the PATH,
the documents somewhere else.

    dskfat.py IMAGE mkdir DIR                 create DIR (and its parents)
    dskfat.py IMAGE add [--date=Y-M-DTH:M] DIR FILE[=NAME] ...
                                              copy host FILEs into DIR
    dskfat.py IMAGE attr PATH [+|-][rhsa]...  set or clear attribute bits
    dskfat.py IMAGE ls [DIR]                  list DIR (default: the root)
    dskfat.py IMAGE get PATH [HOSTFILE]       extract one file

DIR and PATH use "\\" or "/" and are relative to the root ("TOOLS", "DEV\\SUB",
"\\" or "." for the root).  NAME defaults to the host file name, upper-cased;
FILE=NAME is accepted too, to add several files under other names.  A file
that already exists is replaced (its old cluster chain is freed first).  The
geometry is read from the boot sector's BPB, so any FAT12 image works.
"""

import datetime
import os
import struct
import sys

ATTR_DIR = 0x10
ATTR_ARC = 0x20
ATTR_VOL = 0x08
ENTRY = 32


class Fat12(object):
    def __init__(self, path):
        self.path = path
        with open(path, 'rb') as fh:
            self.img = bytearray(fh.read())
        b = self.img
        (self.bps,) = struct.unpack_from('<H', b, 11)
        self.spc = b[13]
        (self.reserved,) = struct.unpack_from('<H', b, 14)
        self.nfats = b[16]
        (self.rootents,) = struct.unpack_from('<H', b, 17)
        (total,) = struct.unpack_from('<H', b, 19)
        (self.spf,) = struct.unpack_from('<H', b, 22)
        if self.bps not in (512, 1024) or not self.spc or not self.nfats:
            raise SystemExit('%s: no FAT12 BPB in the boot sector' % path)
        self.fat_off = self.reserved * self.bps
        self.root_off = self.fat_off + self.nfats * self.spf * self.bps
        self.data_off = self.root_off + self.rootents * ENTRY
        self.csize = self.spc * self.bps
        self.nclus = (total * self.bps - self.data_off) // self.csize
        if self.nclus >= 4085:
            raise SystemExit('%s: FAT16 volume, not FAT12' % path)
        self.fat = [self._fat_get(i) for i in range(self.nclus + 2)]

    # - FAT ------------------------------------------------------------

    def _fat_get(self, n):
        off = self.fat_off + n * 3 // 2
        v = self.img[off] | (self.img[off + 1] << 8)
        return (v >> 4) if n & 1 else (v & 0xFFF)

    def _fat_put_all(self):
        for copy in range(self.nfats):
            base = self.fat_off + copy * self.spf * self.bps
            for n in range(2, self.nclus + 2):
                off = base + n * 3 // 2
                v = self.fat[n]
                if n & 1:
                    self.img[off] = (self.img[off] & 0x0F) | ((v << 4) & 0xF0)
                    self.img[off + 1] = (v >> 4) & 0xFF
                else:
                    self.img[off] = v & 0xFF
                    self.img[off + 1] = (self.img[off + 1] & 0xF0) | (v >> 8)

    def chain(self, first):
        out = []
        n = first
        while 2 <= n < 0xFF8:
            if n in out or n >= self.nclus + 2:
                raise SystemExit('corrupt FAT chain at cluster %d' % n)
            out.append(n)
            n = self.fat[n]
        return out

    def alloc(self, count):
        free = [n for n in range(2, self.nclus + 2) if self.fat[n] == 0][:count]
        if len(free) < count:
            raise SystemExit('%s: disk full' % self.path)
        for a, b in zip(free, free[1:]):
            self.fat[a] = b
        if free:
            self.fat[free[-1]] = 0xFFF
        return free

    def free_chain(self, first):
        for n in self.chain(first):
            self.fat[n] = 0

    def coff(self, n):
        return self.data_off + (n - 2) * self.csize

    # - directories ----------------------------------------------------

    def slots(self, dirclus):
        """Byte offsets of every entry slot of a directory (0 = the root)."""
        if dirclus == 0:
            return [self.root_off + i * ENTRY for i in range(self.rootents)]
        return [self.coff(c) + i * ENTRY for c in self.chain(dirclus)
                for i in range(self.csize // ENTRY)]

    def entries(self, dirclus):
        for off in self.slots(dirclus):
            first = self.img[off]
            if first == 0:
                break
            if first == 0xE5 or self.img[off + 11] & ATTR_VOL:
                continue
            yield off

    def find(self, dirclus, name83):
        for off in self.entries(dirclus):
            if bytes(self.img[off:off + 11]) == name83:
                return off
        return None

    def free_slot(self, dirclus):
        for off in self.slots(dirclus):
            if self.img[off] in (0, 0xE5):
                return off
        if dirclus == 0:
            raise SystemExit('%s: root directory full' % self.path)
        # grow the subdirectory by one zeroed cluster
        last = self.chain(dirclus)[-1]
        (new,) = self.alloc(1)
        self.fat[last] = new
        self.img[self.coff(new):self.coff(new) + self.csize] = \
            bytes(self.csize)
        return self.coff(new)

    stamp = None                    # datetime for new entries; None = now

    def write_entry(self, off, name83, attr, clus, size):
        now = self.stamp or datetime.datetime.now()
        t = (now.hour << 11) | (now.minute << 5) | (now.second // 2)
        d = ((max(now.year, 1980) - 1980) << 9) | (now.month << 5) | now.day
        e = bytearray(ENTRY)
        e[0:11] = name83
        e[11] = attr
        struct.pack_into('<HHHI', e, 22, t, d, clus, size)
        self.img[off:off + ENTRY] = e

    def resolve(self, dirpath, create=False):
        """Cluster of a directory path, 0 for the root."""
        clus = 0
        for part in split_path(dirpath):
            name83 = to83(part)
            off = self.find(clus, name83)
            if off is None:
                if not create:
                    raise SystemExit('no such directory: %s' % dirpath)
                clus = self._mkdir(clus, name83)
                continue
            if not self.img[off + 11] & ATTR_DIR:
                raise SystemExit('not a directory: %s' % part)
            (clus,) = struct.unpack_from('<H', self.img, off + 26)
        return clus

    def _mkdir(self, parent, name83):
        (clus,) = self.alloc(1)
        base = self.coff(clus)
        self.img[base:base + self.csize] = bytes(self.csize)
        self.write_entry(self.free_slot(parent), name83, ATTR_DIR, clus, 0)
        self.write_entry(base, b'.          ', ATTR_DIR, clus, 0)
        self.write_entry(base + ENTRY, b'..         ', ATTR_DIR, parent, 0)
        return clus

    # - files ----------------------------------------------------------

    def add(self, dirclus, name83, data):
        off = self.find(dirclus, name83)
        if off is not None:
            if self.img[off + 11] & ATTR_DIR:
                raise SystemExit('%s is a directory' % from83(name83))
            (old,) = struct.unpack_from('<H', self.img, off + 26)
            self.free_chain(old)
        else:
            off = self.free_slot(dirclus)
        count = (len(data) + self.csize - 1) // self.csize
        clusters = self.alloc(count)
        for i, c in enumerate(clusters):
            piece = data[i * self.csize:(i + 1) * self.csize]
            base = self.coff(c)
            self.img[base:base + self.csize] = piece.ljust(self.csize, b'\0')
        self.write_entry(off, name83, ATTR_ARC,
                         clusters[0] if clusters else 0, len(data))

    def read(self, off):
        (clus, size) = struct.unpack_from('<HI', self.img, off + 26)
        out = b''.join(bytes(self.img[self.coff(c):self.coff(c) + self.csize])
                       for c in self.chain(clus))
        return out[:size]

    def save(self):
        self._fat_put_all()
        with open(self.path, 'wb') as fh:
            fh.write(self.img)


def split_path(p):
    return [x for x in p.replace('/', '\\').split('\\') if x not in ('', '.')]


def to83(name):
    name = name.upper()
    base, _, ext = name.partition('.')
    if not base or len(base) > 8 or len(ext) > 3 or '.' in ext:
        raise SystemExit('not an 8.3 name: %s' % name)
    return (base.ljust(8) + ext.ljust(3)).encode('ascii')


def from83(raw):
    raw = bytes(raw).decode('ascii', 'replace')
    base, ext = raw[:8].rstrip(), raw[8:].rstrip()
    return base + ('.' + ext if ext else '')


def main(argv):
    if len(argv) < 3:
        sys.exit(__doc__)
    fs = Fat12(argv[1])
    cmd, args = argv[2].lower(), argv[3:]
    if cmd == 'mkdir' and len(args) == 1:
        fs.resolve(args[0], create=True)
        fs.save()
    elif cmd == 'add' and len(args) >= 2:
        if args[0].startswith('--date='):
            fs.stamp = datetime.datetime.fromisoformat(args[0][7:])
            args = args[1:]
        clus = fs.resolve(args[0], create=True)
        for spec in args[1:]:
            host, _, name = spec.partition('=')
            with open(host, 'rb') as fh:
                data = fh.read()
            fs.add(clus, to83(name or os.path.basename(host)), data)
        fs.save()
    elif cmd == 'attr' and len(args) >= 2:
        parts = split_path(args[0])
        clus = fs.resolve('\\'.join(parts[:-1]))
        off = fs.find(clus, to83(parts[-1]))
        if off is None:
            sys.exit('no such entry: %s' % args[0])
        bits = {'r': 0x01, 'h': 0x02, 's': 0x04, 'a': 0x20}
        attr = fs.img[off + 11]
        for spec in args[1:]:
            on = not spec.startswith('-')
            for ch in spec.lstrip('+-').lower():
                attr = (attr | bits[ch]) if on else (attr & ~bits[ch])
        fs.img[off + 11] = attr
        fs.save()
    elif cmd == 'ls' and len(args) <= 1:
        clus = fs.resolve(args[0] if args else '')
        for off in fs.entries(clus):
            attr = fs.img[off + 11]
            (size,) = struct.unpack_from('<I', fs.img, off + 28)
            print('%-12s %s' % (from83(fs.img[off:off + 11]),
                                '<DIR>' if attr & ATTR_DIR else size))
    elif cmd == 'get' and len(args) in (1, 2):
        parts = split_path(args[0])
        if not parts:
            sys.exit('get needs a file name')
        clus = fs.resolve('\\'.join(parts[:-1]))
        off = fs.find(clus, to83(parts[-1]))
        if off is None or fs.img[off + 11] & ATTR_DIR:
            sys.exit('no such file: %s' % args[0])
        with open(args[1] if len(args) == 2 else parts[-1], 'wb') as fh:
            fh.write(fs.read(off))
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main(sys.argv)
