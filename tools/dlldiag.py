"""Diagnose why a native DLL fails to load (missing imports / missing exports).

    python tools\\dlldiag.py <path-to-dll>
"""

from __future__ import annotations

import os
import struct
import sys


class PE:
    def __init__(self, path: str) -> None:
        self.path = path
        with open(path, "rb") as handle:
            self.data = handle.read()
        data = self.data
        e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
        if data[e_lfanew:e_lfanew + 4] != b"PE\x00\x00":
            raise ValueError("not a PE file: %s" % path)
        coff = e_lfanew + 4
        nsec, = struct.unpack_from("<H", data, coff + 2)
        opt_size, = struct.unpack_from("<H", data, coff + 16)
        opt = coff + 20
        magic, = struct.unpack_from("<H", data, opt)
        self.pe32plus = magic == 0x20B
        self.dd_off = opt + (112 if self.pe32plus else 96)
        sec_off = opt + opt_size
        self.sections = []
        for index in range(nsec):
            base = sec_off + index * 40
            name = data[base:base + 8].rstrip(b"\x00").decode("ascii", "replace")
            vsize, vaddr, raw_size, raw_ptr = struct.unpack_from("<IIII", data, base + 8)
            self.sections.append((vaddr, vsize, raw_ptr, raw_size, name))

    def rva_to_off(self, rva: int):
        for vaddr, vsize, raw_ptr, raw_size, _name in self.sections:
            if vaddr <= rva < vaddr + max(vsize, raw_size):
                return raw_ptr + (rva - vaddr)
        return None

    def cstring(self, offset: int) -> str:
        end = self.data.index(b"\x00", offset)
        return self.data[offset:end].decode("ascii", "replace")

    @property
    def pointer_size(self) -> int:
        return 8 if self.pe32plus else 4

    def imports(self):
        imp_rva, _size = struct.unpack_from("<II", self.data, self.dd_off + 8)
        result = {}
        if imp_rva == 0:
            return result
        off = self.rva_to_off(imp_rva)
        while True:
            entry = self.data[off:off + 20]
            if len(entry) < 20 or entry == b"\x00" * 20:
                break
            oft, _time, _fwd, name_rva, first_thunk = struct.unpack_from("<IIIII", entry, 0)
            if name_rva == 0:
                break
            dll = self.cstring(self.rva_to_off(name_rva))
            names = []
            walker = self.rva_to_off(oft or first_thunk)
            if walker is not None:
                step = self.pointer_size
                ordinal_flag = 1 << (63 if self.pe32plus else 31)
                code = "<Q" if self.pe32plus else "<I"
                while True:
                    value, = struct.unpack_from(code, self.data, walker)
                    if value == 0:
                        break
                    if not value & ordinal_flag:
                        names.append(self.cstring(self.rva_to_off(value) + 2))
                    walker += step
            result[dll] = names
            off += 20
        return result

    def exports(self):
        exp_rva, _size = struct.unpack_from("<II", self.data, self.dd_off)
        if exp_rva == 0:
            return set()
        off = self.rva_to_off(exp_rva)
        (_flags, _time, _major, _minor, _name_rva, _base, _nfunc,
         nnames, _addr_func, addr_name, _addr_ord) = struct.unpack_from("<IIHHIIIIIII", self.data, off)
        names = set()
        name_off = self.rva_to_off(addr_name)
        for index in range(nnames):
            rva, = struct.unpack_from("<I", self.data, name_off + index * 4)
            names.add(self.cstring(self.rva_to_off(rva)))
        return names


def file_version(path: str) -> str:
    try:
        import ctypes
        size = ctypes.windll.version.GetFileVersionInfoSizeW(path, None)
        if not size:
            return ""
        buffer = ctypes.create_string_buffer(size)
        ctypes.windll.version.GetFileVersionInfoW(path, 0, size, buffer)
        value = ctypes.c_void_p()
        length = ctypes.c_uint()
        ctypes.windll.version.VerQueryValueW(buffer, "\\", ctypes.byref(value), ctypes.byref(length))
        fixed = ctypes.cast(value, ctypes.POINTER(ctypes.c_uint32 * 13)).contents
        ms, ls = fixed[2], fixed[3]
        return "v%d.%d.%d.%d" % (ms >> 16, ms & 0xFFFF, ls >> 16, ls & 0xFFFF)
    except Exception:
        return ""


def resolve(name: str, search_dirs):
    for directory in search_dirs:
        candidate = os.path.join(directory, name)
        if os.path.exists(candidate):
            return candidate
    for directory in (os.path.dirname(sys.executable),
                      os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")):
        candidate = os.path.join(directory, name)
        if os.path.exists(candidate):
            return candidate
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        if directory and os.path.exists(os.path.join(directory, name)):
            return os.path.join(directory, name)
    return None


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    target = os.path.abspath(sys.argv[1])
    pe = PE(target)
    search_dirs = [os.path.dirname(target)]
    print("target : %s (%s)" % (target, "PE32+" if pe.pe32plus else "PE32"))
    print("search : %s" % search_dirs)

    problems = 0
    for dll, names in pe.imports().items():
        path = resolve(dll, search_dirs)
        if path is None:
            print("  MISSING DLL      %-38s" % dll)
            problems += 1
            continue
        exported = PE(path).exports()
        missing = [name for name in names if name not in exported]
        marker = "  OK              " if not missing else "  MISSING EXPORT  "
        print("%s %-38s %-16s %s" % (marker, dll, file_version(path), path))
        if missing:
            problems += 1
            for name in missing[:15]:
                print("            -> %s" % name)
            if len(missing) > 15:
                print("            -> ... and %d more" % (len(missing) - 15))
    print("\n%d problem(s) found" % problems)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
