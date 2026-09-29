"""Build matching Stylist client/server files from three independent appearance limits.

Run without arguments for the wizard, or use --from-conf conf/battle/client.conf.
Only the Python standard library is required. Existing server files are never modified.
"""
import argparse
from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sys
import uuid

from generate_catalogue import ROOT, SOURCE, generate, PACKAGE

# An appearance and its purchase index must fit signed 16-bit storage. Clothing
# has a regular default-color row in addition to the free -1 reset sentinel.
MAX_COUNT = 32766
KEYS = ('max_cloth_color', 'max_hair_color', 'max_hair_style')
CLIENT_PATH = 'data/luafiles514/lua files/stylingshop/stylingshopinfo.lub'
CALL = re.compile(r'^StylingShop\.(Add\w+)\((\d+),.*\)$')


@dataclass(frozen=True)
class Settings:
    max_cloth_color: int
    max_hair_color: int
    max_hair_style: int
    include_doram: bool = False
    new_entry_price: int = 100000

    def validate(self):
        for key in KEYS:
            value = getattr(self, key)
            minimum = 1 if key == 'max_hair_style' else 0
            if type(value) is not int or not minimum <= value <= MAX_COUNT:
                raise ValueError(f'{key} must be an integer from {minimum} to {MAX_COUNT}.')
        if type(self.include_doram) is not bool:
            raise ValueError('include_doram must be true or false.')
        if type(self.new_entry_price) is not int or not 0 <= self.new_entry_price <= 2147483647:
            raise ValueError('new_entry_price must be an integer from 0 to 2147483647.')


def read_conf(path, stack=()):
    """Read the three rAthena max_* settings, honoring ordered imports/overrides.

    Import paths are relative to the repository (as in rAthena); a sibling file
    is also supported for standalone profiles. Cycles and missing files fail.
    """
    path = Path(path).resolve()
    if path in stack:
        raise ValueError(f'Configuration import cycle: {path}')
    values = {}
    for number, raw in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), 1):
        line = raw.split('//', 1)[0].strip()
        if not line or line.startswith('#') or ':' not in line:
            continue
        key, value = (part.strip() for part in line.split(':', 1))
        if key == 'import':
            imported = Path(value)
            if not imported.is_absolute():
                imported = ROOT / value if (ROOT / value).is_file() else path.parent / value
            values.update(read_conf(imported, (*stack, path)))
        elif key in KEYS:
            if not re.fullmatch(r'\d+', value):
                raise ValueError(f'{path}:{number}: {key} must be a nonnegative integer.')
            values[key] = int(value)
        elif key in ('min_cloth_color', 'min_hair_color', 'min_hair_style'):
            if value != '0':
                raise ValueError(f'{path}:{number}: this generator requires {key}: 0 for default/reset support.')
    return values


def configured_source(settings, source_path=None):
    settings.validate()
    source = Path(source_path or SOURCE).read_text(encoding='utf-8-sig')
    originals = {}
    for line in source.splitlines():
        match = CALL.fullmatch(line.strip())
        if match:
            originals.setdefault(match[1], {})[int(match[2])] = line

    def entries(fn, ids):
        old = originals.get(fn, {})
        result = []
        for value in ids:
            if value in old:
                result.append(old[value])
            else:
                flags = ''
                if fn == 'AddHeadPalette':
                    flags = ', ' + str(settings.include_doram).lower()
                elif fn == 'AddDoramHeadStyle':
                    flags = ', true'
                result.append(f'StylingShop.{fn}({value}, {{ zeny = {settings.new_entry_price} }}{flags})')
        return result

    # Keep official clothing indices first (0,2,3,...7); append missing colors
    # afterwards, including ID 1. This retains the Doram prefix and ticket costs.
    old_clothes = originals.get('AddBodyPalette', {})
    cloth_ids = [value for value in old_clothes if value <= settings.max_cloth_color]
    cloth_ids += [value for value in range(settings.max_cloth_color + 1) if value not in old_clothes]
    hair_ids = range(1, settings.max_hair_style + 1)
    palette_ids = range(1, settings.max_hair_color + 1)
    doram_hair = hair_ids if settings.include_doram else [i for i in originals.get('AddDoramHeadStyle', {}) if i <= settings.max_hair_style]
    doram_cloth = cloth_ids if settings.include_doram else [i for i in originals.get('AddDoramBodyPalette', {}) if i <= settings.max_cloth_color]
    replacements = {
        'AddHeadPalette': entries('AddHeadPalette', palette_ids),
        'AddHeadStyle': entries('AddHeadStyle', hair_ids),
        'AddBodyPalette': entries('AddBodyPalette', cloth_ids),
        'AddDoramHeadStyle': entries('AddDoramHeadStyle', doram_hair),
        'AddDoramBodyPalette': entries('AddDoramBodyPalette', doram_cloth),
    }
    emitted, result = set(), []
    for line in source.splitlines():
        match = CALL.fullmatch(line.strip())
        fn = match[1] if match else None
        if fn in replacements:
            if fn not in emitted:
                result.extend(replacements[fn])
                emitted.add(fn)
        else:
            result.append(line)
    return '\n'.join(result) + '\n'


def build_files(settings, source_path=None):
    required = ('src/common/mmo.hpp', 'src/map/stylist.hpp', 'db/re')
    if not all((ROOT / name).exists() for name in required):
        raise ValueError('Set STYLIST_SERVER_ROOT to a patched rAthena source tree containing src and db.')
    source = configured_source(settings, source_path)
    yml, standard, summary, lineage = generate(source)
    config = ('// Generated Stylist appearance limits. Import after other battle settings.\n'
              '// Counts are maximum IDs; color 0 is the default, outside the requested count.\n'
              'min_hair_style: 0\nmin_hair_color: 0\nmin_cloth_color: 0\n'
              + ''.join(f'{key}: {getattr(settings, key)}\n' for key in KEYS)
              + f'pet_hair_style: {max(100, settings.max_hair_style + 1)}\n')
    files = {
        'db/re/stylist_modern.yml': yml,
        'client/Files/' + CLIENT_PATH: standard,
        'client/LineageFiles/' + CLIENT_PATH: lineage,
        'conf/battle/stylist_generated.conf': config,
        'source/stylingshopinfo.lub': source,
        'settings.json': json.dumps(asdict(settings), indent=2) + '\n',
        'catalogue.json': json.dumps(summary, indent=2) + '\n',
        'INSTALL.md': f'''# Generated Stylist catalogue

Clothing colors: **{settings.max_cloth_color}** (IDs 1 through {settings.max_cloth_color}).
Hair colors: **{settings.max_hair_color}** (IDs 1 through {settings.max_hair_color}).
Hairstyles: **{settings.max_hair_style}** (IDs 1 through {settings.max_hair_style}).
Color 0 is the default and does not count toward either color quantity.
Extend Doram resources: **{settings.include_doram}**.

1. Back up your installed Stylist table, server catalogue, and battle settings.
2. Copy `db/re/stylist_modern.yml` into the same path in your server. Replace the
   complete file: merging into `db/import` would leave stale options when shrinking.
   Check `db/import/stylist_modern.yml` for overrides of generated entries.
3. Copy `conf/battle/stylist_generated.conf` into your server. Add
   `import: conf/battle/stylist_generated.conf` at the end of
   `conf/import/battle_conf.txt`. Later overrides must not lower these limits.
4. Choose ONE client table: `client/LineageFiles` for `stylist_class_lineage: on`,
   or `client/Files` for `stylist_class_lineage: off`. Copy its `data` folder into
   your client GRF at `{CLIENT_PATH}`. Do not install both variants.
5. Restart the map server and client together. This requires the modern Stylist
   server integration; deploy the compiled lineage update first if needed.
6. Verify the highest color and hairstyle IDs, purchases, and reconnect persistence
   for every supported sex, class and species in your actual client.

Existing entries retain their ticket/zeny prices. Newly added entries cost
{settings.new_entry_price} zeny. Returning to default color uses the free reset
selection. Clothing keeps its original indices first, then appends missing IDs.
The default generated package extends human options and retains available Doram
options within the selected limits. `--include-doram` extends Doram too; existing
non-colorable Doram hairstyles retain their restriction.

This package registers resources you already have. It does not create sprite,
ACT, or PAL assets, change hardcoded client limits, or translate the native UI.
Install compatible resources for every enabled ID. The integer bounds protect
server storage and purchase indices; actual client support must be verified.

To reproduce this package, run `tools\\StylistTools.exe --from-conf
<package>/conf/battle/stylist_generated.conf` (or the same options with
`python tools/catalogue/configure_catalogue.py`) with the same `--include-doram`
and `--new-entry-price` choices recorded in `settings.json`.
Use `--source <package>/source/stylingshopinfo.lub` when reproducing edited source tables.
`manifest.json` contains SHA-256 hashes of every other file.
''',
    }
    add_manifest(files)
    return files


def add_manifest(files):
    files['manifest.json'] = json.dumps({
        name: hashlib.sha256(value.encode('utf-8')).hexdigest()
        for name, value in files.items() if name != 'manifest.json'}, indent=2) + '\n'


def write_package(settings, output, source_path=None):
    files = build_files(settings, source_path)
    output = Path(output).resolve()
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError(f'Output must be a new or empty directory: {output}')
    output.mkdir(parents=True, exist_ok=True)
    for name, value in files.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(value, encoding='utf-8', newline='\n')
    return output


def ask_count(label, key, default):
    minimum = 1 if key == 'max_hair_style' else 0
    while True:
        answer = input(f'{label} ({key}, {minimum}-{MAX_COUNT}) [{default}]: ').strip()
        if not answer:
            return default
        if answer.isdecimal() and minimum <= int(answer) <= MAX_COUNT:
            return int(answer)
        print(f'Enter a whole number from {minimum} to {MAX_COUNT}.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--from-conf', type=Path, help='Read rAthena max_cloth_color, max_hair_color and max_hair_style (including imports)')
    parser.add_argument('--cloth-colors', type=int, help='Clothing color count (IDs 1..N; default color 0 is extra)')
    parser.add_argument('--hair-colors', type=int, help='Hair color count (IDs 1..N; default color 0 is extra)')
    parser.add_argument('--hairstyles', type=int, help='Hairstyle count (IDs 1..N)')
    parser.add_argument('--include-doram', action='store_true', help='Also extend Doram options using installed Doram assets')
    parser.add_argument('--new-entry-price', type=int, default=100000, help='Zeny price for new entries; existing prices are retained')
    parser.add_argument('--source', type=Path, help='Custom source StylingShop Lua table; defaults to the credited table shipped with this package')
    parser.add_argument('--output', type=Path, help='New or empty output directory')
    args = parser.parse_args(argv)
    try:
        values = read_conf(args.from_conf) if args.from_conf else {}
        overrides = dict(zip(KEYS, (args.cloth_colors, args.hair_colors, args.hairstyles)))
        values.update({key: value for key, value in overrides.items() if value is not None})
        interactive = not args.from_conf and all(value is None for value in overrides.values())
        if interactive:
            defaults = read_conf(PACKAGE / 'server/conf/battle/stylist.conf')
            print('Stylist Catalogue Builder\nSet clothing colors, hair colors, and hairstyles independently.')
            print('Colors use IDs 1..N plus default color 0. Install the matching client assets.')
            labels = ('How many clothing colors?', 'How many hair colors?', 'How many hairstyles?')
            values = {key: ask_count(label, key, defaults[key]) for key, label in zip(KEYS, labels)}
        missing = [key for key in KEYS if key not in values]
        if missing:
            raise ValueError('Missing settings: ' + ', '.join(missing) + '. Supply all three counts or use --from-conf.')
        settings = Settings(**values, include_doram=args.include_doram, new_entry_price=args.new_entry_price)
        output = args.output or PACKAGE / 'generated' / (datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6])
        output = write_package(settings, output, args.source)
        print(f'Generated matching client tables, server catalogue, and battle limits in:\n{output}')
        print(f'Installation instructions: {output / "INSTALL.md"}')
        return 0
    except (ValueError, OSError, EOFError, KeyboardInterrupt) as error:
        print(f'Generation failed: {error or "input cancelled"}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
