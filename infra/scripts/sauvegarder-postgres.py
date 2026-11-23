#!/usr/bin/env python3
"""Sauvegarder PostgreSQL sur EC2 et télécharger une copie vérifiée par SSH."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]

REMOTE_BACKUP = r'''set -euo pipefail
umask 077
exec 9>/opt/cafedolbeau/deploy.lock
flock -n 9 || { echo 'Un déploiement, import ou une sauvegarde est en cours.' >&2; exit 1; }
cd /opt/cafedolbeau/current
compose=(docker compose --project-name cafedolbeau_ --env-file "$PWD/.env" -f "$PWD/compose.yaml")
install -d -m 0700 /opt/cafedolbeau/backups
folder=$(mktemp -d /opt/cafedolbeau/backups/export-XXXXXXXX)
trap 'rm -f "$folder/production.dump.part"' EXIT
"${compose[@]}" exec -T db sh -ec \
  'exec pg_dump --no-password --format=custom --no-owner --no-acl -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  < /dev/null > "$folder/production.dump.part"
"${compose[@]}" exec -T db pg_restore --list < "$folder/production.dump.part" > /dev/null
mv "$folder/production.dump.part" "$folder/production.dump"
python3 - "$folder/production.dump" <<'PY'
import hashlib, json, sys
from pathlib import Path
path = Path(sys.argv[1])
with path.open('rb') as archive:
    checksum = hashlib.file_digest(archive, 'sha256').hexdigest()
print(json.dumps({'path': str(path), 'sha256': checksum, 'bytes': path.stat().st_size}))
PY
'''


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True, help='Serveur SSH : ubuntu@DNS_EC2.')
    parser.add_argument('--identity', help='Clé privée SSH ; sinon agent/config SSH.')
    parser.add_argument('--port', type=int, default=22)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'backups/postgres',
                        help='Dossier local de sauvegarde (défaut : backups/postgres du dépôt).')
    args = parser.parse_args(argv)
    if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.@:-]*', args.host):
        parser.error('Hôte SSH invalide ; utiliser ubuntu@DNS_EC2, une IPv4 ou un alias SSH.')
    if not 1 <= args.port <= 65535:
        parser.error('Port SSH invalide.')
    return args


def main(argv=None):
    args = arguments(argv)
    ssh = ['ssh', '-T', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=accept-new',
           '-o', 'ConnectTimeout=15', '-p', str(args.port)]
    if args.identity:
        ssh += ['-i', str(Path(args.identity).expanduser())]
    ssh.append(args.host)
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

    print('Création et validation de la sauvegarde sur EC2…', flush=True)
    result = subprocess.run(ssh + ['sudo -n bash -s'], input=REMOTE_BACKUP,
                            text=True, stdout=subprocess.PIPE, check=True)
    metadata = json.loads(result.stdout)
    remote_path = metadata['path']
    if not re.fullmatch(r'/opt/cafedolbeau/backups/export-[A-Za-z0-9]+/production\.dump', remote_path):
        raise ValueError('Chemin de sauvegarde distant inattendu.')
    if not re.fullmatch(r'[a-f0-9]{64}', metadata['sha256']) or metadata['bytes'] <= 0:
        raise ValueError('Empreinte ou taille de sauvegarde distante invalide.')
    print(f'Sauvegarde distante conservée : {remote_path}', flush=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    name = f"cafe-production-{stamp}-{Path(remote_path).parent.name}.dump"
    destination = output_dir / name
    # Le fichier partiel reste privé et n'est publié qu'après vérification.
    with tempfile.TemporaryDirectory(prefix='.sauvegarde-', dir=output_dir) as directory:
        partial = Path(directory) / 'production.dump'
        with partial.open('xb') as archive:
            partial.chmod(0o600)
            subprocess.run(ssh + ['sudo -n cat -- ' + shlex.quote(remote_path)],
                           stdout=archive, check=True)
        with partial.open('rb') as archive:
            checksum = hashlib.file_digest(archive, 'sha256').hexdigest()
        if partial.stat().st_size != metadata['bytes'] or checksum != metadata['sha256']:
            raise ValueError('Copie locale invalide : la taille ou le SHA-256 diffère du serveur.')
        # Lien atomique : refuse d'écraser une sauvegarde existante.
        os.link(partial, destination)
    print(f'Sauvegarde téléchargée et vérifiée : {destination}')
    print(f"Taille : {metadata['bytes']} octets ; SHA-256 : {checksum}")
    print('A8 : il reste à restaurer cette archive dans une base de test séparée.')
    return destination


if __name__ == '__main__':
    try:
        main()
    except (subprocess.CalledProcessError, OSError, ValueError, KeyError, TypeError) as error:
        raise SystemExit(f'Échec de la sauvegarde : {error}') from error
