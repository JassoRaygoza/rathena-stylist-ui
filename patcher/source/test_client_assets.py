"""GRF 0x300 writer and selector box rendering, on synthetic files only."""
import io
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from PIL import Image

import client_assets as assets
import generate_patch as patch

MAGENTA, BORDER, WHITE = (255, 0, 255), (231, 231, 239), (255, 255, 255)


def write_grf(path, files):
    body, table, position = bytearray(), bytearray(), 0
    for name, data in files.items():
        packed = zlib.compress(data)
        aligned = (len(packed) + 7) // 8 * 8
        body += packed + bytes(aligned - len(packed))
        table += name.encode('cp949') + b'\0' + struct.pack('<IIIBQ', len(packed), aligned, len(data), 1, position)
        position += aligned
    packed = zlib.compress(bytes(table))
    header = b'Event Horizon\0RL' + bytes(range(1, 15)) + struct.pack('<QII', position, len(files), 0x300)
    Path(path).write_bytes(header + body + bytes(4) + struct.pack('<II', len(packed), len(table)) + packed)


def native_box():
    """Same layout as the client's 110x42 bg_styling_color.bmp."""
    image = Image.new('RGB', (110, 42), WHITE)
    for x in range(110):
        image.putpixel((x, 0), BORDER)
        image.putpixel((x, 41), BORDER)
    for y in range(42):
        image.putpixel((0, y), BORDER)
        image.putpixel((109, y), BORDER)
    for x, y in ((0, 0), (1, 0), (0, 1), (108, 0), (109, 0), (109, 1),
                 (0, 40), (0, 41), (1, 41), (109, 40), (108, 41), (109, 41)):
        image.putpixel((x, y), MAGENTA)
    for y in range(4, 38, 2):
        image.putpixel((30, y), BORDER)               # dotted divider
    for x, y in ((6, 6), (10, 8)):
        image.putpixel((x, y), (160, 180, 220))       # brush
    return image


class ClientAssetTests(unittest.TestCase):
    def test_boxes_keep_native_frame(self):
        hair, style = assets.render_boxes(native_box())
        self.assertEqual(hair.size, patch.HAIR_BOX_SIZE)
        self.assertEqual(style.size, patch.STYLE_BOX_SIZE)
        for image in (hair, style):
            w, h = image.size
            for corner in ((0, 0), (w-1, 0), (0, h-1), (w-1, h-1)):
                self.assertEqual(image.getpixel(corner), MAGENTA)
            self.assertEqual(image.getpixel((w//2, 0)), BORDER)
            self.assertEqual(image.getpixel((w//2, h-1)), BORDER)
            self.assertEqual(image.getpixel((w-1, h//2)), BORDER)
            self.assertEqual(image.getpixel((w-10, h//2)), WHITE)
        self.assertEqual(hair.getpixel((6, 6)), (160, 180, 220))
        self.assertEqual(hair.getpixel((30, 20)), BORDER)
        # The plain selector box has no brush or divider.
        self.assertEqual({style.getpixel((x, y)) for x in range(4, 238) for y in range(4, 46)}, {WHITE})

    def test_add_files_replaces_and_appends(self):
        lub = assets.LUB
        with tempfile.TemporaryDirectory() as temp:
            grf = Path(temp) / 'new.grf'
            write_grf(grf, {lub: b'old table', 'data\\other.txt': b'keep me'})
            before = assets.Grf(grf)
            new = {lub: b'new table' * 100, assets.TEXTURE + patch.HAIR_BOX_BMP: b'BM' + bytes(50)}
            assets.add_files(grf, new)
            after = assets.Grf(grf)
            self.assertEqual(after.count, 3)
            for name, data in new.items():
                self.assertEqual(after.read(after.find(name)), data)
            other = after.find('data\\other.txt')
            self.assertEqual(after.entries[other], before.entries[other])
            self.assertEqual(after.read(other), b'keep me')

    def test_install_backs_up_highest_priority_grf(self):
        with tempfile.TemporaryDirectory() as temp:
            client = Path(temp)
            (client / 'DATA.INI').write_text('[Data]\n0=new.grf\n1=data.grf\n')
            write_grf(client / 'new.grf', {'data\\x.txt': b'x'})
            out = io.BytesIO()
            native_box().save(out, 'BMP')
            write_grf(client / 'data.grf', {assets.TEXTURE + assets.NATIVE_BOX: out.getvalue()})
            original = (client / 'new.grf').read_bytes()
            data_grf = (client / 'data.grf').read_bytes()
            (client / 'table.lub').write_bytes(b'-- lub')
            target, backup, names = assets.install(client, client / 'table.lub')
            self.assertEqual(target, client / 'new.grf')
            self.assertEqual(backup.read_bytes(), original)
            self.assertEqual((client / 'data.grf').read_bytes(), data_grf)
            grf = assets.Grf(target)
            self.assertEqual(grf.read(grf.find(assets.LUB)), b'-- lub')
            box = Image.open(io.BytesIO(grf.read(grf.find(assets.TEXTURE + patch.STYLE_BOX_BMP))))
            self.assertEqual(box.size, patch.STYLE_BOX_SIZE)


if __name__ == '__main__':
    unittest.main()
