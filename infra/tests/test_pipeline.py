import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'infra/scripts' / f'{name}.py')
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


class PlanProtectionTests(unittest.TestCase):
    def change(self, actions, kind='aws_instance', before=None, after=None):
        return {'resource_changes': [{'address': 'aws_instance.main', 'type': kind,
                                     'change': {'actions': actions, 'before': before, 'after': after}}]}

    def test_creation_and_noop_allowed(self):
        for action in ('create', 'no-op'):
            module('check-plan').check(self.change([action]))

    def test_instance_and_volume_destruction_rejected(self):
        for kind in ('aws_instance', 'aws_ebs_volume', 'aws_volume_attachment'):
            for actions in (['delete'], ['create', 'delete'], ['delete', 'create']):
                with self.subTest(kind=kind, actions=actions), self.assertRaises(ValueError):
                    module('check-plan').check(self.change(actions, kind))

    def test_root_disk_mutation_rejected(self):
        with self.assertRaises(ValueError):
            module('check-plan').check(self.change(['update'], before={'root_block_device': [{'volume_size': 30}]},
                                                  after={'root_block_device': [{'volume_size': 40}]}))


class ProductionConfigTests(unittest.TestCase):
    def prepare(self, folder, env_content):
        (folder / 'docker').mkdir()
        (folder / 'infra/scripts').mkdir(parents=True)
        for relative in ('docker/compose.prod.yaml', 'infra/scripts/deploy.sh'):
            (folder / relative).write_bytes((ROOT / relative).read_bytes())
        return subprocess.run(['python3', str(ROOT / 'infra/scripts/prepare-release.py')], cwd=folder,
                              env=os.environ | {'PRODUCTION_ENV': env_content,
                                                'IMAGE_TAG': 'a' * 40, 'PUBLIC_DOMAIN': 'cafe.example.com'},
                              text=True, capture_output=True)

    def test_missing_secrets_rejected_without_disclosure(self):
        marker = 'private-secret-must-not-be-printed'
        with tempfile.TemporaryDirectory() as folder:
            result = self.prepare(Path(folder), f'SECRET_KEY={marker}\n')
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn(marker, result.stdout + result.stderr)

    def test_prod_config_exposes_only_proxy_and_local_metrics(self):
        content = f'SECRET_KEY={"s" * 64}\nPOSTGRES_PASSWORD={"p" * 64}\nCLOUDFLARE_TUNNEL_TOKEN=test-token\n'
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            result = self.prepare(folder, content)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((folder / '.deploy/release/.env').stat().st_mode & 0o777, 0o600)
            config = json.loads(subprocess.check_output([
                'docker', 'compose', '--env-file', '.deploy/release/.env',
                '-f', '.deploy/release/compose.yaml', 'config', '--format', 'json'], cwd=folder))
            services = config['services']
            self.assertFalse(any('build' in s for s in services.values()))
            self.assertNotIn('ports', services['app'])
            self.assertNotIn('ports', services['db'])
            self.assertEqual(services['proxy']['ports'][0]['published'], '80')
            self.assertEqual(services['cloudflared']['ports'][0]['host_ip'], '127.0.0.1')
            self.assertEqual(services['app']['environment']['DJANGO_DEBUG'], 'false')
            self.assertEqual(services['app']['environment']['DJANGO_SESSION_COOKIE_SECURE'], 'true')
            self.assertEqual(services['app']['image'], services['init']['image'])
            self.assertEqual(services['app']['image'], services['secrets']['image'])


class MigrationFailureTests(unittest.TestCase):
    def test_failed_migration_never_starts_app_or_promotes_release(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            release = root / 'releases/test'
            release.mkdir(parents=True)
            binaries = root / 'bin'
            binaries.mkdir()
            docker = binaries / 'docker'
            docker.write_text('''#!/bin/bash
echo "$*" >> "$COMMAND_LOG"
if [[ "$*" == *"run --rm --no-deps init"* ]]; then exit 42; fi
''')
            docker.chmod(0o755)
            for filename in ('.env', 'compose.yaml', 'images.tar.gz'):
                (release / filename).write_text('test')
            script = (ROOT / 'infra/scripts/deploy.sh').read_text().replace('/opt/cafedolbeau', str(root))
            (release / 'deploy.sh').write_text(script)
            (release / 'SHA256SUMS').write_text(''.join(
                f'{hashlib.sha256((release / file).read_bytes()).hexdigest()}  {file}\n'
                for file in ('.env', 'compose.yaml', 'images.tar.gz', 'deploy.sh')))
            log = root / 'commands.log'
            result = subprocess.run(['bash', str(release / 'deploy.sh')],
                                    env=os.environ | {'PATH': f'{binaries}:{os.environ["PATH"]}', 'COMMAND_LOG': str(log)},
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, 42, result.stderr)
            self.assertIn('run --rm --no-deps init', log.read_text())
            self.assertNotIn('--wait-timeout 240 app', log.read_text())
            self.assertFalse((root / 'current').exists())


if __name__ == '__main__':
    unittest.main()
