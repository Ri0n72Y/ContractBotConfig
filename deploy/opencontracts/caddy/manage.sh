#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
DEPLOY_DIR=$(dirname "$SCRIPT_DIR")
ENV_FILE=${ENV_FILE:-"$DEPLOY_DIR/.env"}
COMPOSE_FILE="$SCRIPT_DIR/compose.yml"
RUNTIME_DIR="$DEPLOY_DIR/runtime"

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

[ -f "$ENV_FILE" ] || fail "missing $ENV_FILE; copy $DEPLOY_DIR/.env.example to .env first"

set -a
. "$ENV_FILE"
set +a

: "${OPENCONTRACTS_LAN_IP:?set OPENCONTRACTS_LAN_IP in $ENV_FILE}"
: "${OPENCONTRACTS_DOCKER_NETWORK:?set OPENCONTRACTS_DOCKER_NETWORK in $ENV_FILE}"

compose() {
    docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

check() {
    command -v docker >/dev/null 2>&1 || fail "docker is not installed"
    docker compose version >/dev/null
    docker network inspect "$OPENCONTRACTS_DOCKER_NETWORK" >/dev/null 2>&1 || \
        fail "Docker network '$OPENCONTRACTS_DOCKER_NETWORK' does not exist; run ../opencontracts-admin.sh network"
    compose config >/dev/null
}

case "${1:-}" in
    check)
        check
        echo "Caddy deployment configuration is valid."
        ;;
    up)
        check
        compose up -d
        compose exec -T caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
        echo "Caddy is running at https://$OPENCONTRACTS_LAN_IP"
        ;;
    export-ca)
        check
        mkdir -p "$RUNTIME_DIR"
        compose cp caddy:/data/caddy/pki/authorities/local/root.crt "$RUNTIME_DIR/caddy-root.crt"
        chmod 0644 "$RUNTIME_DIR/caddy-root.crt" 2>/dev/null || true
        echo "$RUNTIME_DIR/caddy-root.crt"
        ;;
    status)
        check
        compose ps
        ;;
    logs)
        check
        compose logs --tail=200 -f caddy
        ;;
    down)
        check
        compose down
        ;;
    *)
        cat <<'EOF'
Usage: ./manage.sh <command>

Commands:
  check       Validate Docker, external network and Compose configuration
  up          Start Caddy and validate the loaded Caddyfile
  export-ca   Copy Caddy's internal root CA to ../runtime/caddy-root.crt
  status      Show Caddy Compose status
  logs        Follow Caddy logs
  down        Stop Caddy without deleting its named CA/config volumes
EOF
        exit 2
        ;;
esac
