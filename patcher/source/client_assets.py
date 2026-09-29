"""Build the Stylist selector box textures and install client files into a GRF.

    python client_assets.py install CLIENT_DIR --lub stylingshopinfo.lub

Reads the native bg_styling_color.bmp from the client's GRFs, renders the two
selector boxes used by the patched client, and adds them (plus the optional
Stylist table) to the highest-priority GRF listed in DATA.INI. A timestamped
backup of that GRF is written first. Only GRF 0x300 (GRF Editor) is written.
"""
import argparse
from datetime import datetime
import hashlib
import io
from pathlib import Path
import shutil
import struct
import zlib

from PIL import Image

from generate_patch import HAIR_BOX_BMP, HAIR_BOX_SIZE, STYLE_BOX_BMP, STYLE_BOX_SIZE

TEXTURE = 'data\\texture\\'
NATIVE_BOX = '유저인터페이스\\styleshop\\bg_styling_color.bmp'
LUB = 'data\\luafiles514\\lua files\\stylingshop\\stylingshopinfo.lub'
FILE_FLAG = 1


def encode(name):
    return name.encode('cp949')


class Grf:
    """Read-only view of a GRF 0x200/0x300 file table."""

    def __init__(self, path):
        self.path = Path(path)
        with self.path.open('rb') as f:
            header = f.read(46)
            self.version = struct.unpack('<I', header[42:46])[0]
            if self.version == 0x300:
                self.offset, self.count = struct.unpack('<QI', header[30:42])
                entry, skip = struct.Struct('<IIIBQ'), 4
            elif self.version == 0x200:
                self.offset, seed, raw = struct.unpack('<III', header[30:42])
                self.count = raw - seed - 7
                entry, skip = struct.Struct('<IIIBI'), 0
            else:
                raise ValueError(f'{path}: unsupported GRF version 0x{self.version:x}')
            f.seek(self.offset + 46)
            self.prefix = f.read(skip)
            compressed, size = struct.unpack('<II', f.read(8))
            table = zlib.decompress(f.read(compressed))
        if len(table) != size:
            raise ValueError(f'{path}: truncated file table')
        self.entries, i = {}, 0
        while i < len(table):
            end = table.index(b'\0', i)
            self.entries[table[i:end]] = entry.unpack_from(table, end + 1)
            i = end + 1 + entry.size
        if len(self.entries) != self.count:
            raise ValueError(f'{path}: expected {self.count} entries, found {len(self.entries)}')

    def find(self, name):
        wanted = encode(name).lower()
        return next((k for k in self.entries if k.lower() == wanted), None)

    def read(self, key):
        compressed, aligned, size, flags, position = self.entries[key]
        if flags != FILE_FLAG:
            raise ValueError(f'{key!r}: encrypted or non-file entries are not supported')
        with self.path.open('rb') as f:
            f.seek(position + 46)
            data = zlib.decompress(f.read(aligned)[:compressed])
        if len(data) != size:
            raise ValueError(f'{key!r}: size mismatch')
        return data


def grf_order(client):
    """GRFs in DATA.INI priority order (index 0 wins)."""
    order = []
    for line in (Path(client) / 'DATA.INI').read_text(encoding='latin-1').splitlines():
        key, _, value = line.partition('=')
        if key.strip().isdigit() and value.strip():
            order.append((int(key), Path(client) / value.strip()))
    return [path for _, path in sorted(order)]


def native_box(client):
    for path in grf_order(client):
        grf = Grf(path)
        key = grf.find(TEXTURE + NATIVE_BOX)
        if key:
            return Image.open(io.BytesIO(grf.read(key))).convert('RGB')
    raise FileNotFoundError(NATIVE_BOX + ' was not found in any GRF listed in DATA.INI')


def render_boxes(native):
    """Stretch the native box: corners/edges kept, plain interior repeated."""
    w, h = native.size
    if (w, h) != (110, 42) or native.getpixel((0, 0)) != (255, 0, 255):
        raise ValueError('Unexpected native bg_styling_color.bmp layout')
    plain_x = 60     # column with border only (right of brush and divider)
    edge = 4         # rounded corner / border thickness

    def stretch(source, left, size):
        width, height = size
        out = Image.new('RGB', size)
        out.paste(source.crop((0, 0, left, source.height)), (0, 0))
        column = source.crop((plain_x, 0, plain_x + 1, source.height))
        for x in range(left, width - edge):
            out.paste(column, (x, 0))
        out.paste(source.crop((w - edge, 0, w, source.height)), (width - edge, 0))
        if height != source.height:
            rows = out
            out = Image.new('RGB', size)
            out.paste(rows.crop((0, 0, width, edge)), (0, 0))
            middle = rows.crop((0, h // 2, width, h // 2 + 1))
            for y in range(edge, height - edge):
                out.paste(middle, (0, y))
            out.paste(rows.crop((0, h - edge, width, h)), (0, height - edge))
        return out

    # Hair color keeps the brush and dotted divider; the selector box is plain.
    hair = stretch(native, 40, HAIR_BOX_SIZE)
    style = stretch(native, edge, STYLE_BOX_SIZE)
    return hair, style


def bmp(image):
    out = io.BytesIO()
    image.save(out, 'BMP')
    return out.getvalue()


def add_files(path, files):
    """Append files and a new table after the old one; the header is written last."""
    grf = Grf(path)
    if grf.version != 0x300:
        raise ValueError(f'{path}: only GRF 0x300 can be written')
    entries = dict(grf.entries)
    with Path(path).open('r+b') as f:
        f.seek(0, 2)
        position = f.tell() - 46
        for name, data in files.items():
            packed = zlib.compress(data, 9)
            aligned = (len(packed) + 7) // 8 * 8
            f.write(packed + bytes(aligned - len(packed)))
            key = grf.find(name) or encode(name)
            entries[key] = (len(packed), aligned, len(data), FILE_FLAG, position)
            position += aligned
        table = b''.join(k + b'\0' + struct.pack('<IIIBQ', *v) for k, v in entries.items())
        packed = zlib.compress(table, 9)
        f.write(grf.prefix + struct.pack('<II', len(packed), len(table)) + packed)
        f.flush()
        f.seek(30)
        f.write(struct.pack('<QI', position, len(entries)))
    check = Grf(path)
    for name, data in files.items():
        if check.read(check.find(name)) != data:
            raise ValueError(f'{path}: verification failed for {name}')
    for key, value in grf.entries.items():
        if key not in {check.find(n) for n in files} and check.entries[key] != value:
            raise ValueError(f'{path}: unrelated entry changed: {key!r}')


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def texture_resource(client):
    """STYTEX01 blob embedded in the patcher: count, then (name, data) pairs."""
    hair, style = render_boxes(native_box(client))
    out = bytearray(b'STYTEX01' + struct.pack('<I', 2))
    for name, image in ((TEXTURE + HAIR_BOX_BMP, hair), (TEXTURE + STYLE_BOX_BMP, style)):
        raw, data = encode(name), bmp(image)
        out += struct.pack('<I', len(raw)) + raw + struct.pack('<I', len(data)) + data
    return bytes(out)


def install(client, lub=None, preview=None):
    hair, style = render_boxes(native_box(client))
    files = {TEXTURE + HAIR_BOX_BMP: bmp(hair), TEXTURE + STYLE_BOX_BMP: bmp(style)}
    if lub:
        files[LUB] = Path(lub).read_bytes()
    if preview:
        Path(preview).mkdir(parents=True, exist_ok=True)
        hair.save(Path(preview) / 'hair_box.png')
        style.save(Path(preview) / 'style_box.png')
    target = grf_order(client)[0]
    backup = target.with_name(f'{target.name}.{datetime.now():%Y%m%d-%H%M%S}.pre-stylist.bak')
    shutil.copyfile(target, backup)
    if sha256(backup) != sha256(target):
        raise OSError('Backup verification failed; the GRF was not changed.')
    add_files(target, files)
    return target, backup, list(files)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    cmd = sub.add_parser('install')
    cmd.add_argument('client', type=Path, help='Client folder containing DATA.INI')
    cmd.add_argument('--lub', type=Path, help='stylingshopinfo.lub to install as well')
    cmd.add_argument('--preview', type=Path, help='Also save PNG previews of the boxes here')
    res = sub.add_parser('resource', help='Write the texture blob embedded by build.ps1')
    res.add_argument('client', type=Path, help='Client folder containing DATA.INI')
    res.add_argument('output', type=Path)
    args = parser.parse_args()
    if args.command == 'resource':
        args.output.write_bytes(texture_resource(args.client))
        print(f'Wrote {args.output}')
        return
    target, backup, names = install(args.client, args.lub, args.preview)
    print(f'Updated {target}\nBackup  {backup}')
    for name in names:
        print('  +', name)


if __name__ == '__main__':
    main()
