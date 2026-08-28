#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ENV_FILE=${ENV_FILE:-"$SCRIPT_DIR/.env"}

set -a
. "$ENV_FILE"
set +a

oc() {
    docker compose -f "$OPENCONTRACTS_LOCAL_YML" "$@"
}

case "${1:-}" in
    publish-corpuses)
        oc exec -T \
            -e HISTORY_CORPUS="$HISTORY_CORPUS" \
            -e TEMPLATE_CORPUS="$TEMPLATE_CORPUS" \
            django python manage.py shell -c '
import os
from opencontractserver.corpuses.models import Corpus
slugs = [os.environ["HISTORY_CORPUS"], os.environ["TEMPLATE_CORPUS"]]
Corpus.objects.filter(slug__in=slugs).update(is_public=True)
print("PUBLIC=" + ",".join(slugs))
'
        ;;
    mint-worker-key)
        history_id=$(oc exec -T \
            -e HISTORY_CORPUS="$HISTORY_CORPUS" \
            django python manage.py shell -c '
import os
from opencontractserver.corpuses.models import Corpus
print(Corpus.objects.get(slug=os.environ["HISTORY_CORPUS"]).pk)
' | tail -n 1 | tr -d '\r')

        oc exec -T django python manage.py mint_worker_token \
            --corpus "$history_id" \
            --worker-name "${WORKER_NAME:-contractbot-formal-ingest}" \
            --rate-limit "${WORKER_RATE_LIMIT:-30}" \
            --expires-days "${WORKER_EXPIRES_DAYS:-365}"
        ;;
    *)
        cat <<'EOF'
Usage: sh opencontracts-admin.sh <command>

Commands:
  publish-corpuses  Set contracts and contract-templates public
  mint-worker-key   Mint a WorkerKey bound to contracts
EOF
        exit 2
        ;;
esac
