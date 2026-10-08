"""Read-mostly access to NASCAR 26's Unreal objects in the running game (UE 5.7.4, data only, no code changes).

Offsets for the 2026-10-07 update: GUObjectArray RVA 0xA0F6710 (FUObjectItem 0x18, UObject* at +8),
FNamePool blocks RVA 0xA0286D0 (both +0x1000 from the launch build). Each is sanity-checked before use, so a
game update fails safely instead of writing anywhere else.
"""
import ctypes, ctypes.wintypes as wt, struct, subprocess, sys

GUOBJECTARRAY_RVA = 0xA0F6710
FNAME_BLOCKS_RVA = 0xA0286D0    # FNameEntryAllocator::Blocks; CurrentBlock/CurrentByteCursor sit 8 bytes before
CHUNK_ITEMS = 64 * 1024
OBJ_CLASS, OBJ_NAME, OBJ_OUTER = 0x10, 0x18, 0x20
GAME_EXE = "NASCAR26_Steam-Win64-Shipping"

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.OpenProcess.restype = wt.HANDLE
k32.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k32.WriteProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k32.CloseHandle.argtypes = [wt.HANDLE]


class GameNotReady(Exception):
    pass


def find_game():
    """(pid, module base) of the running game window, or None."""
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
                          f"Get-Process {GAME_EXE} -ErrorAction SilentlyContinue | ? MainWindowTitle | "
                          "% { \"$($_.Id) $([int64]$_.MainModule.BaseAddress)\" }"],
                         capture_output=True, text=True, creationflags=0x08000000).stdout.split()
    return (int(out[0]), int(out[1])) if len(out) >= 2 else None


def plausible(p):
    return 0x10000 < p < 0x7FFFFFFFFFFF and p % 8 == 0


class Game:
    def __init__(self, pid, base, write=False):
        self.pid, self.base = pid, base
        access = 0x0010 | 0x0400 | ((0x0020 | 0x0008) if write else 0)
        self.h = k32.OpenProcess(access, False, pid)
        if not self.h:
            raise GameNotReady(f"OpenProcess failed ({ctypes.get_last_error()})")
        self._name_blocks = {}
        self._names = {}

    def close(self):
        k32.CloseHandle(self.h)

    # --- raw memory ---
    def read(self, addr, n):
        buf = ctypes.create_string_buffer(n)
        got = ctypes.c_size_t()
        if not k32.ReadProcessMemory(self.h, ctypes.c_void_p(addr), buf, n, ctypes.byref(got)) or got.value != n:
            return None
        return buf.raw

    def ptr(self, addr):
        b = self.read(addr, 8)
        return struct.unpack("<Q", b)[0] if b else 0

    def i32(self, addr):
        b = self.read(addr, 4)
        return struct.unpack("<i", b)[0] if b else None

    def write(self, addr, data):
        n = ctypes.c_size_t()
        if not k32.WriteProcessMemory(self.h, ctypes.c_void_p(addr), data, len(data), ctypes.byref(n)) or n.value != len(data):
            raise RuntimeError(f"WriteProcessMemory failed at {addr:#x} ({ctypes.get_last_error()})")
        if self.read(addr, len(data)) != data:
            raise RuntimeError(f"write verify failed at {addr:#x}")

    # --- names ---
    def name(self, comparison_index, number=0):
        key = (comparison_index, number)
        if key in self._names:
            return self._names[key]
        block, offset = comparison_index >> 16, (comparison_index & 0xFFFF) * 2
        if block not in self._name_blocks:
            bp = self.ptr(self.base + FNAME_BLOCKS_RVA + block * 8)
            self._name_blocks[block] = self.read(bp, 0x40000) if plausible(bp) else None
        blob = self._name_blocks[block]
        if not blob or offset + 2 > len(blob):
            return None
        header = struct.unpack_from("<H", blob, offset)[0]
        length, wide = header >> 6, header & 1
        raw = blob[offset + 2: offset + 2 + length * (2 if wide else 1)]
        s = raw.decode("utf-16-le" if wide else "latin-1", "replace")
        if number:
            s = f"{s}_{number - 1}"
        self._names[key] = s
        return s

    def obj_name(self, obj):
        b = self.read(obj + OBJ_NAME, 8)
        return self.name(*struct.unpack("<ii", b)) if b else None

    def class_name(self, obj):
        return self.obj_name(self.ptr(obj + OBJ_CLASS))

    # --- objects ---
    def objects(self):
        b = self.read(self.base + GUOBJECTARRAY_RVA + 0x10, 0x20)
        if not b:
            raise GameNotReady("object array unreadable")
        chunks, _, maxel, numel, maxch, numch = struct.unpack("<QQiiii", b)
        if not (plausible(chunks) and 0 < numel <= maxel and 0 < numch <= maxch):
            raise GameNotReady("object array not initialised (or game version changed)")
        for c in range(numch):
            cp = self.ptr(chunks + c * 8)
            n = min(CHUNK_ITEMS, numel - c * CHUNK_ITEMS)
            blob = self.read(cp, n * 0x18) if plausible(cp) else None
            if not blob:
                continue
            for i in range(n):
                o = struct.unpack_from("<Q", blob, i * 0x18 + 8)[0]
                if plausible(o):
                    yield o

    def find_by_class(self, class_names):
        """{class name: {object name: object}} for the requested classes."""
        want = set(class_names)
        class_ptr_name = {}
        found = {c: {} for c in want}
        for o in self.objects():
            cp = self.ptr(o + OBJ_CLASS)
            if cp not in class_ptr_name:
                class_ptr_name[cp] = self.obj_name(cp)
            cn = class_ptr_name[cp]
            if cn in want:
                found[cn][self.obj_name(o)] = o
        return found

    def sanity_check_names(self):
        blk0 = self.ptr(self.base + FNAME_BLOCKS_RVA)
        head = self.read(blk0, 6) if plausible(blk0) else None
        if not head or head[2:6] != b"None":
            raise GameNotReady("name table not found (game version changed?)")
