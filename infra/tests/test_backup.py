import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('backup', ROOT / 'infra/scripts/sauvegarder-postgres.py')
backup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(backup)


class BackupTests(unittest.TestCase):
    def test_invalid_host_or_port_never_connects(self):
        for args in [['--host', '-bad'], ['--host', 'prod', '--port', '0']]:
            with patch.object(backup.subprocess, 'run') as run:
                with self.assertRaises(SystemExit):
                    backup.main(args)
                run.assert_not_called()

    def download(self, directory, payload=b'database', fail=False):
        metadata = {'path': '/opt/cafedolbeau/backups/export-abc12345/production.dump',
                    'sha256': hashlib.sha256(b'database').hexdigest(), 'bytes': 8}

        def run(command, **kwargs):
            if 'input' in kwargs:
                return subprocess.CompletedProcess(command, 0, json.dumps(metadata))
            kwargs['stdout'].write(payload)
            if fail:
                raise subprocess.CalledProcessError(1, command)
            return subprocess.CompletedProcess(command, 0)

        with patch.object(backup.subprocess, 'run', side_effect=run):
            return backup.main(['--host', 'ubuntu@prod', '--output-dir', directory])

    def test_download_checks_integrity_and_keeps_private_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = self.download(directory)
            self.assertEqual(archive.read_bytes(), b'database')
            self.assertEqual(archive.stat().st_mode & 0o777, 0o600)
            self.assertEqual(list(Path(directory).iterdir()), [archive])

    def test_corrupt_or_interrupted_download_removes_partial_file(self):
        for fail in [False, True]:
            with tempfile.TemporaryDirectory() as directory:
                with self.assertRaises((ValueError, subprocess.CalledProcessError)):
                    self.download(directory, b'corrupt', fail)
                self.assertEqual(list(Path(directory).iterdir()), [])

    def test_remote_backup_validates_archive_and_cleans_failed_dump(self):
        for fail in [False, True]:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / 'current').mkdir()
                binary = root / 'bin'
                binary.mkdir()
                docker = binary / 'docker'
                docker.write_text('''#!/usr/bin/env python3
import os, sys
if 'pg_dump' in sys.argv[-1]:
    sys.stdout.buffer.write(b'database')
    sys.exit(1 if os.environ['FAIL_DUMP'] == '1' else 0)
assert 'pg_restore' in sys.argv
assert sys.stdin.buffer.read() == b'database'
''')
                docker.chmod(0o700)
                script = backup.REMOTE_BACKUP.replace('/opt/cafedolbeau', directory)
                result = subprocess.run(['bash', '-s'], input=script, text=True, capture_output=True,
                                        env=os.environ | {'PATH': str(binary) + ':' + os.environ['PATH'],
                                                          'FAIL_DUMP': '1' if fail else '0'})
                self.assertFalse(list(root.rglob('*.part')))
                if fail:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(list(root.rglob('*.dump')))
                else:
                    self.assertEqual(result.returncode, 0, result.stderr)
                    metadata = json.loads(result.stdout)
                    self.assertEqual(Path(metadata['path']).read_bytes(), b'database')
                    self.assertEqual(metadata['sha256'], hashlib.sha256(b'database').hexdigest())
