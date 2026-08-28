#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
DEPLOY_DIR=$(dirname "$SCRIPT_DIR")
ENV_FILE=${ENV_FILE:-"$DEPLOY_DIR/.env"}
COMPOSE_FILE="$SCRIPT_DIR/compose.yml"

set -a
. "$ENV_FILE"
set +a

compose() {
    docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

case "${1:-}" in
    up)
        compose up -d
        ;;
    export-ca)
        mkdir -p "$(dirname "$CADDY_CA_OUTPUT")"
        compose cp caddy:/data/caddy/pki/authorities/local/root.crt "$CADDY_CA_OUTPUT"
        echo "$CADDY_CA_OUTPUT"
        ;;
    logs)
        compose logs --tail=200 -f caddy
        ;;
    down)
        compose down
        ;;
    *)
        cat <<'EOF'
Usage: sh manage.sh <command>

Commands:
  up          Start Caddy
  export-ca   Export Caddy internal root CA to CADDY_CA_OUTPUT
  logs        Follow Caddy logs
  down        Stop Caddy
EOF
        exit 2
        ;;
esac
