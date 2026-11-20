#!/usr/bin/env python3
"""Suivre un déploiement GitHub Actions puis afficher son résumé dans le terminal."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
PREFIXES = ('Version : ', 'EC2 : ', 'DNS public EC2 : ', 'Application : ',
            'Santé HTTP : ', 'Transfert PostgreSQL depuis votre ordinateur ',
            'python3 infra/scripts/transferer-postgres.py ')


def summary_lines(log):
    """Extraire seulement les sorties du résumé, sans les commandes ni autres logs."""
    lines = []
    for line in log.splitlines():
        fields = line.split('\t', 2)
        if len(fields) != 3 or not fields[1].startswith('DNS EC2 : '):
            continue
        content = re.sub(r'^\S+Z\s+', '', fields[2])
        if content.startswith(PREFIXES):
            lines.append(content)
    return lines


def gh(*args, **kwargs):
    return subprocess.run(['gh', *args], cwd=ROOT, **kwargs)


def launch(ref):
    # Le titre unique évite de suivre le déploiement déclenché par un autre utilisateur.
    token = uuid.uuid4().hex
    title = f'Déployer sur EC2 · {ref} · {token}'
    gh('workflow', 'run', 'deploy.yml', '--ref', 'main', '-f', f'ref={ref}',
       '-f', f'suivi_id={token}', check=True)
    print(f'Déploiement demandé pour {ref}. Recherche de son exécution…', flush=True)
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        result = gh('run', 'list', '--workflow', 'deploy.yml', '--branch', 'main',
                    '--event', 'workflow_dispatch', '--limit', '50',
                    '--json', 'databaseId,displayTitle', capture_output=True,
                    text=True, check=True)
        for run in json.loads(result.stdout):
            if run['displayTitle'] == title:
                return run['databaseId']
        time.sleep(2)
    raise SystemExit('Pipeline déclenché, mais son ID reste introuvable après 120 secondes. '
                     f'Consultez gh run list avant de relancer. Identifiant de suivi : {token}')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id', nargs='?', type=int,
                        help='ID GitHub Actions ; par défaut, le dernier déploiement de main.')
    parser.add_argument('--lancer', action='store_true',
                        help='Déclencher un nouveau déploiement puis suivre cette exécution.')
    parser.add_argument('--ref', help='Branche, tag ou SHA à déployer avec --lancer (défaut : main).')
    args = parser.parse_args(argv)
    if args.lancer and args.run_id is not None:
        parser.error('--lancer ne peut pas être combiné avec un ID existant.')
    if args.ref is not None and not args.lancer:
        parser.error('--ref nécessite --lancer.')
    run_id = args.run_id
    if args.lancer:
        run_id = launch(args.ref or 'main')
    if run_id is None:
        result = gh('run', 'list', '--workflow', 'deploy.yml', '--branch', 'main',
                    '--limit', '1', '--json', 'databaseId', capture_output=True,
                    text=True, check=True)
        runs = json.loads(result.stdout)
        if not runs:
            raise SystemExit('Aucun déploiement de main trouvé.')
        run_id = runs[0]['databaseId']
    watched = gh('run', 'watch', str(run_id), '--exit-status')
    result = gh('run', 'view', str(run_id), '--log', capture_output=True,
                text=True, errors='replace', check=True)
    lines = summary_lines(result.stdout)
    if lines:
        print('\nRésumé du déploiement\n', flush=True)
        print('\n\n'.join(lines), flush=True)
    else:
        print('\nAucun résumé disponible pour cette exécution.', flush=True)
    if watched.returncode:
        print(f'Consulter les erreurs : gh run view {run_id} --log-failed', flush=True)
    return watched.returncode


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, subprocess.CalledProcessError, ValueError) as error:
        raise SystemExit(f'Erreur de déploiement ou de suivi : {error}') from None
