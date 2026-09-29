"""Check that tools/StylistTools.exe produces byte-identical output to the Python generator.

Requires Windows, a built StylistTools.exe and STYLIST_SERVER_ROOT set to the patched tree:
    python -m unittest discover -s tools/source -p "test_*.py" -v
"""
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

PACKAGE = Path(__file__).resolve().parents[2]
EXE = PACKAGE / 'tools' / 'StylistTools.exe'
sys.path.insert(0, str(PACKAGE / 'tools' / 'catalogue'))

from configure_catalogue import Settings, write_package  # noqa: E402
from generate_catalogue import ROOT  # noqa: E402

CASES = (
    Settings(700, 700, 50),
    Settings(700, 12, 50, True, 12345),
    Settings(667, 5, 42),
    Settings(0, 0, 1),
    Settings(1, 1, 1, True),
    Settings(6, 2, 45),
    Settings(32766, 0, 1),
)


def files(folder):
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in sorted(folder.rglob('*')) if p.is_file()}


@unittest.skipUnless(EXE.is_file() and (ROOT / 'src/map/stylist.hpp').is_file(),
                     'Needs tools/StylistTools.exe and STYLIST_SERVER_ROOT')
class StylistToolsTests(unittest.TestCase):
    def run_exe(self, *args, stdin=None, server=None):
        env = dict(os.environ)
        env.pop('STYLIST_SERVER_ROOT', None)
        if server:
            env['STYLIST_SERVER_ROOT'] = str(server)
        return subprocess.run([str(EXE), *map(str, args)], input=stdin, capture_output=True, text=True, env=env)

    def assertSameOutput(self, settings, extra=(), server=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_package(settings, root / 'python')
            args = ['--cloth-colors', settings.max_cloth_color, '--hair-colors', settings.max_hair_color,
                    '--hairstyles', settings.max_hair_style, '--new-entry-price', settings.new_entry_price,
                    '--output', root / 'exe', *extra]
            if settings.include_doram:
                args.append('--include-doram')
            run = self.run_exe(*args, server=server)
            self.assertEqual(run.returncode, 0, run.stderr)
            expected, actual = files(root / 'python'), files(root / 'exe')
            self.assertEqual(sorted(expected), sorted(actual))
            for name in expected:
                self.assertEqual(expected[name], actual[name], name)

    def test_builtin_data_matches_python(self):
        for settings in CASES:
            with self.subTest(settings=settings):
                self.assertSameOutput(settings)

    def test_server_folder_matches_python(self):
        for settings in CASES[:3]:
            with self.subTest(settings=settings):
                self.assertSameOutput(settings, server=ROOT)
                self.assertSameOutput(settings, extra=('--server', ROOT))

    def test_conf_override_wizard_and_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'base.conf').write_text('max_hair_style: 45\nmax_hair_color: 8\n')
            (path / 'client.conf').write_text('import: base.conf\nmax_cloth_color: 700 // pack\n')
            run = self.run_exe('--from-conf', path / 'client.conf', '--hairstyles', 50, '--output', path / 'conf')
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn('"max_hair_style": 50', (path / 'conf/settings.json').read_text())
            self.assertIn('"max_hair_color": 8', (path / 'conf/settings.json').read_text())
            run = self.run_exe('--output', path / 'wizard', stdin='bad\n700\n12\n50\n')
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn('Enter a whole number', run.stdout)
            self.assertIn('"max_hair_color": 12', (path / 'wizard/settings.json').read_text())
            run = self.run_exe('--cloth-colors', 1, '--hair-colors', 1, '--hairstyles', 1, '--output', path / 'conf')
            self.assertEqual(run.returncode, 1)
            self.assertIn('empty directory', run.stderr)
            run = self.run_exe('--hairstyles', 50)
            self.assertEqual(run.returncode, 1)
            self.assertIn('Missing settings', run.stderr)
            run = self.run_exe('--cloth-colors', 7, '--hair-colors', 8, '--hairstyles', 0, '--output', path / 'bad')
            self.assertEqual(run.returncode, 1)
            self.assertIn('max_hair_style must be an integer from 1 to 32766', run.stderr)
            (path / 'base.conf').write_text('import: client.conf\n')
            run = self.run_exe('--from-conf', path / 'client.conf', '--output', path / 'cycle')
            self.assertIn('cycle', run.stderr)
            self.assertEqual(self.run_exe('--bogus').returncode, 2)


@unittest.skipUnless(EXE.is_file(), 'Needs tools/StylistTools.exe')
class ChecksumTests(unittest.TestCase):
    def test_write_checksums_skips_ignored_files_and_passes_both_verifiers(self):
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory) / 'package'
            shutil.copytree(PACKAGE, package, ignore=shutil.ignore_patterns('generated', '__pycache__', 'SHA256SUMS.txt'))
            for junk in ('generated/run/settings.json', 'tools/__pycache__/x.pyc', 'README.md.pre-stylist.bak'):
                (package / junk).parent.mkdir(parents=True, exist_ok=True)
                (package / junk).write_text('junk')
            exe = package / 'tools' / 'StylistTools.exe'
            run = subprocess.run([str(exe), '--write-checksums'], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn('PASS:', run.stdout)
            listed = [line.split('  ', 1)[1] for line in (package / 'SHA256SUMS.txt').read_text().splitlines()]
            self.assertEqual(listed, sorted(listed))
            self.assertIn('tools/StylistTools.exe', listed)
            self.assertFalse([name for name in listed if name.startswith('generated/') or name.endswith(('.pyc', '.bak'))])
            python = subprocess.run([sys.executable, str(package / 'tools' / 'verify_package.py')], capture_output=True, text=True)
            self.assertEqual(python.returncode, 0, python.stderr)
            with (package / 'README.md').open('a') as stream:
                stream.write('changed')
            run = subprocess.run([str(exe), '--verify'], capture_output=True, text=True)
            self.assertEqual(run.returncode, 1)
            self.assertIn('Missing or changed file: README.md', run.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)
