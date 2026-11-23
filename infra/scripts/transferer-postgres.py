#!/usr/bin/env python3
"""Exporter PostgreSQL local et l'importer sur EC2, directement par SSH."""
import argparse
import hashlib
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True, help='Destination SSH : ubuntu@IP_EC2')
    parser.add_argument('--confirm-host', required=True,
                        help='Répéter exactement --host pour autoriser le remplacement de sa base.')
    parser.add_argument('--identity', help='Chemin de la clé privée SSH (sinon agent/config SSH).')
    parser.add_argument('--port', type=int, default=22)
    parser.add_argument('--env-file', default='.env', help='Configuration Compose locale.')
    parser.add_argument('-f', '--compose-file', action='append', help='Fichier Compose local, répétable.')
    parser.add_argument('--project-name', help='Nom du projet Compose local si différent du défaut.')
    source = parser.add_mutually_exclusive_group()
    source.add_argument('--pg-service', help='Base hors Docker : service libpq local, avec .pgpass.')
    source.add_argument('--container', help='Conteneur PostgreSQL source, par exemple BLA (sans Compose).')
    args = parser.parse_args(argv)
    if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.@:-]*', args.host):
        parser.error('Destination SSH invalide ; utiliser un nom DNS, une IPv4 ou un alias SSH.')
    if args.confirm_host != args.host:
        parser.error('--confirm-host doit être identique à --host.')
    if not 1 <= args.port <= 65535:
        parser.error('Port SSH invalide.')
    if args.pg_service and not re.fullmatch(r'[A-Za-z0-9_.-]+', args.pg_service):
        parser.error('Nom du service PostgreSQL invalide.')
    if args.container:
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', args.container):
            parser.error('Nom du conteneur PostgreSQL invalide.')
        if args.project_name or args.compose_file or args.env_file != '.env':
            parser.error('--container ne peut pas être combiné avec --project-name, -f ou --env-file.')
    return args


def dump_command(args):
    if args.pg_service:
        return ['pg_dump', '--no-password', '--format=custom', '--no-owner', '--no-acl',
                '--dbname', f'service={args.pg_service}']
    if args.container:
        return ['docker', 'exec', args.container, 'sh', '-ec',
                'exec pg_dump --no-password --format=custom --no-owner --no-acl '
                '-U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-postgres}"']
    command = ['docker', 'compose', '--env-file', args.env_file]
    for filename in args.compose_file or ['docker/compose.yaml']:
        command += ['-f', filename]
    if args.project_name:
        command += ['--project-name', args.project_name]
    return command + ['exec', '-T', 'db', 'sh', '-ec',
                      'exec pg_dump --no-password --format=custom --no-owner --no-acl '
                      '-U "$POSTGRES_USER" -d "$POSTGRES_DB"']


def ssh_command(args):
    command = ['ssh', '-T', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=accept-new',
               '-o', 'ConnectTimeout=15', '-p', str(args.port)]
    if args.identity:
        command += ['-i', args.identity]
    return command + [args.host]


def main(argv=None):
    args = arguments(argv)
    ssh = ssh_command(args)
    # Vérifier l'accès avant de lire la base locale. Aucun changement distant.
    subprocess.run(ssh + ['sudo -n test -f /opt/cafedolbeau/current/compose.yaml'], check=True)
    with tempfile.TemporaryDirectory(prefix='cafedolbeau-transfert-') as folder:
        archive = Path(folder) / 'source.dump'
        print('Export cohérent de la base locale…', flush=True)
        with archive.open('xb') as output:
            archive.chmod(0o600)
            subprocess.run(dump_command(args), cwd=ROOT, stdout=output, check=True)
        with archive.open('rb') as source:
            checksum = hashlib.file_digest(source, 'sha256').hexdigest()
        script = Path(__file__).with_name('importer-postgres.sh').read_text()
        remote = shlex.join(['sudo', '-n', 'bash', '-c', script, 'importer-postgres', checksum])
        print(f'Transfert direct vers {args.host} et import (interruption du site)…', flush=True)
        with archive.open('rb') as source:
            subprocess.run(ssh + [remote], stdin=source, check=True)
    print('Transfert terminé ; le fichier temporaire local a été supprimé.')


if __name__ == '__main__':
    try:
        main()
    except (OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(f'Transfert interrompu : {error}. Consulter les messages du serveur.') from None
