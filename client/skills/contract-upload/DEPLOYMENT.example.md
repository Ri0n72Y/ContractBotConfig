# Contract Upload Deployment

The server preparation script generates `DEPLOYMENT.md` from the current OpenContracts host configuration.

Example:

```text
IMPORT_URL=http://10.10.20.15/api/imports/documents/
```

Clients do not send an Authorization header. The server-side Caddy gateway injects the corpus-bound WorkerKey.
