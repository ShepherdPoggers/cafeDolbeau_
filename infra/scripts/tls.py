#!/usr/bin/env python3
"""Certbot DNS-01 et publication transactionnelle des certificats Nginx (hôte EC2)."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import tempfile

ROOT = Path('/opt/cafedolbeau')
CERTBOT_IMAGE = ('certbot/dns-cloudflare:v5.10.0@sha256:'
                 '6d5e1e84f687ce81786c97cbeccb9dda94d86bbb29a81dbb85527bd68008d77d')


def run(command):
    # Certbot conserve ses détails dans tls/*/logs, privés. Ne jamais les envoyer à SSM.
    result = subprocess.run([str(part) for part in command], capture_output=True, timeout=1500)
    if result.returncode:
        raise RuntimeError(f'Échec de {command[0]} (code {result.returncode}) ; consulter les journaux TLS privés sur EC2.')
    return result.stdout


def private_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as output:
        temporary = Path(output.name)
        os.fchmod(output.fileno(), 0o600)
        output.write(content)
    temporary.replace(path)


class TLS:
    def __init__(self, config, root=ROOT):
        self.config = config
        self.root = root
        self.folder = root / 'tls'
        self.domain = config['domain']

    def certbot(self, staging=False, renew=False, dry_run=False):
        storage = self.folder / ('staging' if staging else 'production')
        for name in ('config', 'work', 'logs'):
            (storage / name).mkdir(parents=True, exist_ok=True, mode=0o700)
        command = ['docker', 'run', '--rm', '--log-driver', 'none',
                   '-v', f'{storage / "config"}:/etc/letsencrypt',
                   '-v', f'{storage / "work"}:/var/lib/letsencrypt',
                   '-v', f'{storage / "logs"}:/var/log/letsencrypt',
                   '-v', f'{self.folder / "cloudflare.ini"}:/run/secrets/cloudflare.ini:ro',
                   CERTBOT_IMAGE, 'renew' if renew else 'certonly',
                   '--non-interactive', '--cert-name', self.domain,
                   '--dns-cloudflare', '--dns-cloudflare-credentials', '/run/secrets/cloudflare.ini',
                   '--dns-cloudflare-propagation-seconds', '60']
        if not renew:
            command += ['--agree-tos', '--email', self.config['email'],
                        '--keep-until-expiring', '-d', self.domain]
            if staging:
                command += ['--test-cert']
        if dry_run:
            command += ['--dry-run']
        run(command)

    def validate(self, chain, key):
        # load_cert_chain vérifie aussi que la clé privée correspond au certificat.
        ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER).load_cert_chain(chain, key)
        run(['openssl', 'x509', '-in', chain, '-noout', '-checkend', '86400'])
        run(['openssl', 'verify', '-purpose', 'sslserver', '-verify_hostname', self.domain,
             '-untrusted', chain, chain])

    def compose(self, *args):
        current = self.root / 'current'
        return run(['docker', 'compose', '--project-name', 'cafedolbeau_',
                    '--env-file', current / '.env', '-f', current / 'compose.yaml',
                    'exec', '-T', 'proxy', 'nginx', '-c', '/tmp/nginx.conf', *args])

    def publish(self, reload=False):
        source = self.folder / 'production/config/live' / self.domain
        chain, key = source / 'fullchain.pem', source / 'privkey.pem'
        self.validate(chain, key)
        served = self.folder / 'served'
        # Le GID provient de l'image effectivement déployée, sans supposer 101.
        gid = int(self.config['nginx_gid'])
        served.mkdir(exist_ok=True, mode=0o750)
        os.chown(served, 0, gid)
        served.chmod(0o750)
        link = served / 'current'
        previous = os.readlink(link) if link.is_symlink() else None
        if previous and all((served / previous / name).read_bytes() == (source / name).read_bytes()
                            for name in ('fullchain.pem', 'privkey.pem')):
            return False
        generation = Path(tempfile.mkdtemp(prefix='cert-', dir=served))
        os.chown(generation, 0, gid)
        generation.chmod(0o750)
        for name in ('fullchain.pem', 'privkey.pem'):
            target = generation / name
            target.write_bytes((source / name).read_bytes())
            os.chown(target, 0, gid)
            target.chmod(0o640)
        self.switch(generation.name)
        try:
            if reload:
                self.compose('-t')
                self.compose('-s', 'reload')
        except Exception:
            if previous:
                self.switch(previous)
                # Le master conserve l'ancien certificat si la validation échoue.
            else:
                link.unlink()
            shutil.rmtree(generation)
            raise
        for old in served.glob('cert-*'):
            if old.name not in (generation.name, previous):
                shutil.rmtree(old)
        print('Certificat TLS publié' + (' et Nginx rechargé.' if reload else '.'))
        return True

    def switch(self, target):
        temporary = self.folder / 'served/current.new'
        temporary.unlink(missing_ok=True)
        temporary.symlink_to(target)
        temporary.replace(self.folder / 'served/current')

    def prepare(self, release):
        self.folder.mkdir(mode=0o700, exist_ok=True)
        self.folder.chmod(0o700)
        private_write(self.folder / 'cloudflare.ini', (release / 'cloudflare.ini').read_bytes())
        run(['docker', 'pull', CERTBOT_IMAGE])
        # Test d'émission ET de renouvellement isolé, une fois par domaine/compte.
        marker = self.folder / ('staging-ok-' + hashlib.sha256(self.domain.encode()).hexdigest())
        if not marker.exists():
            self.certbot(staging=True)
            self.certbot(staging=True, renew=True, dry_run=True)
            private_write(marker, b'ok\n')
        self.certbot()
        self.config['nginx_gid'] = int(run(['docker', 'run', '--rm', '--entrypoint', 'id',
                                          self.config['proxy_image'], '-g', 'nginx']).strip())
        self.publish()
        private_write(self.folder / 'config.json', json.dumps(self.config).encode())


def check_https(release, domain):
    compose = ['docker', 'compose', '--project-name', 'cafedolbeau_',
               '--env-file', release / '.env', '-f', release / 'compose.yaml']
    container = run([*compose, 'ps', '-q', 'proxy']).decode().strip()
    networks = json.loads(run(['docker', 'inspect', '--format',
                              '{{json .NetworkSettings.Networks}}', container]))
    if len(networks) != 1:
        raise RuntimeError('Le proxy doit appartenir à un seul réseau Docker.')
    # Python dans l'image Certbot fournit CA publiques, vérification du nom et SNI.
    script = ("import http.client,ssl,sys; "
              "c=http.client.HTTPSConnection(sys.argv[1],8443,timeout=10,context=ssl.create_default_context()); "
              "c._create_connection=lambda address,timeout,source_address=None: "
              "__import__('socket').create_connection(('proxy',8443),timeout); "
              "c.request('GET','/healthz'); r=c.getresponse(); "
              "assert r.status==200,r.status; c.close()")
    run(['docker', 'run', '--rm', '--network', next(iter(networks)), '--entrypoint', 'python',
         CERTBOT_IMAGE, '-c', script, domain])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['prepare', 'renew', 'dry-run', 'check'])
    parser.add_argument('--release', type=Path, default=Path.cwd())
    args = parser.parse_args()
    os.umask(0o077)
    config = json.loads((args.release / 'tls.json').read_text()) if args.mode in ('prepare', 'check') else None
    if args.mode == 'prepare':
        # deploy.sh détient déjà deploy.lock jusqu'à la promotion de la version.
        TLS(config).prepare(args.release)
    elif args.mode == 'check':
        # deploy.sh détient le verrou et la version n'est pas encore promue.
        check_https(args.release, config['domain'])
    else:
        with (ROOT / 'deploy.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            tls = TLS(json.loads((ROOT / 'tls/config.json').read_text()))
            tls.certbot(renew=True, dry_run=args.mode == 'dry-run')
            if args.mode == 'renew':
                tls.publish(reload=True)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, ssl.SSLError, subprocess.TimeoutExpired):
        raise SystemExit('Opération TLS échouée ; certificat servi précédent conservé si disponible. '
                         'Consulter /opt/cafedolbeau/tls/*/logs et journalctl -u cafedolbeau-tls.service.') from None
