import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('transfer', ROOT / 'infra/scripts/transferer-postgres.py')
transfer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(transfer)


class TransferTests(unittest.TestCase):
    def test_refuse_wrong_confirmation_and_option_injection(self):
        for host, confirm in [('ubuntu@prod', 'ubuntu@other'), ('-oProxyCommand=bad', '-oProxyCommand=bad')]:
            with self.subTest(host=host), patch.object(transfer.subprocess, 'run') as run:
                with self.assertRaises(SystemExit):
                    transfer.main(['--host', host, '--confirm-host', confirm])
                run.assert_not_called()

    def test_transfer_checksum_and_temporary_file_cleanup(self):
        calls = []

        def run(command, **kwargs):
            calls.append(command)
            if command[0] == 'docker':
                kwargs['stdout'].write(b'private-database')
                self.archive = Path(kwargs['stdout'].name)
                self.assertEqual(self.archive.stat().st_mode & 0o777, 0o600)
            elif 'stdin' in kwargs:
                self.assertEqual(kwargs['stdin'].read(), b'private-database')
                self.assertIn(transfer.hashlib.sha256(b'private-database').hexdigest(), command[-1])

        with patch.object(transfer.subprocess, 'run', side_effect=run):
            transfer.main(['--host', 'ubuntu@prod', '--confirm-host', 'ubuntu@prod'])
        self.assertFalse(self.archive.exists())
        self.assertEqual(len(calls), 3)
        self.assertIn('StrictHostKeyChecking=yes', calls[0])

    def test_failed_export_is_not_transferred(self):
        with patch.object(transfer.subprocess, 'run', side_effect=[None, subprocess.CalledProcessError(1, 'dump')]) as run:
            with self.assertRaises(subprocess.CalledProcessError):
                transfer.main(['--host', 'prod', '--confirm-host', 'prod'])
        self.assertEqual(run.call_count, 2)

    def test_native_service_uses_libpq_without_password_in_command(self):
        args = transfer.arguments(['--host', 'prod', '--confirm-host', 'prod', '--pg-service', 'cafe-local'])
        self.assertEqual(transfer.dump_command(args)[-1], 'service=cafe-local')


class RemoteImportTests(unittest.TestCase):
    def execute(self, failure='', checksum=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            current = root / 'current'
            current.mkdir()
            (current / '.env').touch()
            (current / 'compose.yaml').touch()
            binary = root / 'bin'
            binary.mkdir()
            docker = binary / 'docker'
            docker.write_text('''#!/usr/bin/env python3
import os, sys
from pathlib import Path
args = sys.argv[1:]
line = ' '.join(args)
with open(os.environ['EVENTS'], 'a') as out:
    out.write(line + '\\n')
failure = os.environ.get('FAILURE', '')
if failure == 'startup' and 'up -d' in line:
    sys.exit(1)
if 'pg_restore --no-password' in line:
    sys.stdin.buffer.read()
    sys.exit(1 if failure == 'restore' else 0)
if 'pg_dump' in line:
    if failure == 'backup':
        sys.exit(1)
    sys.stdout.buffer.write(b'previous-database')
elif 'pg_restore' in args:
    sys.stdin.buffer.read()
elif 'migrate --check' in line and failure == 'migrations':
    sys.exit(1)
''')
            docker.chmod(0o700)
            curl = binary / 'curl'
            curl.write_text('#!/bin/sh\nexit 0\n')
            curl.chmod(0o700)
            script = (ROOT / 'infra/scripts/importer-postgres.sh').read_text().replace('/opt/cafedolbeau', str(root))
            payload = b'local-database'
            result = subprocess.run(['bash', '-c', script, 'import', checksum or transfer.hashlib.sha256(payload).hexdigest()],
                                    input=payload, capture_output=True,
                                    env=os.environ | {'PATH': str(binary) + ':' + os.environ['PATH'],
                                                      'EVENTS': str(root / 'events'), 'FAILURE': failure})
            events = (root / 'events').read_text() if (root / 'events').exists() else ''
            backups = [path.read_bytes() for path in root.glob('backups/*/avant-import.dump')]
            self.assertFalse(list(root.glob('backups/*/source.dump')))
            return result, events, backups

    def test_success_backups_before_restore_then_reopens(self):
        result, events, backups = self.execute()
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual(backups, [b'previous-database'])
        self.assertLess(events.index('stop cloudflared proxy app'), events.index('pg_dump'))
        self.assertLess(events.index('pg_dump'), events.index('pg_restore --no-password'))
        self.assertLess(events.index('migrate --check'), events.index('up -d'))
        self.assertIn('--single-transaction', events)

    def test_failure_does_not_reopen_site(self):
        for failure in ['backup', 'restore', 'migrations']:
            with self.subTest(failure=failure):
                result, events, backups = self.execute(failure)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('up -d', events)
                self.assertIn('site maintenu arrêté', result.stderr.decode())
                if failure == 'backup':
                    self.assertNotIn('pg_restore --no-password', events)
                else:
                    self.assertEqual(backups, [b'previous-database'])

    def test_corrupted_transfer_does_not_stop_or_restore(self):
        result, events, backups = self.execute(checksum='0' * 64)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(events, '')
        self.assertEqual(backups, [])

    def test_failed_startup_stops_services_again(self):
        result, events, backups = self.execute('startup')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('up -d', events)
        self.assertTrue(events.rstrip().endswith('stop cloudflared proxy app'))
        self.assertEqual(backups, [b'previous-database'])


if __name__ == '__main__':
    unittest.main()
