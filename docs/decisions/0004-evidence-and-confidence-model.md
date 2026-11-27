# ADR 0004: Evidence and confidence model

- **Status:** accepted
- **Date:** 2026-11-26

## Context

The declared weakness of existing unused-table tools is false positives. Unity Catalog lineage only records the events it can infer, and ADLS last access time only exists after it is enabled. A bank will not retier or drop anything on a guess.

## Decision

Every finding carries:

- **Evidence:** each signal that supports it, with its source and timestamp.
- **Confidence:**
  - **high:** lineage shows no read in the window *and* storage last access covers the whole window and shows no read.
  - **medium:** lineage shows no read and storage cannot confirm (tracking off, enabled too late, or no inventory); or, for storage no table owns, storage confirms no read.
  - **low:** storage no table owns, with no storage confirmation.
- **Coverage notes:** what could not be seen, per finding and per run (lineage history shorter than the window, tracking enabled after the window start, JDBC blind spot).
- **Proof hash:** SHA-256 over the canonical JSON of the finding, so a later run or an auditor can verify it is unchanged.

Conflicting signals resolve towards "in use": if storage shows a read inside the window, there is no finding even when lineage is silent.

Tables created inside the window, views and the `samples` catalog are skipped.

Each run can be compared with the previous one (`cosmosproof diff`): new findings are the alerts, resolved ones feed the realized-savings ledger (`cosmosproof ledger`), which records the action, who took it and the finding's proof hash.

## Consequences

- Fewer findings than a naive tool, by design.
- The model mirrors Cosmos Semantic's evidence envelope, applied to cost and risk.
- Cost estimates use only the customer's own rates per tier; there are no built-in prices, because a wrong price is worse than none.
