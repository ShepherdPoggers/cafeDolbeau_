#!/usr/bin/env python3
"""Ouvrir Café Dolbeau en local avec la base déjà restaurée pour A8."""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT / '.deploy/restauration-web.env'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--container', default='cafe-restauration-a8',
                        help='Conteneur créé par restaurer-postgres.py.')
    parser.add_argument('--port', type=int, default=8001)
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error('Port invalide.')
    project = 'cafe-restauration-web'
    env_file = ENV_FILE
    if args.container != 'cafe-restauration-a8':
        suffix = hashlib.sha256(args.container.encode()).hexdigest()[:12]
        project += '-' + suffix
        env_file = ENV_FILE.with_name(f'restauration-web-{suffix}.env')
    result = subprocess.run(['docker', 'inspect', '--type', 'container', args.container],
                            capture_output=True, text=True, check=True)
    container = json.loads(result.stdout)[0]
    environment = container['Config'].get('Env', [])
    if (container['HostConfig'].get('NetworkMode') != 'none'
            or 'POSTGRES_DB=cafe_restore' not in environment
            or 'POSTGRES_HOST_AUTH_METHOD=trust' not in environment):
        parser.error('La source doit être le conteneur isolé créé par restaurer-postgres.py.')
    mounts = [mount for mount in container['Mounts']
              if mount['Destination'] == '/var/lib/postgresql/data' and mount['Type'] == 'volume']
    if len(mounts) != 1:
        parser.error('Volume PostgreSQL restauré introuvable.')
    volume = mounts[0]['Name']

    # Le fichier persistant permet aussi de gérer Compose après le lancement.
    env_file.parent.mkdir(parents=True, exist_ok=True)
    if env_file.exists():
        values = dict(line.split('=', 1) for line in env_file.read_text().splitlines() if '=' in line)
        if values.get('RESTORE_DB_VOLUME') != volume or values.get('RESTORE_HTTP_PORT') != str(args.port):
            parser.error(f'Une autre configuration locale existe déjà pour ce conteneur dans {env_file}. '
                         'Réutiliser son port initial ou arrêter cette pile puis supprimer ce fichier '
                         'avant de changer sa base ou son port.')
    else:
        with env_file.open('x') as config:
            env_file.chmod(0o600)
            config.write(f'RESTORE_DB_VOLUME={volume}\nRESTORE_HTTP_PORT={args.port}\n'
                         f'RESTORE_SECRET_KEY={secrets.token_urlsafe(64)}\n')

    compose = ['docker', 'compose', '--project-name', project,
               '--env-file', str(env_file), '-f', str(ROOT / 'docker/compose.restore.yaml')]
    subprocess.run(compose + ['config', '--quiet'], cwd=ROOT, check=True)
    print('Arrêt du PostgreSQL de test avant de réutiliser son volume…', flush=True)
    subprocess.run(['docker', 'stop', container['Id']], check=True)
    print('Construction et démarrage de Café Dolbeau avec la base restaurée…', flush=True)
    try:
        subprocess.run(compose + ['up', '-d', '--build', '--wait', '--wait-timeout', '240'],
                       cwd=ROOT, check=True)
    finally:
        print(f'Journaux : {shlex.join(compose + ["logs", "--tail", "100"])}', flush=True)
        print(f'Arrêt : {shlex.join(compose + ["down"])}', flush=True)
    print(f'Application locale : http://localhost:{args.port}', flush=True)
    print('Connexion avec les comptes présents dans la sauvegarde.', flush=True)
    print('Le volume restauré est conservé ; ne pas redémarrer son ancien conteneur tant que cette pile tourne.',
          flush=True)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, subprocess.CalledProcessError, ValueError, KeyError) as error:
        raise SystemExit(f'Échec du démarrage local : {error}') from None
