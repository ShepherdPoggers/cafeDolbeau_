#!/bin/bash
# Appelé exclusivement par transferer-postgres.py ; l'archive arrive sur stdin.
set -euo pipefail
umask 077
[[ ${1:-} =~ ^[a-f0-9]{64}$ ]] || { echo 'SHA256 manquant ou invalide.' >&2; exit 1; }
exec 9>/opt/cafedolbeau/deploy.lock
flock -n 9 || { echo 'Un déploiement ou transfert est déjà en cours.' >&2; exit 1; }
cd /opt/cafedolbeau/current
compose=(docker compose --project-name cafedolbeau_ --env-file "$PWD/.env" -f "$PWD/compose.yaml")
install -d -m 0700 /opt/cafedolbeau/backups
folder=$(mktemp -d /opt/cafedolbeau/backups/import-XXXXXXXX)
stopped=false
success=false
cleanup() {
    rm -f "$folder/source.dump"
    if [ "$stopped" = true ] && [ "$success" != true ]; then
        "${compose[@]}" stop cloudflared proxy app || true
        echo "Import interrompu ; site maintenu arrêté. Sauvegarde éventuelle : $folder/avant-import.dump" >&2
        echo 'Examiner la base et les journaux avant de redémarrer app, proxy et cloudflared.' >&2
    fi
}
trap cleanup EXIT
cat > "$folder/source.dump"
printf '%s  %s\n' "$1" "$folder/source.dump" | sha256sum --check --status
# Détecter une archive invalide/incompatible avant d'arrêter le site.
"${compose[@]}" exec -T db pg_restore --list < "$folder/source.dump" > /dev/null
echo 'Arrêt du site et sauvegarde de la base distante…'
stopped=true
"${compose[@]}" stop cloudflared proxy app
"${compose[@]}" exec -T db sh -ec \
    'exec pg_dump --no-password --format=custom --no-owner --no-acl -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
    > "$folder/avant-import.dump"
"${compose[@]}" exec -T db pg_restore --list < "$folder/avant-import.dump" > /dev/null
echo "Sauvegarde conservée sur EC2 : $folder/avant-import.dump"
# Une erreur SQL annule toute la restauration. Aucun mot de passe dans la commande.
"${compose[@]}" exec -T db sh -ec \
    'exec pg_restore --no-password --clean --if-exists --single-transaction --no-owner --no-acl -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
    < "$folder/source.dump"
# Ne pas ouvrir un site dont le code attend des migrations absentes de l'import.
"${compose[@]}" run --rm --no-deps app python src/manage.py migrate --check --noinput
"${compose[@]}" up -d --no-deps --wait --wait-timeout 240 app
"${compose[@]}" up -d --no-deps --wait --wait-timeout 120 proxy
curl --fail --silent --show-error --max-time 15 http://127.0.0.1/healthz > /dev/null
"${compose[@]}" up -d --no-deps cloudflared
success=true
echo 'Import terminé ; application saine et tunnel redémarré.'
