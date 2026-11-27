# ADR 0008: Storage read logs as a second storage signal

- **Status:** accepted
- **Date:** 2026-11-27

## Context

In storage-only mode ([ADR 0006](0006-storage-only-mode.md)) the verdict rests on ADLS last access time, which has a **one-day granularity**: a second read on the same day does not move it. That makes short windows impossible and hides who read a file.

Azure Storage resource logs (category `StorageRead`), sent to Log Analytics, record every read (`GetBlob`, `ReadFile`) with its exact time and the caller, for any reader inside or outside Databricks.

## Decision

- `storage[].access_logs: {workspace_id, since}` makes the scan query `StorageBlobLogs` for reads of each container since logging was enabled, mapped to file URLs.
- A storage group counts as **read** when either signal shows a data-file read inside the window, and **silent** only when every signal that covers the window shows none. A signal covers the window only if it was on before the window started.
- `window_hours` gives a window in hours ending now. It only makes sense with read logs.
- `cosmosproof grants --log-analytics <workspace>` prints the diagnostic setting and the `Log Analytics Reader` role for the identity.

## Consequences

- Short windows work, which made it possible to validate the lab on the same day it was deployed.
- Platform maintenance that reads files (for example `OPTIMIZE`) counts as a read, and every log-based finding says so.
- Ingestion has a cost proportional to read volume, so read logs are optional; last access time remains the free default.
- Logs reach Log Analytics after a delay of minutes; a scan right after a read may not see it yet.
