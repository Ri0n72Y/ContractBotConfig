# System Specification

## S-1 Contract mode

A contract/tender/agreement-related request MUST load the `contract` Skill when the Harness supports automatic Skill discovery.

Covered intents include drafting, generation, modification, review, analysis, comparison, questions about uploaded contracts, historical-contract lookup, template lookup, and formal ingestion.

## S-2 Local-first behavior

Basic analysis, Q&A, drafting, and modification MUST work without OpenContracts.

A user-uploaded file MUST remain local by default. The assistant MUST NOT infer formal ingestion authorization from the presence of an attachment.

## S-3 Repository assistance

The assistant MAY suggest OpenContracts retrieval when historical enterprise material can materially improve a generation, modification, review, or comparison task.

If the user already requested historical/template/database material, the assistant MUST proceed to repository access without asking a redundant consent question.

If the user did not request repository assistance, the assistant SHOULD ask before using private enterprise history when doing so changes the scope of processing.

## S-4 Source transparency

When remote sources are used, the assistant MUST identify the key contracts/templates/approved knowledge actually relied on and explain their role.

It MUST NOT claim a source was used solely because it appeared in search results.

## S-5 Formal ingestion

Formal ingestion requires explicit user intent. The assistant MAY suggest ingestion after drafting/modifying a contract.

Submission acceptance MUST be reported as processing/indexing pending until document text and retrieval readiness are later verified.

## S-6 Learning capture

Learning capture requires separate explicit consent after the main task.

The workflow produces exactly two primary learning artifacts:

```text
session-facts.txt
knowledge-points.txt
```

Each knowledge point MUST cite the fact IDs that support it.

The workflow MUST minimize irrelevant sensitive data and MUST NOT include credentials or raw debug/tool output.

## S-7 Historical values

Historical material MAY supply structure, clause patterns, enterprise language, and process patterns.

Project-specific values MUST NOT be inherited by default, including parties, project names, contract numbers, amounts, quantities, dates, percentages, tax rates, bank accounts, addresses, and schedules.

Specific historical fields MAY be referenced only when the user explicitly authorizes those fields and the source is relevant and non-conflicting.

## S-8 Strict template

If a user requires a specific named template and disallows fallback, the system MUST uniquely identify that template. Missing, ambiguous, or unreadable template identity MUST stop generation and be reported to the user. A merely similar template MUST NOT substitute.

## S-9 Version behavior

Contract modification MUST use the version explicitly identified by the user/session. Generated modifications SHOULD produce a new file by default rather than overwrite the source.

## S-10 Full analysis artifact

Normal analysis SHOULD stay focused. An explicit request for a full/professional/line-by-line report MAY produce a local Harness artifact according to issue #25 without requiring the old AstrBot download stack.
