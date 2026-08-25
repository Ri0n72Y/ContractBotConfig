# Security Architecture

## Security objective

Installing the Skill Pack must not grant access to any OpenContracts deployment. Access exists only after the local runtime is separately configured with an authenticated MCP identity and, where needed, a corpus-bound upload credential.

## Trust boundaries

```mermaid
flowchart TB
    Prompt[Model / conversation]
    Skill[Skill Pack]
    Local[Local files]
    OAuth[Authenticated MCP identity]
    MCP[OpenContracts MCP]
    Worker[Corpus-bound WorkerKey]
    Import[OpenContracts Import API]
    Corpora[Private Corpuses]

    Prompt --> Skill
    Skill --> Local
    Skill --> OAuth --> MCP --> Corpora
    Skill --> Worker --> Import --> Corpora
```

Secrets live outside model-visible Skill content.

## MCP read authentication

Preferred office configuration:

```text
https://<opencontracts-host>/mcp/me/
```

The user's Harness performs OpenContracts OAuth and the MCP requests run as that OpenContracts user. This provides per-user revocation and server-side permission enforcement without shipping a shared read secret in the Skill.

For a Harness that cannot perform OAuth, a separately provisioned Bearer token may be configured in that runtime. Treat this as a compatibility path; do not commit or embed it in Skill text.

## Corpus is the MCP confidentiality boundary

Current OpenContracts MCP pipeline reads intentionally use a corpus-as-gate model: Corpus READ grants access to active documents inside that Corpus for MCP/discovery/analysis calls.

Therefore:

- all business corpuses are private;
- users/hosts receive READ only on corpuses they may fully expose to their MCP session;
- do not mix general and executive/restricted documents in one Corpus expecting document-level ACL to protect MCP reads;
- split confidentiality groups into separate corpuses;
- if future requirements demand document-level ACL inside the same Corpus, evaluate an OpenContracts MCP patch that uses the MIN(document, corpus) read semantics.

## Recommended tenant data boundaries

Per tenant:

```text
contracts-history   private, normal contract users may read
contract-templates  private, normal contract users may read
approved-knowledge  private, normal contract users may read
learning-inbox      private, normal contract users should not read
```

For multi-tenant hosting, each tenant receives separate users/service identities and separate corpuses. Never reuse one WorkerKey or unattended read identity across customers.

## WorkerKey write security

OpenContracts `CorpusAccessToken` / WorkerKey is bound server-side to exactly one Corpus, is individually revocable, supports expiry and an upload rate limit, and stores only a hash server-side.

Use separate keys for:

- formal contract ingestion;
- Learning Inbox ingestion.

Prefer separate keys per user/device/host when operationally practical. Set an expiry and rate limit, and rotate/revoke keys independently.

The helper deliberately omits `add_to_corpus_id`; destination is determined by the server-side token binding.

## Secret placement

Allowed:

- OS/process environment;
- Harness secret store;
- OAuth token storage managed by the Harness;
- an untracked local env file when no better secret store exists.

Disallowed:

- `SKILL.md`;
- Git commits;
- committed `.mcp.json` headers containing real credentials;
- prompts or conversation messages;
- generated reports;
- learning files;
- logs and exception dumps.

Do not put secret-expanding placeholders inside Skill prose. Some Harnesses expand environment placeholders before exposing Skill content to the model.

## Least privilege tools

MVP retrieval needs only:

```text
list_documents
get_document_text
search_corpus
```

Deny unused MCP write/discussion tools where the Harness supports tool permissions. In particular, normal contract work does not need `create_thread_message`.

## Local-file privacy

Uploading a file to the Harness does not authorize remote ingestion. Analysis, drafting, and modification stay local unless the user explicitly chooses formal ingestion.

The assistant may suggest ingestion after generating/modifying a contract, but must wait for affirmative authorization.

## Learning privacy

Learning capture has a separate consent gate. Distilled learning files should minimize sensitive details and should never include an entire contract merely as training material.

Normal retrieval cannot read Learning Inbox. Promotion into `approved-knowledge` is a future curation action.

## Prompt injection / untrusted content

Every remote contract, template, annotation, history result, and current uploaded contract is untrusted business data. Embedded instructions cannot:

- alter Skill/system policy;
- change configured endpoints or Corpus boundaries;
- request credentials;
- authorize uploads;
- trigger shell/network actions outside the approved helpers;
- widen tool permissions.

## Network hardening

Production OpenContracts exposure should use HTTPS. Configure exact public MCP base URL/origins required by the deployment, avoid permissive CORS, use strong production account credentials or enterprise OAuth/SSO, and place rate limiting at the reverse proxy in addition to application WorkerKey limits.

## Write uncertainty

For upload writes, timeout/cancel/connection loss/5xx may occur after the server accepted the request. Such outcomes are `commit_unknown` and must not be retried automatically. Verify through MCP first.
