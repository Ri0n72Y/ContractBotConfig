#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ENV_FILE=${ENV_FILE:-"$SCRIPT_DIR/.env"}

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

[ -f "$ENV_FILE" ] || fail "missing $ENV_FILE; copy $SCRIPT_DIR/.env.example to .env first"

set -a
. "$ENV_FILE"
set +a

: "${OPENCONTRACTS_DIR:?set OPENCONTRACTS_DIR in $ENV_FILE}"

LOCAL_YML="$OPENCONTRACTS_DIR/local.yml"
[ -f "$LOCAL_YML" ] || fail "OpenContracts local.yml not found: $LOCAL_YML"

oc() {
    docker compose -f "$LOCAL_YML" "$@"
}

require_running_django() {
    django_id=$(oc ps -q django)
    [ -n "$django_id" ] || fail "OpenContracts django is not running; start the upstream local.yml first"
    printf '%s' "$django_id"
}

case "${1:-}" in
    status)
        oc ps
        ;;
    network)
        django_id=$(require_running_django)
        docker inspect "$django_id" --format '{{range $name, $_ := .NetworkSettings.Networks}}{{$name}}{{"\n"}}{{end}}'
        ;;
    corpuses)
        : "${HISTORY_CORPUS:?set HISTORY_CORPUS in $ENV_FILE}"
        : "${TEMPLATE_CORPUS:?set TEMPLATE_CORPUS in $ENV_FILE}"
        require_running_django >/dev/null
        oc exec -T \
            -e HISTORY_CORPUS="$HISTORY_CORPUS" \
            -e TEMPLATE_CORPUS="$TEMPLATE_CORPUS" \
            django python manage.py shell -c '
import os
from opencontractserver.corpuses.models import Corpus
slugs = [os.environ["HISTORY_CORPUS"], os.environ["TEMPLATE_CORPUS"]]
qs = Corpus.objects.filter(slug__in=slugs)
found = set(qs.values_list("slug", flat=True))
missing = [slug for slug in slugs if slug not in found]
print("FOUND=" + ",".join(sorted(found)))
print("MISSING=" + ",".join(missing))
if missing:
    raise SystemExit(3)
qs.update(is_public=True)
print("PUBLIC=OK")
'
        ;;
    mint-worker-key)
        : "${HISTORY_CORPUS:?set HISTORY_CORPUS in $ENV_FILE}"
        : "${WORKER_NAME:=contractbot-formal-ingest}"
        : "${WORKER_RATE_LIMIT:=30}"
        : "${WORKER_EXPIRES_DAYS:=365}"
        require_running_django >/dev/null

        history_id=$(oc exec -T \
            -e HISTORY_CORPUS="$HISTORY_CORPUS" \
            django python manage.py shell -c '
import os
from opencontractserver.corpuses.models import Corpus
print(Corpus.objects.get(slug=os.environ["HISTORY_CORPUS"]).pk)
' | tail -n 1 | tr -d '\r')

        [ -n "$history_id" ] || fail "could not resolve history Corpus id"
        echo "WARNING: the next command prints the WorkerKey plaintext once. Store it in the Agent/Harness secret environment; do not copy it into .env or Git." >&2
        oc exec -T django python manage.py mint_worker_token \
            --corpus "$history_id" \
            --worker-name "$WORKER_NAME" \
            --rate-limit "$WORKER_RATE_LIMIT" \
            --expires-days "$WORKER_EXPIRES_DAYS"
        ;;
    *)
        cat <<'EOF'
Usage: sh opencontracts-admin.sh <command>

Commands:
  status           Show the existing upstream OpenContracts local.yml services
  network          Print Docker network(s) attached to the running django service
  corpuses         Validate history/template Corpus slugs and set both public
  mint-worker-key  Mint a WorkerKey bound to the history Corpus

This script does not edit local.yml or OpenContracts source files.
EOF
        exit 2
        ;;
esac
