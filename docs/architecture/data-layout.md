# OpenContracts Data Layout

## Principle

OpenContracts stores only retrievable enterprise contract data needed by the current runtime. Session-learning material stays outside OpenContracts because it is maintained manually rather than used as runtime retrieval data.

Corpus boundaries organize business data and workflow. In the trusted-network MVP they are not the confidentiality boundary because the retrieval corpuses remain public.

## Recommended corpuses

### `contracts-history`

Purpose: formally ingested executed/draft historical contracts used for retrieval and comparison.

Rules:

- public inside the trusted-network MVP;
- formal ingestion uses a WorkerKey bound only to this Corpus;
- project-specific values are data, never automatic defaults for new contracts.

### `contract-templates`

Purpose: enterprise-approved contract templates.

Rules:

- public inside the trusted-network MVP;
- only templates and directly related template guidance belong here;
- strict named-template requests require unique identity confirmation;
- templates never contain credentials or operational system instructions.

## No knowledge/learning Corpus in MVP

There is no `approved-knowledge`, Learning Inbox, or other experience Corpus in the MVP. Reusable operating guidance that is stable enough for the assistant belongs in the maintained Skill files. If experience material is collected from sessions, it stays as local/shared notes until a maintainer reviews it and edits the relevant Skill.

## Experience system outside OpenContracts

`contract-learning` creates local experience notes after separate user consent. Maintainers periodically collect, review, merge and generalize useful lessons, then update the relevant Skill files through normal version control.

No automatic vectorization, retrieval, remote learning upload or self-modifying Skill loop is part of the MVP.

## Network boundary

```text
trusted LAN / VPN
    ├── Harness users
    ├── WorkBuddy host
    └── OpenContracts fixed LAN IP

Internet / untrusted network
    X OpenContracts
```

If OpenContracts becomes reachable outside this boundary, or internal users need different confidentiality scopes, affected corpuses can later move to private authenticated access.
