#!/bin/sh
set -eu
: "${PUBLIC_SCHEME:=http}"
export PUBLIC_SCHEME
case "$PUBLIC_SCHEME" in
    http|https) ;;
    *) echo 'PUBLIC_SCHEME doit être http ou https.' >&2; exit 1 ;;
esac
# Ne remplacer que cette variable, en conservant les variables propres à nginx.
envsubst '${PUBLIC_SCHEME}' < /etc/nginx/nginx.conf.template > /tmp/nginx.conf
exec nginx -c /tmp/nginx.conf -g 'daemon off;'
