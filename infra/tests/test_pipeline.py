import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import shlex
from types import SimpleNamespace
import unittest
from unittest.mock import patch

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
    def prepare(self, folder, secrets):
        (folder / 'docker').mkdir()
        (folder / 'infra/scripts').mkdir(parents=True)
        (folder / 'infra/systemd').mkdir()
        for relative in ('docker/compose.prod.yaml', 'infra/scripts/deploy.sh', 'infra/scripts/tls.py',
                         'infra/systemd/cafedolbeau-tls.service', 'infra/systemd/cafedolbeau-tls.timer'):
            (folder / relative).write_bytes((ROOT / relative).read_bytes())
        return subprocess.run(['python3', str(ROOT / 'infra/scripts/prepare-release.py')], cwd=folder,
                              env=os.environ | {'SECRET_KEY': '', 'POSTGRES_PASSWORD': '', 'CLOUDFLARE_TUNNEL_TOKEN': '',
                                                'CLOUDFLARE_DNS_API_TOKEN': 'dns-test-token',
                                                'LETSENCRYPT_EMAIL': 'admin@example.com',
                                                'IMAGE_TAG': 'a' * 40, 'PUBLIC_DOMAIN': 'cafe.example.com'} | secrets,
                              text=True, capture_output=True)

    def test_missing_secrets_rejected_without_disclosure(self):
        marker = 'private-secret-must-not-be-printed'
        with tempfile.TemporaryDirectory() as folder:
            result = self.prepare(Path(folder), {'SECRET_KEY': marker})
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn(marker, result.stdout + result.stderr)

    def test_prod_config_exposes_only_proxy_and_local_metrics(self):
        content = {'SECRET_KEY': 's' * 64, 'POSTGRES_PASSWORD': 'p' * 64, 'CLOUDFLARE_TUNNEL_TOKEN': 'test-token'}
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
            self.assertEqual({(p['host_ip'], p['published'], p['target'])
                              for p in services['proxy']['ports']},
                             {('0.0.0.0', '80', 8081), ('0.0.0.0', '443', 8444)})
            self.assertEqual(len(services['proxy']['ports']), 2)
            tls_mount = next(v for v in services['proxy']['volumes'] if v['target'] == '/etc/nginx/tls')
            self.assertTrue(tls_mount['read_only'])
            self.assertFalse(tls_mount['bind']['create_host_path'])
            self.assertNotIn('dns-test-token', (folder / '.deploy/release/.env').read_text())
            self.assertEqual((folder / '.deploy/release/cloudflare.ini').stat().st_mode & 0o777, 0o600)
            self.assertEqual(services['cloudflared']['ports'][0]['host_ip'], '127.0.0.1')
            self.assertEqual(services['app']['environment']['DJANGO_DEBUG'], 'false')
            self.assertEqual(services['app']['environment']['DJANGO_SESSION_COOKIE_SECURE'], 'true')
            self.assertEqual(services['app']['image'], services['init']['image'])
            self.assertEqual(services['app']['image'], services['secrets']['image'])

    def test_special_characters_preserved_without_logging_secrets(self):
        content = {'SECRET_KEY': 'x' * 32 + '''$HOME ${VARIABLE} "quote" 'apostrophe' \\path #comment''',
                   'POSTGRES_PASSWORD': 'p' * 48, 'CLOUDFLARE_TUNNEL_TOKEN': 'test-token'}
        with tempfile.TemporaryDirectory() as folder:
            result = self.prepare(Path(folder), content)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn(content['SECRET_KEY'], result.stdout + result.stderr)

    def test_multiline_secret_rejected_without_logging(self):
        content = {'SECRET_KEY': 's' * 64, 'POSTGRES_PASSWORD': 'p' * 48,
                   'CLOUDFLARE_TUNNEL_TOKEN': 'private-token\nINJECTED_VARIABLE=value'}
        with tempfile.TemporaryDirectory() as folder:
            result = self.prepare(Path(folder), content)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn('private-token', result.stdout + result.stderr)

    def test_dns_token_and_acme_email_are_required_without_disclosure(self):
        for invalid in ({'CLOUDFLARE_DNS_API_TOKEN': ''},
                        {'CLOUDFLARE_DNS_API_TOKEN': 'private-token\nINJECT=value'},
                        {'LETSENCRYPT_EMAIL': ''}, {'LETSENCRYPT_EMAIL': 'invalid'},
                        {'LETSENCRYPT_EMAIL': 'admin@exa\nmple.com'}):
            content = {'SECRET_KEY': 's' * 64, 'POSTGRES_PASSWORD': 'p' * 48,
                       'CLOUDFLARE_TUNNEL_TOKEN': 'test-token'} | invalid
            with self.subTest(invalid=list(invalid)), tempfile.TemporaryDirectory() as folder:
                result = self.prepare(Path(folder), content)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('private-token', result.stdout + result.stderr)

    def test_acme_email_trims_surrounding_pasted_whitespace(self):
        content = {'SECRET_KEY': 's' * 64, 'POSTGRES_PASSWORD': 'p' * 48,
                   'CLOUDFLARE_TUNNEL_TOKEN': 'test-token',
                   'LETSENCRYPT_EMAIL': ' \tadmin@example.com\r\n'}
        with tempfile.TemporaryDirectory() as folder:
            result = self.prepare(Path(folder), content)
            self.assertEqual(result.returncode, 0, result.stderr)
            config = json.loads((Path(folder) / '.deploy/release/tls.json').read_text())
            self.assertEqual(config['email'], 'admin@example.com')


class MigrationFailureTests(unittest.TestCase):
    def test_failed_migration_never_starts_app_or_promotes_release(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            release = root / 'releases/test'
            release.mkdir(parents=True)
            binaries = root / 'bin'
            binaries.mkdir()
            python = binaries / 'python3'
            python.write_text('#!/bin/sh\nexit 0\n')
            python.chmod(0o755)
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


class SSHKeysTests(unittest.TestCase):
    def test_sync_installs_all_keys_and_removes_revoked_keys(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / '.ssh'
            folder.mkdir()
            (folder / 'authorized_keys').write_text('old-revoked-key\n')
            keys = ["ssh-ed25519 AAAATest elliot", "ssh-ed25519 AAAASecond colleague's key"]
            args = shlex.split(module('deploy-ssm').ssh_keys_command(keys))
            user = SimpleNamespace(pw_dir=temporary, pw_uid=os.getuid(), pw_gid=os.getgid())
            with patch('pwd.getpwnam', return_value=user), patch('sys.argv', ['-c', args[3]]):
                exec(compile(args[2], '<ssh-key-sync>', 'exec'), {})
            self.assertEqual((folder / 'authorized_keys').read_text(), '\n'.join(keys) + '\n')
            self.assertEqual((folder / 'authorized_keys').stat().st_mode & 0o777, 0o600)
            self.assertEqual(folder.stat().st_mode & 0o777, 0o700)

    def test_empty_keys_rejected(self):
        with self.assertRaises(ValueError):
            module('deploy-ssm').ssh_keys_command([])


if __name__ == '__main__':
    unittest.main()
