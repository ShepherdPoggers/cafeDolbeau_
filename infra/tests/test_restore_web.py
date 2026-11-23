import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('restore_web', ROOT / 'infra/scripts/lancer-restauration.py')
web = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(web)


class RestoreWebTests(unittest.TestCase):
    def test_custom_container_has_separate_configuration_and_project(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(web, 'ENV_FILE', Path(directory) / 'restauration-web.env'), \
                patch.object(web.subprocess, 'run', side_effect=[
                    SimpleNamespace(stdout=json.dumps([self.source()])), None, None, None,
                ]) as run:
            web.ENV_FILE.write_text('RESTORE_DB_VOLUME=original-volume\nRESTORE_HTTP_PORT=8001\n')
            original = web.ENV_FILE.read_text()
            self.assertEqual(web.main(['--container', 'BLA', '--port', '8002']), 0)
            self.assertEqual(web.ENV_FILE.read_text(), original)
            configs = list(Path(directory).glob('restauration-web-*.env'))
            self.assertEqual(len(configs), 1)
            self.assertIn('RESTORE_HTTP_PORT=8002', configs[0].read_text())
            command = run.call_args_list[3].args[0]
            project = command[command.index('--project-name') + 1]
            self.assertTrue(project.startswith('cafe-restauration-web-'))

    def source(self, mode='none'):
        return {'Id': 'test-id', 'HostConfig': {'NetworkMode': mode},
                'Config': {'Env': ['POSTGRES_DB=cafe_restore', 'POSTGRES_HOST_AUTH_METHOD=trust']},
                'Mounts': [{'Destination': '/var/lib/postgresql/data', 'Type': 'volume', 'Name': 'restored-volume'}]}

    def test_refuses_normal_database_before_stopping_anything(self):
        with patch.object(web.subprocess, 'run', return_value=SimpleNamespace(stdout=json.dumps([self.source('bridge')])) ) as run:
            with self.assertRaises(SystemExit):
                web.main([])
            run.assert_called_once()

    def test_reuses_restored_volume_and_stops_original_before_compose_up(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(web, 'ENV_FILE', Path(directory) / '.deploy/restore.env'), \
                patch.object(web.subprocess, 'run', side_effect=[
                    SimpleNamespace(stdout=json.dumps([self.source()])), None, None, None,
                ]) as run:
            self.assertEqual(web.main([]), 0)
            self.assertIn('RESTORE_DB_VOLUME=restored-volume', web.ENV_FILE.read_text())
            self.assertEqual(web.ENV_FILE.stat().st_mode & 0o777, 0o600)
        self.assertEqual(run.call_args_list[2].args[0], ['docker', 'stop', 'test-id'])
        self.assertIn('up', run.call_args_list[3].args[0])
        self.assertNotIn('-v', run.call_args_list[3].args[0])
