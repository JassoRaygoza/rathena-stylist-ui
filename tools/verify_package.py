"""Verify this release without changing a server, client, or database."""
from pathlib import Path
import hashlib
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def main():
    manifest = ROOT / 'SHA256SUMS.txt'
    count = 0
    listed = set()
    for line in manifest.read_text(encoding='utf-8').splitlines():
        expected, relative = line.split('  ', 1)
        if not re.fullmatch(r'[0-9a-f]{64}', expected) or relative in listed:
            raise ValueError('Invalid or duplicate checksum entry: ' + relative)
        path = (ROOT / relative).resolve()
        path.relative_to(ROOT)
        if not path.is_file() or digest(path) != expected:
            raise ValueError('Missing or changed file: ' + relative)
        listed.add(relative)
        count += 1
    metadata = json.loads((ROOT / 'diff/base.json').read_text(encoding='utf-8'))
    patch = (ROOT / 'diff/stylist_ui.diff').read_bytes()
    chunks = patch.split(b'diff --git ')[1:]
    mirrors = {}
    for chunk in chunks:
        lines = chunk.splitlines(keepends=True)
        if not any(line.startswith(b'new file mode ') for line in lines):
            continue
        header = next(line for line in lines if line.startswith(b'+++ b/'))
        relative = header[len(b'+++ b/'):].strip().decode('utf-8')
        mirrors[relative] = b''.join(line[1:] for line in lines if line.startswith(b'+') and not line.startswith(b'+++ '))
    for relative in metadata['new_files']:
        name = 'server/' + relative
        if name not in listed or mirrors.get(relative) != (ROOT / name).read_bytes():
            raise ValueError('New server file differs from patch: ' + relative)
    required = {'README.md', 'INSTALL.md', 'diff/stylist_ui.diff',
                'patcher/StylistUIPatcher.exe',
                'client/data/luafiles514/lua files/stylingshop/stylingshopinfo.lub'}
    if not required <= listed:
        raise ValueError('Manifest is missing a required release component')
    print(f'PASS: {count} release files verified; all {len(mirrors)} new server files match the diff.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, StopIteration) as error:
        print('Verification failed: ' + str(error), file=sys.stderr)
        raise SystemExit(1)