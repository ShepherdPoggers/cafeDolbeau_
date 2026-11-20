#!/bin/bash
set -euo pipefail
umask 077
cd "$(dirname "$0")"
exec 9>/opt/cafedolbeau/deploy.lock
flock -n 9 || { echo 'Un déploiement est déjà en cours.'; exit 1; }
trap 'rm -f images.tar.gz old-config.json new-config.json' EXIT
sha256sum --check SHA256SUMS
docker load --input images.tar.gz

compose=(docker compose --project-name cafedolbeau_ --env-file "$PWD/.env" -f "$PWD/compose.yaml")

# Ne jamais modifier silencieusement les identifiants d'une base existante.
if [ -f /opt/cafedolbeau/current/.env ]; then
  "${compose[@]}" config --format json > new-config.json
  docker compose --project-name cafedolbeau_ --env-file /opt/cafedolbeau/current/.env \
    -f /opt/cafedolbeau/current/compose.yaml config --format json > old-config.json
  python3 - <<'PY'
import json
from pathlib import Path
old = json.loads(Path('old-config.json').read_text())['services']
new = json.loads(Path('new-config.json').read_text())['services']
for service, keys in [('secrets', ['SECRET_KEY', 'POSTGRES_PASSWORD']), ('db', ['POSTGRES_DB', 'POSTGRES_USER'])]:
    if any(old[service]['environment'].get(key) != new[service]['environment'].get(key) for key in keys):
        raise SystemExit('Changement des identifiants persistants refusé ; rotation manuelle requise.')
PY
  rm -f old-config.json new-config.json
fi

# Télécharger toutes les dépendances avant l'interruption de service.
"${compose[@]}" pull db cloudflared
"${compose[@]}" stop cloudflared proxy app
"${compose[@]}" run --rm --no-deps secrets
"${compose[@]}" up -d --no-deps --wait --wait-timeout 180 db
"${compose[@]}" run --rm --no-deps init
"${compose[@]}" up -d --no-deps --wait --wait-timeout 240 app
"${compose[@]}" up -d --no-deps --wait --wait-timeout 120 proxy cloudflared

# cloudflared n'inclut pas de shell : son endpoint de métriques fournit la readiness.
for attempt in $(seq 1 60); do
  if curl --fail --silent --max-time 3 http://127.0.0.1:2000/ready >/dev/null; then break; fi
  if [ "$attempt" -eq 60 ]; then echo 'Le tunnel Cloudflare ne devient pas prêt.'; exit 1; fi
  sleep 5
done
curl --fail --silent --show-error --retry 12 --retry-all-errors --retry-delay 5 \
  --max-time 10 http://127.0.0.1/healthz >/dev/null

release="$PWD"
ln -sfn "$release" /opt/cafedolbeau/current.new
mv -Tf /opt/cafedolbeau/current.new /opt/cafedolbeau/current
rm -f images.tar.gz old-config.json new-config.json
# Les versions arrêtées ne contiennent plus d'archives ni de copies du .env.
find /opt/cafedolbeau/releases -mindepth 1 -maxdepth 1 -type d ! -path "$release" -exec rm -rf -- {} +
docker image prune -f >/dev/null
# Les anciennes images étiquetées ne sont pas supprimées par image prune.
current_image=$("${compose[@]}" config --images | awk '/^cafe-dolbeau-app:/ && !seen++')
current_tag=${current_image#cafe-dolbeau-app:}
while read -r image; do
  case "$image" in
    cafe-dolbeau-app:"$current_tag"|cafe-dolbeau-proxy:"$current_tag") continue ;;
    cafe-dolbeau-app:*|cafe-dolbeau-proxy:*) docker image rm "$image" >/dev/null 2>&1 || true ;;
  esac
done < <(docker image ls --format '{{.Repository}}:{{.Tag}}')
"${compose[@]}" ps
