"""Execute patched x86 routines against simulated native UI/Lua services.

Set STYLIST_TEST_CLIENT to the exact supported client before running unittest.
These tests do not substitute for visual and purchase checks inside the game.
"""
import hashlib
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import types
import unittest

import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_EBP, UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EDI, UC_X86_REG_EIP, UC_X86_REG_ESI, UC_X86_REG_ESP

import client_assets
import generate_patch as patch
from test_client_assets import write_grf

SOURCE_PATH = os.environ.get("STYLIST_TEST_CLIENT")
PARENT, CHILD, PANEL, DEFAULT = 0x7001000, 0x7001200, 0x7001400, 0x7001600
VTABLE, POSITION, EVENT, REFRESH = 0x7002000, 0x7003000, 0x7003010, 0x7003020
STACK, STOP = 0x70F0000, 0x7003030
RESOURCES, TEXTURES = 0x7005000, 0x7006000


class Machine:
    def __init__(self, binary, colours=None, doram=False, colouring=True, missing=()):
        self.u = Uc(UC_ARCH_X86, UC_MODE_32)
        pe = pefile.PE(data=binary)
        mapped = pe.get_memory_mapped_image()
        self.u.mem_map(0x400000, (len(mapped)+4095)//4096*4096)
        self.u.mem_write(0x400000, mapped)
        self.u.mem_map(0x7000000, 0x100000)
        self.u.mem_map(0, 0x1000)
        self.heap = 0x7040000
        self.colours = colours if colours is not None else list(range(1, 678))
        self.tables = {"HeadPalette": self.colours, "HeadStyle": list(range(1, 51)),
                       "BodyPalette": list(range(1, 701)), "DoramHeadStyle": [1, 2, 4, 6],
                       "DoramBodyPalette": [1, 2, 3]}
        self.doram, self.colouring = doram, colouring
        self.textures, self.buttons, self.drawn, self.dialogs, self.queries = [], [], [], [], []
        self.default_cleared = False
        self.missing, self.loaded, self.bitmaps = set(missing), [], []
        # Current job and CostumeChange rows per original job (StylingShop_GetCostumeSize).
        self.job, self.costumes = None, {}
        self.name = b"Skorm v2"
        self.stops = {STOP}
        for obj in (PARENT, CHILD, PANEL, DEFAULT):
            self.put(obj, VTABLE)
        self.put(PARENT+0x7C, CHILD)
        self.put(PARENT+0x80, PANEL)
        self.put(PARENT+0x94, DEFAULT)
        self.put(CHILD+0x8C, 1)
        self.put(VTABLE+0x10, POSITION)
        self.put(VTABLE+0xB4, EVENT)
        self.put(VTABLE+0x98, REFRESH)
        self.put(patch.COUNT, len(self.colours))
        self.u.hook_add(UC_HOOK_CODE, self.hook)

    def put(self, address, value):
        self.u.mem_write(address, struct.pack("<I", value & 0xFFFFFFFF))

    def get(self, address):
        return struct.unpack("<I", self.u.mem_read(address, 4))[0]

    def cstring(self, address):
        result = bytearray()
        for i in range(256):
            value = bytes(self.u.mem_read(address+i, 1))
            if value == b"\0":
                return bytes(result)
            result.extend(value)
        raise AssertionError("Unterminated string")

    def arg(self, i):
        return self.get(self.u.reg_read(UC_X86_REG_ESP)+4+4*i)

    def ret(self, cleanup=0, value=0):
        sp = self.u.reg_read(UC_X86_REG_ESP)
        self.u.reg_write(UC_X86_REG_EIP, self.get(sp))
        self.u.reg_write(UC_X86_REG_ESP, sp+4+cleanup)
        self.u.reg_write(UC_X86_REG_EAX, value)

    def alloc(self):
        result = self.heap
        self.heap += 0x200
        return result

    def hook(self, uc, address, size, unused):
        if address in self.stops:
            uc.emu_stop()
            return
        ecx = uc.reg_read(UC_X86_REG_ECX)
        if address in (0xE624AE, 0x4FA050):
            self.ret(4 if address == 0x4FA050 else 0, self.alloc())
        elif address == 0x84EAB0:
            self.put(ecx, VTABLE)
            self.put(ecx+0xB4, 9)
            self.put(ecx+0xB8, 12)
            self.ret(value=ecx)
        elif address == 0x8657A0:
            self.textures.append(self.cstring(self.arg(0)))
            self.ret(12)
        elif address == 0xA7B470:
            self.ret(8)
        elif address == POSITION:
            self.put(ecx+0x1C, self.arg(0))
            self.put(ecx+0x20, self.arg(1))
            self.ret(8)
        elif address == EVENT:
            self.put(ecx+0x2C, self.arg(0))
            self.ret(4)
        elif address == 0xA7A080:
            self.buttons.append(self.arg(0))
            self.put(self.arg(0)+0x10, ecx)
            self.ret(4)
        elif address in (REFRESH, 0x829C30, 0x829D10):
            self.ret()
        elif address == 0x867BB0:
            self.default_cleared = ecx == DEFAULT and self.arg(0) == 0
            self.ret(4)
        elif address == 0xDDDFE0:
            self.ret(value=self.job if self.job is not None else 4218 if self.doram else 0)
        elif address == 0xE3CFF0:
            self.ret(4, int(self.doram))
        elif address == 0xB00F00:
            self.dialogs.append(self.arg(0))
            self.ret(value=0x7004000)
        elif address == 0xA901E0:
            self.ret(36)
        elif address == 0x8264A0:
            out, kind = self.arg(0), self.get(self.arg(1))
            name = {1: "HeadPalette", 2: "HeadStyle", 3: "BodyPalette"}[kind]
            if self.doram and kind != 1:
                name = "Doram"+name
            raw = name.encode()+b"\0"
            if len(name) < 16:
                uc.mem_write(out, raw)
                self.put(out+20, 15)
            else:
                buf = self.alloc()
                uc.mem_write(buf, raw)
                self.put(out, buf)
                self.put(out+20, 31)
            self.put(out+16, len(name))
            self.ret(8, out)
        elif address == 0xAF1620:
            self.ret(value=RESOURCES)
        elif address == 0xB01200:
            self.ret(value=self.arg(0))
        elif address == 0xAEE770:
            assert ecx == RESOURCES
            name = self.cstring(self.arg(0)).decode("cp949")
            self.loaded.append(name)
            self.ret(4, 0 if name in self.missing else TEXTURES+len(self.loaded))
        elif address == 0xA7BB60:
            assert self.arg(3) == 0
            self.bitmaps.append((ecx, self.arg(0), self.arg(1), self.loaded[self.arg(2)-TEXTURES-1]))
            self.ret(16)
        elif address == 0x4F98A0:
            self.ret()
        elif address == 0xAFC9A0:
            # Args: Lua*, std::string(24), format, table/value, value/out, out.
            sp = uc.reg_read(UC_X86_REG_ESP)
            name = self.cstring(self.get(sp+8)).decode()
            signature = self.cstring(self.arg(7)).decode()
            if signature == "d>b":
                assert name == "StylingShop_GetIsColoring_by_goods"
                uc.mem_write(self.arg(9), bytes([int(self.colouring)]))
            elif signature == "d>d":
                assert name == "StylingShop_GetCostumeSize"
                self.queries.append((name, self.arg(8)))
                self.put(self.arg(9), self.costumes.get(self.arg(8), 0))
            else:
                table = self.cstring(self.arg(8)).decode()
                items = self.tables[table]
                if signature == "s>d":
                    value, out = len(items), self.arg(9)
                else:
                    candidate, out = self.arg(9), self.arg(10)
                    if name == "StylingShop_GetSeqnumber_by_goods":
                        value = items.index(candidate)+1 if candidate in items else 0
                    elif name == "StylingShop_GetGoods":
                        value = items[candidate-1] if 1 <= candidate <= len(items) else 0
                    else:
                        raise AssertionError(name)
                self.queries.append((name, table))
                self.put(out, value)
            self.ret(value=1)
        elif address == 0xE08C70:
            assert ecx == 0x1732638
            buf = self.alloc()
            uc.mem_write(buf, self.name+b"\0")
            self.ret(value=buf)
        elif address == 0x602B00:
            fmt = self.cstring(self.arg(2)).decode()
            text = (fmt % tuple(self.arg(3+i) for i in range(fmt.count("%")))).encode()
            assert len(text) < self.arg(1)
            uc.mem_write(self.arg(0), text+b"\0")
            self.ret(value=len(text))
        elif address == 0xA84360:
            self.drawn.append((self.arg(0), self.arg(1), self.cstring(self.arg(2)).decode()))
            self.ret(36)

    def call(self, address, this=PARENT):
        self.u.reg_write(UC_X86_REG_ESP, STACK)
        self.u.reg_write(UC_X86_REG_ECX, this)
        self.put(STACK, STOP)
        self.u.emu_start(address, 0, count=20000)
        assert self.u.reg_read(UC_X86_REG_EIP) == STOP
        assert self.u.reg_read(UC_X86_REG_ESP) == STACK+4

    def event(self, event, current=1, source=0):
        frame = STACK+0x100
        self.u.reg_write(UC_X86_REG_EBP, frame)
        self.u.reg_write(UC_X86_REG_EDI, PARENT)
        self.u.reg_write(UC_X86_REG_ESP, STACK)
        self.put(frame+8, source)
        self.put(frame+0x10, event)
        self.put(CHILD+0x94, current)
        self.stops.add(0x82D384)
        self.u.emu_start(0x82D156, 0, count=20000)
        assert self.u.reg_read(UC_X86_REG_EIP) == 0x82D384
        assert self.u.reg_read(UC_X86_REG_ESP) == STACK
        return self.get(CHILD+0x94)


@unittest.skipUnless(SOURCE_PATH, "Set STYLIST_TEST_CLIENT to the supported EXE")
class PatcherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = Path(SOURCE_PATH).read_bytes()
        cls.output, cls.patches, _ = patch.build(cls.source)

    def test_source_guard(self):
        with self.assertRaises(ValueError):
            patch.build(self.source[:-1])
        with self.assertRaises(ValueError):
            patch.build(self.output)

    def test_only_declared_ranges_change(self):
        untouched = bytearray(self.output[:len(self.source)])
        for offset, old, new in self.patches:
            if old:
                untouched[offset:offset+len(old)] = old
        self.assertEqual(self.source, untouched)
        pe = pefile.PE(data=self.output)
        self.assertEqual(pe.sections[-1].Name.rstrip(b"\0"), b".stynum")
        original = pefile.PE(data=self.source)
        cm = next(s for s in original.sections if s.Name.rstrip(b"\0") == b".cmkeep")
        self.assertEqual(cm.get_data(), self.output[cm.PointerToRawData:cm.PointerToRawData+cm.SizeOfRawData])
        self.assertEqual(original.get_data(0x82D213-0x400000, 0xCC), pe.get_data(0x82D213-0x400000, 0xCC))

    def test_creates_two_arrows_without_colour_images(self):
        m = Machine(self.output)
        m.u.reg_write(UC_X86_REG_EBP, STACK+0x200)
        m.u.reg_write(UC_X86_REG_EDI, PARENT)
        m.u.reg_write(UC_X86_REG_ESP, STACK)
        m.put(STACK+0x200-0xF8, 677)
        m.stops.add(0x828738)
        m.u.emu_start(0x828556, 0, count=20000)
        self.assertEqual(m.u.reg_read(UC_X86_REG_EIP), 0x828738)
        self.assertEqual(m.u.reg_read(UC_X86_REG_ESP), STACK)
        self.assertEqual(len(m.buttons), 2)
        self.assertEqual([m.get(b+0x2C) for b in m.buttons], [patch.PREVIOUS, patch.NEXT])
        self.assertTrue(all(b"arrow_chr_" in t for t in m.textures))
        self.assertEqual(len(m.textures), 6)
        self.assertEqual(m.get(PARENT+0x88), 0)
        self.assertEqual(m.get(patch.COUNT), 677)
        # Aligned with the native hairstyle/clothing arrows, inside the wide box.
        self.assertEqual([(m.get(b+0x1C), m.get(b+0x20)) for b in m.buttons], [(108, 252), (231, 252)])
        left, _ = patch.HAIR_BOX_POS
        self.assertTrue(all(left < x and x+8 < left+patch.HAIR_BOX_SIZE[0] for x in patch.HAIR_ARROW_X))

    def test_hair_navigation_and_wrap(self):
        for current, event, expected in [(1, patch.NEXT, 2), (677, patch.NEXT, 1),
                                         (1, patch.PREVIOUS, 677), (0, patch.NEXT, 1),
                                         (0, patch.PREVIOUS, 677)]:
            with self.subTest(current=current, event=event):
                m = Machine(self.output)
                self.assertEqual(m.event(event, current), expected)
                self.assertTrue(m.default_cleared)

    def test_sparse_goods_use_catalogue_ids(self):
        m = Machine(self.output, colours=[1, 50, 677])
        self.assertEqual(m.event(patch.NEXT, 1), 50)
        m.call(patch.DRAW)
        self.assertEqual(m.drawn[-1][2], "Hair Color 2/3")

    def test_doram_denies_noncolourable_style(self):
        m = Machine(self.output, doram=True, colouring=False)
        self.assertEqual(m.event(patch.NEXT, 4), 4)
        self.assertEqual(m.dialogs, [0xB12])
        self.assertFalse(m.default_cleared)

    def test_doram_allows_colourable_style(self):
        m = Machine(self.output, doram=True, colouring=True)
        self.assertEqual(m.event(patch.NEXT, 4), 5)
        self.assertFalse(m.dialogs)

    def test_default_empty_and_unrelated_events(self):
        m = Machine(self.output)
        self.assertEqual(m.event(0x1EF, 677, DEFAULT), 0)
        self.assertEqual(m.event(0x1EF, 677, 0), 677)
        self.assertEqual(m.event(1234, 10), 10)
        m = Machine(self.output, colours=[])
        self.assertEqual(m.event(patch.NEXT, 0), 0)
        m.call(patch.DRAW)
        self.assertEqual(m.drawn[-1][2], "Hair Color 0/0")

    def test_three_captions_and_race_specific_counts(self):
        for doram in (False, True):
            with self.subTest(doram=doram):
                m = Machine(self.output, doram=doram)
                m.put(CHILD+0x8C, 4)
                m.put(CHILD+0x98, 2)
                m.put(CHILD+0x94, 677)
                m.call(patch.PREVIEW_DRAW, CHILD)
                m.call(patch.DRAW)
                texts = [text for x, y, text in m.drawn]
                self.assertEqual(texts, ["Hairstyle 3/4" if doram else "Hairstyle 4/50",
                                        "Clothing Color 2/3" if doram else "Clothing Color 2/700",
                                        "Hair Color 677/677"])
                self.assertEqual(m.drawn[-1][:2], (patch.HAIR_TEXT_X, 253))
                # Boxes are drawn before their captions: selector box on the preview, hair box on the panel.
                self.assertEqual(m.bitmaps, [(CHILD, 4, 24, patch.STYLE_BOX_BMP), (PARENT, 71, 233, patch.HAIR_BOX_BMP)])

    def test_selector_box_covers_both_rows(self):
        x, y = patch.STYLE_BOX_POS
        w, h = patch.STYLE_BOX_SIZE
        for arrow_x in (11, 231):          # native arrows, 8x12
            for arrow_y in (32, 54):
                self.assertTrue(x < arrow_x and arrow_x+8 < x+w and y < arrow_y and arrow_y+12 < y+h)
        self.assertLess(x+w, 249)          # native divider between preview and item list

    def test_dye_removal_sends_reset_index(self):
        # Hair color slot of the purchase packet, right after the Lua lookup.
        for looked_up, sent in [(0, 0xFFFFFFFF), (1, 1), (5, 5)]:
            with self.subTest(looked_up=looked_up):
                m = Machine(self.output)
                frame = STACK+0x1000
                m.u.reg_write(UC_X86_REG_EBP, frame)
                m.u.reg_write(UC_X86_REG_ESP, STACK)
                m.put(frame-0x8A8, looked_up)
                m.stops.add(0x8251CA)
                m.u.emu_start(0x8250B0, 0, count=100)
                self.assertEqual(m.u.reg_read(UC_X86_REG_EIP), 0x8251CA)
                self.assertEqual(m.u.reg_read(UC_X86_REG_ESP), STACK)
                self.assertEqual(m.get(frame-0x8A8), sent)

    def run_native(self, m, start, stops, esi=0):
        m.u.reg_write(UC_X86_REG_ESP, STACK)
        m.u.reg_write(UC_X86_REG_EBP, STACK+0x1000)
        for reg, value in ((UC_X86_REG_ESI, esi), (UC_X86_REG_EDI, 0x1234), (UC_X86_REG_EBX, 0x5678)):
            m.u.reg_write(reg, value)
        m.stops.update(stops)
        m.u.emu_start(start, 0, count=5000)
        self.assertEqual((m.u.reg_read(UC_X86_REG_ESI), m.u.reg_read(UC_X86_REG_EDI),
                          m.u.reg_read(UC_X86_REG_EBX)), (esi, 0x1234, 0x5678))
        return m.u.reg_read(UC_X86_REG_EIP)

    def test_costume_tab_enabled_for_jobs_with_table_rows(self):
        # Reached only when the native 3rd/4th job checks failed (e.g. Assassin Cross).
        for job, rows, enabled in [(4013, 3, True), (0, 0, False), (7, 0, False), (12, 2, True)]:
            with self.subTest(job=job):
                m = Machine(self.output)
                m.job, m.costumes = job, {job: rows}
                eip = self.run_native(m, 0x8296B9, {0x82970D, 0x8296BE})
                self.assertEqual(eip, 0x82970D if enabled else 0x8296BE)
                self.assertEqual(m.queries, [("StylingShop_GetCostumeSize", job)])
                if enabled:
                    self.assertEqual(m.u.reg_read(UC_X86_REG_ESP), STACK)
                else:   # the replaced "push 0x88" of the disabled path
                    self.assertEqual(m.u.reg_read(UC_X86_REG_ESP), STACK-4)
                    self.assertEqual(m.get(STACK-4), 0x88)

    def test_costume_tab_click_accepted_for_jobs_with_table_rows(self):
        blocked, accepted = 0x82DFF3, 0x82DEA7
        for job, rows, event, expected in [(4013, 3, patch.COSTUME_TAB_ID, accepted),
                                           (0, 0, patch.COSTUME_TAB_ID, blocked),
                                           (0, 0, 0x1F1, accepted)]:
            with self.subTest(job=job, event=event):
                m = Machine(self.output)
                m.job, m.costumes = job, {job: rows}
                self.assertEqual(self.run_native(m, 0x82DE9B, {blocked, accepted}, esi=event), expected)
                self.assertEqual(m.u.reg_read(UC_X86_REG_ESP), STACK)

    def test_favorites_are_keyed_by_name_and_job(self):
        for name, job, key in [(b"Skorm v2", 4013, b"Skorm v2@4013"),
                               (b"Skorm v2", 4071, b"Skorm v2@4071"),
                               (b"A" * 23, 4302, b"A" * 17 + b"@4302"),
                               (b"", 0, b"@0")]:
            with self.subTest(name=name, job=job):
                m = Machine(self.output)
                m.name, m.job = name, job
                m.u.reg_write(UC_X86_REG_ESI, 0x1111)
                m.u.reg_write(UC_X86_REG_EDI, 0x2222)
                m.u.reg_write(UC_X86_REG_EBX, 0x3333)
                m.call(patch.FAV_NAME, this=0x1732638)
                self.assertEqual(m.cstring(m.u.reg_read(UC_X86_REG_EAX)), key)
                # The file reader copies keys with strcpy_s(buffer, 24).
                self.assertLessEqual(len(key), 23)
                self.assertEqual((m.u.reg_read(UC_X86_REG_ESI), m.u.reg_read(UC_X86_REG_EDI),
                                  m.u.reg_read(UC_X86_REG_EBX)), (0x1111, 0x2222, 0x3333))

    def test_every_favorites_name_lookup_is_redirected(self):
        pe = pefile.PE(data=self.output, fast_load=True)
        for address in patch.FAV_NAME_CALLS:
            code = pe.get_data(address-0x400000, 5)
            self.assertEqual(code[0], 0xE8)
            self.assertEqual(address+5+struct.unpack("<i", code[1:])[0], patch.FAV_NAME)
        # No other stylist UI code (0x820000-0x832000) reads the name natively any more.
        start = pe.get_offset_from_rva(0x820000-0x400000)
        region = self.output[start:start+0x12000]
        native = [0x820000+i for i in range(len(region)-5) if region[i] == 0xE8 and
                  0x820000+i+5+struct.unpack_from("<i", region, i+1)[0] == 0xE08C70]
        self.assertEqual(native, [])

    def test_missing_box_textures_are_skipped(self):
        m = Machine(self.output, missing={patch.HAIR_BOX_BMP, patch.STYLE_BOX_BMP})
        m.call(patch.PREVIEW_DRAW, CHILD)
        m.call(patch.DRAW)
        self.assertEqual(m.bitmaps, [])
        self.assertEqual(len(m.drawn), 3)

    def test_hidden_preview_has_no_extra_labels(self):
        m = Machine(self.output)
        m.u.mem_write(CHILD+0xB0, b"\x01")
        m.call(patch.PREVIEW_DRAW, CHILD)
        self.assertEqual(m.drawn, [])
        self.assertEqual(m.bitmaps, [])

    def run_patcher(self, client):
        exe = Path(__file__).resolve().parent.parent / "StylistUIPatcher.exe"
        return subprocess.run([str(exe), str(client)], capture_output=True, text=True)

    @staticmethod
    def textures():
        """The (GRF name, BMP) pairs embedded in the patcher by build.ps1."""
        blob = (Path(__file__).parent / "generated" / "textures.bin").read_bytes()
        assert blob[:8] == b"STYTEX01"
        pos, result = 12, {}
        for _ in range(struct.unpack_from("<I", blob, 8)[0]):
            size = struct.unpack_from("<I", blob, pos)[0]; name = blob[pos+4:pos+4+size]; pos += 4+size
            size = struct.unpack_from("<I", blob, pos)[0]; result[name.decode("cp949")] = blob[pos+4:pos+4+size]; pos += 4+size
        return result

    def patch_copy(self, data, textures_installed=False, data_ini=True):
        """Patch a temporary client folder (EXE + DATA.INI + synthetic GRF 0x300)."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            client = root / "client.exe"
            client.write_bytes(data)
            if data_ini:
                (root / "DATA.INI").write_text("[Data]\n0=new.grf\n1=data.grf\n")
            write_grf(root / "new.grf", {"data\\keep.txt": b"keep"})
            if textures_installed:
                client_assets.add_files(root / "new.grf", self.textures())
            grf_before = (root / "new.grf").read_bytes()
            result = self.run_patcher(client)
            grf = client_assets.Grf(root / "new.grf")
            run = types.SimpleNamespace(
                result=result, exe=client.read_bytes(), grf_before=grf_before,
                grf=(root / "new.grf").read_bytes(),
                textures={n: grf.read(grf.find(n)) for n in self.textures() if grf.find(n)},
                keep=grf.read(grf.find("data\\keep.txt")),
                backups=[p.read_bytes() for p in root.glob("client.exe.*.pre-stylist.bak")],
                grf_backups=[p.read_bytes() for p in root.glob("new.grf.*.pre-stylist.bak")])
            self.assertFalse(any(p.name.endswith(".tmp") for p in root.iterdir()))
            return run

    def legacy(self):
        """An earlier Stylist patch: same sites except Dye Removal, older payload."""
        data = bytearray(self.output)
        offset = self.site(0x8250B0)
        old = next(o for off, o, n in self.patches if off == offset)
        data[offset:offset+len(old)] = old
        base = len(data) - 4096
        data[base:base+64] = bytes(range(64))
        return bytes(data)

    def site(self, address):
        return pefile.PE(data=self.source, fast_load=True).get_offset_from_rva(address-0x400000)

    def assert_installed(self, run):
        self.assertEqual(run.result.returncode, 0, run.result.stderr)
        self.assertEqual(run.textures, self.textures())
        self.assertEqual(run.keep, b"keep")

    def test_compiled_patcher_patches_original_and_installs_textures(self):
        run = self.patch_copy(self.source)
        self.assert_installed(run)
        self.assertEqual(run.exe, self.output)
        self.assertEqual(run.backups, [self.source])
        self.assertEqual(run.grf_backups, [run.grf_before])
        self.assertEqual(hashlib.sha256(Path(SOURCE_PATH).read_bytes()).hexdigest(), patch.SOURCE_SHA256)

    def test_compiled_patcher_upgrades_earlier_stylist_patch(self):
        old = self.legacy()
        self.assertNotEqual(old, self.output)
        run = self.patch_copy(old)
        self.assert_installed(run)
        self.assertEqual(run.exe, self.output)
        self.assertEqual(run.backups, [old])

    def test_compiled_patcher_installs_missing_textures_only(self):
        # The situation in error.png: current EXE, textures absent from the GRF.
        run = self.patch_copy(self.output)
        self.assert_installed(run)
        self.assertEqual(run.exe, self.output)
        self.assertEqual(run.backups, [])
        self.assertEqual(len(run.grf_backups), 1)

    def test_compiled_patcher_leaves_current_client_alone(self):
        run = self.patch_copy(self.output, textures_installed=True)
        self.assert_installed(run)
        self.assertIn("already has the current", run.result.stdout)
        self.assertEqual(run.exe, self.output)
        self.assertEqual(run.grf, run.grf_before)
        self.assertEqual((run.backups, run.grf_backups), ([], []))

    def test_compiled_patcher_keeps_unrelated_changes(self):
        # A byte outside every patch site (e.g. another tool's patch) survives.
        other = self.site(0x401000)
        self.assertFalse(any(o <= other < o+len(n) for o, _, n in self.patches))
        for data in (self.source, self.legacy()):
            changed = bytearray(data)
            changed[other] ^= 0xFF
            run = self.patch_copy(bytes(changed))
            self.assert_installed(run)
            expected = bytearray(self.output)
            expected[other] ^= 0xFF
            self.assertEqual(run.exe, bytes(expected))

    def test_compiled_patcher_refuses_without_changing_anything(self):
        wrong_site = bytearray(self.source)
        wrong_site[self.site(0x82D156)] ^= 0xFF
        cases = [(bytes(wrong_site), True), (self.source[:-1], True), (self.source + bytes(16), True),
                 (self.output[:-1], True), (self.source, False)]
        for data, data_ini in cases:
            run = self.patch_copy(data, data_ini=data_ini)
            self.assertNotEqual(run.result.returncode, 0)
            self.assertIn("No file was changed", run.result.stderr)
            self.assertEqual(run.exe, data)
            self.assertEqual(run.grf, run.grf_before)
            self.assertEqual((run.backups, run.grf_backups), ([], []))

    def test_compiled_patcher_refuses_while_grf_is_in_use(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "client.exe").write_bytes(self.source)
            (root / "DATA.INI").write_text("[Data]\n0=new.grf\n")
            write_grf(root / "new.grf", {"data\\keep.txt": b"keep"})
            before = (root / "new.grf").read_bytes()
            # The running client keeps its GRFs open without write sharing.
            import ctypes
            handle = ctypes.windll.kernel32.CreateFileW(str(root / "new.grf"), 0x80000000, 1, None, 3, 0, None)
            try:
                result = self.run_patcher(root / "client.exe")
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Close the game client", result.stderr)
            self.assertEqual((root / "client.exe").read_bytes(), self.source)
            self.assertEqual((root / "new.grf").read_bytes(), before)
            self.assertEqual(sorted(p.name for p in root.iterdir()), ["DATA.INI", "client.exe", "new.grf"])



if __name__ == "__main__":
    unittest.main()
