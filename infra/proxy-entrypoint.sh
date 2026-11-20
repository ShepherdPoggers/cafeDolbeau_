#!/bin/sh
set -eu
: "${PUBLIC_DOMAIN:?PUBLIC_DOMAIN requis}"
envsubst '${PUBLIC_DOMAIN}' < /etc/nginx/nginx.conf.template > /tmp/nginx.conf
exec nginx -c /tmp/nginx.conf -g 'daemon off;'
