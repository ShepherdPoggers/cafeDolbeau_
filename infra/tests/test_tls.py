import importlib.util
import json
import os
from pathlib import Path
import ssl
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('tls', ROOT / 'infra/scripts/tls.py')
tls = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tls)


class TLSCertificateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.ca = Path(cls.temporary.name)
        def openssl(*args):
            subprocess.run(['openssl', *map(str, args)], check=True, capture_output=True)
        openssl('req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '3',
                '-addext', 'basicConstraints=critical,CA:TRUE',
                '-addext', 'keyUsage=critical,keyCertSign,cRLSign',
                '-subj', '/CN=TLS Test CA', '-keyout', cls.ca / 'ca.key', '-out', cls.ca / 'ca.pem')
        cls.certificates = {}
        for name, domain, days in [('valid', 'cafe.example.com', 2),
                                    ('renewed', 'cafe.example.com', 3),
                                    ('wrong', 'other.example.com', 2),
                                    ('expired', 'cafe.example.com', -1)]:
            folder = cls.ca / name
            folder.mkdir()
            openssl('req', '-new', '-newkey', 'rsa:2048', '-nodes', '-subj', f'/CN={domain}',
                    '-keyout', folder / 'privkey.pem', '-out', folder / 'request.pem')
            (folder / 'extensions').write_text(
                f'subjectAltName=DNS:{domain}\nextendedKeyUsage=serverAuth\n'
                'basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\n'
                'authorityKeyIdentifier=keyid,issuer\nsubjectKeyIdentifier=hash\n')
            openssl('x509', '-req', '-in', folder / 'request.pem', '-CA', cls.ca / 'ca.pem',
                    '-CAkey', cls.ca / 'ca.key', '-CAcreateserial', '-days', days,
                    '-extfile', folder / 'extensions', '-out', folder / 'fullchain.pem')
            cls.certificates[name] = folder

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def setUp(self):
        self.working = tempfile.TemporaryDirectory()
        self.addCleanup(self.working.cleanup)
        self.root = Path(self.working.name)
        self.manager = tls.TLS({'domain': 'cafe.example.com', 'email': 'admin@example.com',
                                'proxy_image': 'proxy:test', 'nginx_gid': os.getgid()}, root=self.root)
        self.source = self.root / 'tls/production/config/live/cafe.example.com'
        self.source.mkdir(parents=True)
        self.served = self.root / 'tls/served'
        self.environment = patch.dict(os.environ, {'SSL_CERT_FILE': str(self.ca / 'ca.pem')})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        ownership = patch.object(tls.os, 'chown')
        ownership.start()
        self.addCleanup(ownership.stop)
        self.load('valid')

    def load(self, name):
        for file in ('fullchain.pem', 'privkey.pem'):
            (self.source / file).write_bytes((self.certificates[name] / file).read_bytes())

    def test_valid_certificate_permissions_and_unchanged_certificate_skips_reload(self):
        self.assertTrue(self.manager.publish())
        self.assertEqual((self.served / 'current/privkey.pem').stat().st_mode & 0o777, 0o640)
        self.assertEqual(self.served.stat().st_mode & 0o777, 0o750)
        self.assertEqual({p.name for p in (self.served / 'current').iterdir()}, {'fullchain.pem', 'privkey.pem'})
        with patch.object(self.manager, 'compose') as compose:
            self.assertFalse(self.manager.publish(reload=True))
            compose.assert_not_called()

    def test_wrong_domain_expired_untrusted_and_wrong_key_are_rejected_before_publication(self):
        self.manager.publish()
        previous = os.readlink(self.served / 'current')
        for name in ('wrong', 'expired'):
            self.load(name)
            with self.subTest(name=name), self.assertRaises(RuntimeError):
                self.manager.publish(reload=True)
            self.assertEqual(os.readlink(self.served / 'current'), previous)
        self.load('valid')
        with patch.dict(os.environ, {'SSL_CERT_FILE': '/nonexistent', 'SSL_CERT_DIR': '/nonexistent'}):
            with self.assertRaises(RuntimeError):
                self.manager.publish()
        (self.source / 'privkey.pem').write_bytes((self.certificates['wrong'] / 'privkey.pem').read_bytes())
        with self.assertRaises(ssl.SSLError):
            self.manager.publish()
        self.assertEqual(os.readlink(self.served / 'current'), previous)

    def test_renewal_validates_then_reloads_and_retains_previous_pair(self):
        self.manager.publish()
        previous = os.readlink(self.served / 'current')
        self.load('renewed')
        with patch.object(self.manager, 'compose') as compose:
            self.assertTrue(self.manager.publish(reload=True))
            self.assertEqual(compose.call_args_list, [unittest.mock.call('-t'), unittest.mock.call('-s', 'reload')])
        self.assertNotEqual(os.readlink(self.served / 'current'), previous)
        self.assertTrue((self.served / previous).exists())

    def test_failed_validation_or_reload_restores_previous_pair(self):
        self.manager.publish()
        previous = os.readlink(self.served / 'current')
        self.load('renewed')
        for failure in ([RuntimeError('invalid config')], [b'', RuntimeError('reload failed')]):
            with patch.object(self.manager, 'compose', side_effect=failure), self.assertRaises(RuntimeError):
                self.manager.publish(reload=True)
            self.assertEqual(os.readlink(self.served / 'current'), previous)
            self.assertEqual(len(list(self.served.glob('cert-*'))), 1)

    def test_prepare_checks_staging_before_production_and_reuses_marker(self):
        release = self.root / 'release'
        release.mkdir()
        (release / 'cloudflare.ini').write_text('dns_cloudflare_api_token = private-token\n')
        with patch.object(tls, 'run', return_value=str(os.getgid()).encode()), \
                patch.object(self.manager, 'certbot') as certbot, patch.object(self.manager, 'publish'):
            self.manager.prepare(release)
            self.assertEqual(certbot.call_args_list, [unittest.mock.call(staging=True),
                             unittest.mock.call(staging=True, renew=True, dry_run=True), unittest.mock.call()])
            certbot.reset_mock()
            self.manager.prepare(release)
            certbot.assert_called_once_with()
        for file in ('cloudflare.ini', 'config.json'):
            self.assertEqual((self.root / 'tls' / file).stat().st_mode & 0o777, 0o600)
        self.assertNotIn('private-token', (self.root / 'tls/config.json').read_text())

    def test_staging_failure_never_requests_production_or_publishes(self):
        release = self.root / 'release'
        release.mkdir()
        (release / 'cloudflare.ini').write_text('dns_cloudflare_api_token = private-token\n')
        with patch.object(tls, 'run'), patch.object(self.manager, 'certbot', side_effect=RuntimeError), \
                patch.object(self.manager, 'publish') as publish, self.assertRaises(RuntimeError):
            self.manager.prepare(release)
        publish.assert_not_called()
        self.assertFalse(list((self.root / 'tls').glob('staging-ok-*')))

    def test_certbot_credentials_are_a_readonly_file_not_command_or_environment(self):
        with patch.object(tls, 'run') as run:
            self.manager.certbot(renew=True)
        command = run.call_args.args[0]
        self.assertIn(tls.CERTBOT_IMAGE, command)
        self.assertIn('renew', command)
        self.assertIn(f'{self.root}/tls/cloudflare.ini:/run/secrets/cloudflare.ini:ro', command)
        self.assertNotIn('--force-renewal', command)
        self.assertNotIn('-e', command)
        self.assertNotIn('/var/run/docker.sock', ' '.join(command))


class TLSDeploymentTests(unittest.TestCase):
    def test_certificate_failure_precedes_any_service_stop(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            release = root / 'release'
            release.mkdir()
            binaries = root / 'bin'
            binaries.mkdir()
            for name, content in {
                'docker': '#!/bin/sh\necho "$*" >> "$COMMAND_LOG"\n',
                'python3': '#!/bin/sh\nexit 41\n',
            }.items():
                (binaries / name).write_text(content)
                (binaries / name).chmod(0o755)
            script = (ROOT / 'infra/scripts/deploy.sh').read_text().replace('/opt/cafedolbeau', str(root))
            (release / 'deploy.sh').write_text(script)
            (release / 'SHA256SUMS').write_text('')
            (release / 'images.tar.gz').write_text('test')
            # sha256sum exige au moins une entrée valide.
            import hashlib
            (release / 'SHA256SUMS').write_text(hashlib.sha256(b'test').hexdigest() + '  images.tar.gz\n')
            result = subprocess.run(['bash', str(release / 'deploy.sh')], capture_output=True,
                                    env=os.environ | {'PATH': f'{binaries}:{os.environ["PATH"]}',
                                                      'COMMAND_LOG': str(root / 'commands')})
            self.assertEqual(result.returncode, 41, result.stderr)
            self.assertNotIn('stop', (root / 'commands').read_text())
            self.assertFalse((root / 'current').exists())


if __name__ == '__main__':
    unittest.main()
