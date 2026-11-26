"""TLS_DOCKER_TESTS=1 python3 -m unittest discover -s infra/tests -p test_tls_integration.py -v"""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch
import uuid

import test_tls as certificates

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('tls_integration', ROOT / 'infra/scripts/tls.py')
tls = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tls)


@unittest.skipUnless(os.environ.get('TLS_DOCKER_TESTS') == '1', 'Activer TLS_DOCKER_TESTS pour les conteneurs isolés')
class NginxTLSIntegrationTests(unittest.TestCase):
    def test_real_nginx_certificate_checks_reload_and_internal_health(self):
        certificates.TLSCertificateTests.setUpClass()
        self.addCleanup(certificates.TLSCertificateTests.tearDownClass)
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            suffix = uuid.uuid4().hex[:10]
            network = f'cafe-tls-test-{suffix}'
            image = f'cafe-tls-test:{suffix}'
            proxy = f'cafe-tls-proxy-{suffix}'
            app = f'cafe-tls-app-{suffix}'

            def docker(*args, check=True):
                return subprocess.run(['docker', *map(str, args)], check=check,
                                      capture_output=True, timeout=180)

            def cleanup():
                docker('rm', '-f', proxy, app, check=False)
                docker('network', 'rm', network, check=False)
                docker('image', 'rm', image, check=False)
            self.addCleanup(cleanup)
            docker('build', '-f', 'docker/proxy.prod.Dockerfile', '-t', image, ROOT)
            gid = int(docker('run', '--rm', '--entrypoint', 'id', image, '-g', 'nginx').stdout)
            served = folder / 'served'
            served.mkdir(mode=0o755)
            for name in ('valid', 'renewed', 'expired'):
                target = served / name
                target.mkdir(mode=0o755)
                for file in ('privkey.pem', 'fullchain.pem'):
                    (target / file).write_bytes((certificates.TLSCertificateTests.certificates[name] / file).read_bytes())
                    (target / file).chmod(0o640)
            docker('run', '--rm', '--user', '0:0', '--entrypoint', 'chown',
                   '-v', f'{served}:/tls', image, '-R', f'{os.getuid()}:{gid}', '/tls')
            (served / 'current').symlink_to('valid')
            (folder / 'ca.pem').write_bytes((certificates.TLSCertificateTests.ca / 'ca.pem').read_bytes())
            docker('network', 'create', network)
            app_script = ('from http.server import HTTPServer,BaseHTTPRequestHandler; '
                          'H=type("H",(BaseHTTPRequestHandler,),'
                          '{"do_GET":lambda s:(s.send_response(200),s.end_headers(),s.wfile.write(b"ok"))}); '
                          'HTTPServer(("0.0.0.0",8000),H).serve_forever()')
            docker('run', '-d', '--name', app, '--network', network, '--network-alias', 'app',
                   '--entrypoint', 'python', tls.CERTBOT_IMAGE, '-c', app_script)
            docker('run', '-d', '--name', proxy, '--network', network, '--network-alias', 'proxy',
                   '-e', 'PUBLIC_DOMAIN=cafe.example.com', '-v', f'{served}:/etc/nginx/tls:ro', image)
            for attempt in range(20):
                if docker('exec', proxy, 'nginx', '-c', '/tmp/nginx.conf', '-t', check=False).returncode == 0:
                    break
                time.sleep(0.2)
            else:
                self.fail(docker('logs', proxy).stderr.decode())
            self.assertEqual(docker('port', proxy).stdout, b'')
            release = folder / 'release'
            release.mkdir()
            (release / '.env').write_text('')
            (release / 'compose.yaml').write_text('services: {}\n')
            def original(command):
                result = subprocess.run([str(p) for p in command], capture_output=True, timeout=60)
                if result.returncode:
                    raise RuntimeError(result.stderr.decode())
                return result.stdout

            def run(command):
                # Substituer uniquement la découverte Compose de ce conteneur isolé.
                if command[:2] == ['docker', 'compose']:
                    return (proxy + '\n').encode()
                if command[:2] == ['docker', 'run']:
                    command = command[:2] + ['-v', f'{folder}/ca.pem:/test-ca.pem:ro',
                                             '-e', 'SSL_CERT_FILE=/test-ca.pem'] + command[2:]
                return original(command)

            def verify(domain='cafe.example.com'):
                with patch.object(tls, 'run', side_effect=run):
                    tls.check_https(release, domain)

            verify()
            with self.assertRaises(RuntimeError):
                verify('other.example.com')
            # Un client sans la CA de test doit refuser ce certificat.
            with patch.object(tls, 'run', side_effect=lambda command:
                              (proxy + '\n').encode() if command[:2] == ['docker', 'compose'] else original(command)):
                with self.assertRaises(RuntimeError):
                    tls.check_https(release, 'cafe.example.com')
            for name, valid in [('renewed', True), ('expired', False), ('valid', True)]:
                (served / 'current.new').symlink_to(name)
                (served / 'current.new').replace(served / 'current')
                docker('exec', proxy, 'nginx', '-c', '/tmp/nginx.conf', '-t')
                docker('exec', proxy, 'nginx', '-c', '/tmp/nginx.conf', '-s', 'reload')
                time.sleep(0.3)
                if valid:
                    verify()
                else:
                    with self.assertRaises(RuntimeError):
                        verify()
            docker('exec', proxy, 'wget', '-qO-', 'http://127.0.0.1:8080/healthz')
            docker('exec', proxy, 'wget', '-qO-', 'http://127.0.0.1:8081/healthz')
