#!/usr/bin/env python3
"""Restaurer un .dump dans un nouveau PostgreSQL local isolé pour vérifier A8."""
import argparse
from pathlib import Path
import re
import shlex
import subprocess
import time

IMAGE = 'postgres:17.9-bookworm'


def docker(*args, **kwargs):
    return subprocess.run(['docker', *args], **kwargs)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dump', type=Path, help='Archive produite par sauvegarder-postgres.py.')
    parser.add_argument('--container', default='cafe-restauration-a8',
                        help='Nom du nouveau conteneur (défaut : cafe-restauration-a8).')
    args = parser.parse_args(argv)
    archive_path = args.dump.expanduser().resolve()
    if not archive_path.is_file() or archive_path.stat().st_size == 0:
        parser.error('Le fichier de sauvegarde doit exister et ne pas être vide.')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', args.container):
        parser.error('Nom de conteneur invalide.')
    # Un dump personnalisé PostgreSQL commence par PGDMP.
    with archive_path.open('rb') as archive:
        if archive.read(5) != b'PGDMP':
            parser.error('Archive attendue au format personnalisé pg_dump (.dump).')

    # Une erreur du démon doit être distinguée d'une liste vide.
    result = docker('container', 'ls', '-a', '--format', '{{.Names}}',
                    capture_output=True, text=True, check=True)
    if args.container in result.stdout.splitlines():
        parser.error(f'Le conteneur {args.container} existe déjà. '
                     'Choisir un autre nom avec --container pour préserver ses données.')

    print(f'Archive : {archive_path}', flush=True)
    print(f'Création de {args.container} : PostgreSQL local, sans réseau ni port publié…', flush=True)
    docker('run', '-d', '--name', args.container, '--network', 'none',
           '-e', 'POSTGRES_HOST_AUTH_METHOD=trust', '-e', 'POSTGRES_DB=cafe_restore',
           IMAGE, check=True)
    cleanup = shlex.join(['docker', 'rm', '-fv', args.container])
    try:
        for _ in range(30):
            ready = docker('exec', args.container, 'pg_isready', '-U', 'postgres', '-d', 'cafe_restore',
                           capture_output=True)
            if ready.returncode == 0:
                break
            time.sleep(2)
        else:
            raise RuntimeError('PostgreSQL de test ne devient pas prêt après environ 60 secondes.')

        print('Restauration dans cafe_restore…', flush=True)
        with archive_path.open('rb') as archive:
            docker('exec', '-i', args.container, 'pg_restore', '--exit-on-error',
                   '--single-transaction', '--no-owner', '--no-acl',
                   '-U', 'postgres', '-d', 'cafe_restore', stdin=archive, check=True)
        print('Vérification des tables et des comptages…', flush=True)
        docker('exec', args.container, 'psql', '-v', 'ON_ERROR_STOP=1',
               '-U', 'postgres', '-d', 'cafe_restore', '-c', r'\dt',
               '-c', 'SELECT COUNT(*) AS clients FROM "CafeDolbeau_client";',
               '-c', 'SELECT COUNT(*) AS transactions FROM "CafeDolbeau_transactioncafe";', check=True)
        print('Restauration et vérifications réussies. Comparer les comptages avec la sauvegarde de production.',
              flush=True)
        print('Conserver cette sortie comme preuve A8.', flush=True)
    finally:
        print(f'Conteneur de test conservé : {args.container}', flush=True)
        print(f'Journaux : docker logs {args.container}', flush=True)
        print(f'Après conservation des preuves, nettoyage : {cleanup}', flush=True)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, subprocess.CalledProcessError, RuntimeError) as error:
        raise SystemExit(f'Échec de la restauration de test : {error}') from None
