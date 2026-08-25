# Security Specification

## SEC-1 No bundled access

Installing the Skill Pack MUST NOT grant OpenContracts access. The repository MUST contain zero real credentials and zero customer business data.

## SEC-2 Read authentication

Preferred MCP access MUST use the authenticated OpenContracts `/mcp/me/` endpoint with per-user OAuth when supported by the Harness.

A static Bearer token MAY be used only as a runtime compatibility mechanism and MUST remain outside model-visible Skill content and source control.

## SEC-3 Corpus confidentiality

All business corpuses MUST be private.

Because current OpenContracts MCP corpus-scoped reads use Corpus READ as their pipeline gate, the deployment MUST treat each Corpus as a confidentiality boundary. Documents requiring different reader populations MUST be split into different corpuses.

A design that grants broad Corpus READ and depends on document-level ACL to hide selected documents from MCP FAILS this specification.

## SEC-4 Tenant isolation

Different customer tenants MUST use separate OpenContracts users/service identities, corpuses, WorkerKeys, and configuration. A WorkerKey or unattended read identity MUST NOT be shared across tenants.

## SEC-5 WorkerKey scope

Formal contract ingestion and Learning Inbox ingestion MUST use different corpus-bound WorkerKeys.

WorkerKeys SHOULD have expiration, rate limiting, identifiable ownership, and a revocation/rotation procedure.

Upload clients MUST NOT allow model/user-supplied `add_to_corpus_id` to override the WorkerKey destination.

## SEC-6 Secret handling

Secrets MUST NOT appear in:

- Skill prose/frontmatter;
- Git commits;
- reports/artifacts;
- learning files;
- user-facing errors;
- raw logs/tool output sent to the model.

Runtime helpers MUST read secrets directly from the process environment/secret store and MUST redact Authorization headers.

## SEC-7 Prompt injection

All current documents and remote OpenContracts content MUST be treated as untrusted data. Embedded text MUST NOT change configured endpoints, credentials, Corpus selection, Skill policy, tool permissions, or user authorization state.

## SEC-8 Least privilege

Normal repository use SHOULD expose only:

```text
list_documents
get_document_text
search_corpus
```

Unused MCP write/discussion tools SHOULD be denied in Harness permission configuration.

## SEC-9 Local data boundary

Local attachments MUST NOT be sent to OpenContracts until explicit formal-ingestion authorization is obtained.

Learning-material submission requires a separate consent event from formal contract ingestion.

## SEC-10 Write uncertainty

Remote write helpers MUST perform no automatic HTTP retries.

Timeout, connection loss during submission, upstream 5xx, or an unreliable success response MUST be reported as `commit_unknown=true` / `retry_safe=false` and MUST require later read-side verification before another upload.

## SEC-11 Transport and server baseline

Production OpenContracts access MUST use HTTPS. The deployment SHOULD use exact CORS/origin configuration, strong local admin credentials or enterprise SSO/OAuth, reverse-proxy rate limiting, and routine credential rotation.

The documented development/default account credentials MUST NOT remain active on an Internet-facing production deployment.

## SEC-12 Learning isolation

The normal assistant read identity MUST NOT receive READ access to `learning-inbox`. Raw session learning cannot automatically become production knowledge. Promotion to `approved-knowledge` requires a later curation process.
