import importlib.util
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('restore', ROOT / 'infra/scripts/restaurer-postgres.py')
restore = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(restore)


class RestoreTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.archive = Path(directory) / 'production.dump'
        self.archive.write_bytes(b'PGDMPtest')

    def test_missing_or_invalid_dump_never_calls_docker(self):
        for payload in [None, b'', b'not a dump']:
            if payload is None:
                self.archive.unlink()
            else:
                self.archive.write_bytes(payload)
            with patch.object(restore, 'docker') as docker:
                with self.assertRaises(SystemExit):
                    restore.main([str(self.archive)])
                docker.assert_not_called()

    def test_existing_container_is_preserved(self):
        with patch.object(restore, 'docker', return_value=SimpleNamespace(stdout='cafe-restauration-a8\n')) as docker:
            with self.assertRaises(SystemExit):
                restore.main([str(self.archive)])
            docker.assert_called_once()

    def test_restores_only_in_isolated_container_then_checks_data(self):
        with patch.object(restore, 'docker', side_effect=[
            SimpleNamespace(stdout=''), None, SimpleNamespace(returncode=0), None, None,
        ]) as docker:
            self.assertEqual(restore.main([str(self.archive)]), 0)
        calls = docker.call_args_list
        self.assertIn('none', calls[1].args)
        self.assertNotIn('-p', calls[1].args)
        self.assertIn('pg_restore', calls[3].args)
        self.assertIn('--single-transaction', calls[3].args)
        self.assertIn('cafe_restore', calls[3].args)
        self.assertIn('ON_ERROR_STOP=1', calls[4].args)
        self.assertFalse(any('rm' in call.args for call in calls))

    def test_restore_failure_prevents_success_checks(self):
        with patch.object(restore, 'docker', side_effect=[
            SimpleNamespace(stdout=''), None, SimpleNamespace(returncode=0),
            subprocess.CalledProcessError(1, 'pg_restore'),
        ]) as docker:
            with self.assertRaises(subprocess.CalledProcessError):
                restore.main([str(self.archive)])
            self.assertEqual(docker.call_count, 4)

    def test_readiness_timeout_does_not_attempt_restore(self):
        with patch.object(restore.time, 'sleep'), patch.object(restore, 'docker', side_effect=[
            SimpleNamespace(stdout=''), None,
            *[SimpleNamespace(returncode=1) for _ in range(30)],
        ]) as docker:
            with self.assertRaisesRegex(RuntimeError, 'ne devient pas prêt'):
                restore.main([str(self.archive)])
            self.assertFalse(any('pg_restore' in call.args for call in docker.call_args_list))
