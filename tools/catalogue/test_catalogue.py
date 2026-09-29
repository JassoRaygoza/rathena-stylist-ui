"""Verify custom catalogue files agree with client indices, prices and battle limits."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

from configure_catalogue import CLIENT_PATH, MAX_COUNT, Settings, build_files, read_conf, write_package
from generate_catalogue import ROOT, generate


def rows(text, look):
    section = text.split(f'  - Look: {look}\n', 1)[1].split('  - Look:', 1)[0]
    result = {}
    for entry in section.split('      - Index: ')[1:]:
        index = int(entry.splitlines()[0])
        value = re.search(r'^        Value: (\d+)$', entry, re.M)
        result[index] = (int(value[1]), entry)
    return result


class ConfiguredCatalogueTests(unittest.TestCase):
    def test_700_colors_and_50_styles_match_both_client_tables_and_limits(self):
        files = build_files(Settings(700, 700, 50))
        yml = files['db/re/stylist_modern.yml']
        for look, fn, count, default in (
                ('Hair_Color', 'AddHeadPalette', 700, False),
                ('Hair', 'AddHeadStyle', 50, False),
                ('Clothes_Color', 'AddBodyPalette', 700, True)):
            server = rows(yml, look)
            for mode in ('Files', 'LineageFiles'):
                client = files[f'client/{mode}/{CLIENT_PATH}']
                values = [int(v) for v in re.findall(rf'^StylingShop\.{fn}\((\d+),', client, re.M)]
                self.assertEqual(len(values), count + int(default))
                self.assertEqual(set(values), set(range(0 if default else 1, count + 1)))
                self.assertEqual({i: value for i, value in enumerate(values, 1)},
                                 {i: value for i, (value, _) in server.items() if i != -1})
        config = files['conf/battle/stylist_generated.conf']
        for line in ('max_cloth_color: 700', 'max_hair_color: 700', 'max_hair_style: 50'):
            self.assertIn(line, config)
        self.assertIn('CostsDoram:', rows(yml, 'Hair')[10][1])
        self.assertNotIn('CostsDoram:', rows(yml, 'Hair')[50][1])
        self.assertNotIn('CostsDoram:', rows(yml, 'Hair_Color')[700][1])
        self.assertIn('RequiredItem: New_Style_Coupon', rows(yml, 'Hair')[24][1])
        self.assertIn('Price: 100000', rows(yml, 'Hair')[50][1])

    def test_independent_counts_and_doram_opt_in(self):
        files = build_files(Settings(700, 12, 50, True, 12345))
        yml = files['db/re/stylist_modern.yml']
        self.assertEqual(max(v for v, _ in rows(yml, 'Hair_Color').values()), 12)
        self.assertEqual(max(v for v, _ in rows(yml, 'Clothes_Color').values()), 700)
        self.assertIn('CostsDoram:', rows(yml, 'Hair')[50][1])
        self.assertIn('Price: 12345', rows(yml, 'Hair')[50][1])
        self.assertIn('ColorableDoram: false', rows(yml, 'Hair')[2][1])
        for look in ('Hair', 'Hair_Color', 'Clothes_Color'):
            for _, entry in rows(yml, look).values():
                self.assertIn('CostsDoram:', entry)

    def test_zero_colors_shrinking_and_default_sentinels(self):
        for limit in (0, 1, 2, 6):
            with self.subTest(limit=limit):
                yml = build_files(Settings(limit, limit, 1))['db/re/stylist_modern.yml']
                for look in ('Hair_Color', 'Clothes_Color'):
                    options = rows(yml, look)
                    self.assertEqual({v for v, _ in options.values()}, set(range(limit + 1)))
                    self.assertEqual(options[-1][0], 0)
                    self.assertIn('Price: 0', options[-1][1])
                self.assertEqual(len(rows(yml, 'Hair')), 1)

    def test_preserves_outfits_accessories_and_existing_costs(self):
        baseline = generate()[0]
        yml = build_files(Settings(700, 700, 50))['db/re/stylist_modern.yml']
        for look in ('Body2', 'Head_Top', 'Head_Mid', 'Head_Bottom'):
            def section(text):
                return text.split(f'  - Look: {look}\n', 1)[1].split('  - Look:', 1)[0]
            self.assertEqual(section(baseline), section(yml))
        for look in ('Hair', 'Hair_Color', 'Clothes_Color'):
            for index, entry in rows(baseline, look).items():
                self.assertEqual(rows(yml, look)[index], entry)

    def test_conf_imports_overrides_cycles_and_missing_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'base.conf').write_text('max_hair_style: 45\nmax_hair_color: 8\nmax_cloth_color: 7\n')
            (root / 'custom.conf').write_text('import: base.conf\nmax_cloth_color: 700 // custom pack\nmax_hair_style: 50\n')
            self.assertEqual(read_conf(root / 'custom.conf'), dict(max_hair_style=50, max_hair_color=8, max_cloth_color=700))
            (root / 'base.conf').write_text('import: custom.conf\n')
            with self.assertRaisesRegex(ValueError, 'cycle'):
                read_conf(root / 'custom.conf')
            (root / 'base.conf').write_text('import: missing.conf\n')
            with self.assertRaises(OSError):
                read_conf(root / 'base.conf')
            for content in ('max_hair_style: -1', 'max_hair_color: 1.5', 'min_hair_color: 1'):
                (root / 'base.conf').write_text(content)
                with self.assertRaises(ValueError):
                    read_conf(root / 'base.conf')

    def test_invalid_settings_and_storage_boundary(self):
        for settings in (Settings(-1, 8, 50), Settings(7, MAX_COUNT + 1, 50),
                         Settings(7, 8, 0), Settings(7, 8, True),
                         Settings(7, 8, 50, new_entry_price=-1)):
            with self.assertRaises(ValueError):
                settings.validate()
        files = build_files(Settings(MAX_COUNT, 0, 1))
        options = rows(files['db/re/stylist_modern.yml'], 'Clothes_Color')
        self.assertEqual(max(options), 32767)
        self.assertEqual(max(v for v, _ in options.values()), MAX_COUNT)

    def test_manifest_and_existing_output_protection(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / 'package'
            write_package(Settings(700, 700, 50), destination)
            manifest = json.loads((destination / 'manifest.json').read_text())
            for name, expected in manifest.items():
                self.assertEqual(hashlib.sha256((destination / name).read_bytes()).hexdigest(), expected)
            with self.assertRaisesRegex(ValueError, 'empty directory'):
                write_package(Settings(1, 1, 1), destination)
            self.assertEqual(json.loads((destination / 'settings.json').read_text())['max_cloth_color'], 700)

    def test_cli_conf_override_and_wizard_invalid_input_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            command = [sys.executable, str(Path(__file__).with_name('configure_catalogue.py'))]
            path = Path(directory)
            conf = path / 'client.conf'
            conf.write_text('max_cloth_color: 700\nmax_hair_color: 8\nmax_hair_style: 45\n')
            run = subprocess.run(command + ['--from-conf', str(conf), '--hairstyles', '50', '--output', str(path / 'conf')],
                                 capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(json.loads((path / 'conf/settings.json').read_text())['max_hair_style'], 50)
            run = subprocess.run(command + ['--output', str(path / 'wizard')], input='bad\n700\n12\n50\n',
                                 capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn('Enter a whole number', run.stdout)
            self.assertEqual(json.loads((path / 'wizard/settings.json').read_text())['max_hair_color'], 12)
            run = subprocess.run(command + ['--hairstyles', '50'], capture_output=True, text=True)
            self.assertNotEqual(run.returncode, 0)
            self.assertIn('Missing settings', run.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)
