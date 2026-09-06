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
    create-corpuses)
        oc exec -T \
            -e HISTORY_CORPUS="$HISTORY_CORPUS" \
            -e TEMPLATE_CORPUS="$TEMPLATE_CORPUS" \
            django /entrypoint python manage.py shell -c '
import os
from django.contrib.auth import get_user_model
from opencontractserver.corpuses.models import Corpus
from opencontractserver.corpuses.services import CorpusService

owner = get_user_model().objects.filter(is_superuser=True).order_by("pk").first()
if owner is None:
    raise RuntimeError("No superuser found; create one before initializing ContractBot corpuses.")

specs = [
    (os.environ["HISTORY_CORPUS"], "Contract History", "Historical contracts used by ContractBot"),
    (os.environ["TEMPLATE_CORPUS"], "Contract Templates", "Contract templates used by ContractBot"),
]

for slug, title, description in specs:
    corpus, created = Corpus.objects.get_or_create(
        slug=slug,
        creator=owner,
        defaults={
            "title": title,
            "description": description,
            "auto_branding_enabled": False,
        },
    )
    CorpusService.grant_creator_permissions(owner, corpus)
    print(f"CORPUS={slug} ID={corpus.pk} CREATED={created}")
'
        ;;
    publish-corpuses)
        oc exec -T \
            -e HISTORY_CORPUS="$HISTORY_CORPUS" \
            -e TEMPLATE_CORPUS="$TEMPLATE_CORPUS" \
            django /entrypoint python manage.py shell -c '
import os
from opencontractserver.corpuses.models import Corpus

slugs = [os.environ["HISTORY_CORPUS"], os.environ["TEMPLATE_CORPUS"]]
for slug in slugs:
    corpus = Corpus.objects.get(slug=slug)
    if not corpus.is_public:
        corpus.is_public = True
        corpus.save()
    print(f"PUBLIC={slug} ID={corpus.pk}")
'
        ;;
    mint-worker-key)
        history_id=$(oc exec -T \
            -e HISTORY_CORPUS="$HISTORY_CORPUS" \
            django /entrypoint python manage.py shell -c '
import os
from opencontractserver.corpuses.models import Corpus
print(Corpus.objects.get(slug=os.environ["HISTORY_CORPUS"]).pk)
' | tail -n 1 | tr -d '\r')

        oc exec -T django /entrypoint python manage.py mint_worker_token \
            --corpus "$history_id" \
            --worker-name "${WORKER_NAME:-contractbot-formal-ingest}" \
            --rate-limit "${WORKER_RATE_LIMIT:-30}" \
            --expires-days "${WORKER_EXPIRES_DAYS:-365}"
        ;;
    *)
        cat <<'EOF'
Usage: sh opencontracts-admin.sh <command>

Commands:
  create-corpuses   Create the configured history/template corpuses if absent
  publish-corpuses  Mark the configured history/template corpuses public
  mint-worker-key   Mint a WorkerKey bound to the history corpus
EOF
        exit 2
        ;;
esac
