# Demo script (about 5 minutes)

Frontend: `https://aggroso-ten.vercel.app`. Backend: https://isushant-aggroso.hf.space. Both demo accounts use the password `migrateiq-demo`.

If the header shows "Waking the server", wait up to a minute; the free Space was asleep.

## 1. Sign in and create a project (30 s)

1. Sign in as `operator`.
2. Create a project with the `baseline_60` dataset. Use your own project name; projects are not shared resets.
3. Open Inputs and glance at the source schema, the fixed target schema and the transform registry.

## 2. Agent proposal (90 s)

1. Open Agent and start a run. The trace shows each tool call, LLM call and validation result as it happens.
2. If the primary is unavailable or rate limited, the run restarts on the backup and a notice says the backup is in use. This can take one to two minutes. In a local build the notice can be forced with `FORCE_BACKUP=true`.
3. If both providers are out of quota, skip to step 3 and use "Load reference plan"; the rest of the demo needs no model.

## 3. Review the plan (60 s)

1. Open Plan. Check mappings, confidence, rationale and risks.
2. Answer the clarification questions and acknowledge the high-severity risk.
3. Optionally edit a mapping, save a new version and open the diff.
4. For the deterministic path, use "Load reference plan".

## 4. Dry run (30 s)

1. Run a dry run. With the reference plan on `baseline_60` the counts are 60 source, 55 transformed, 45 accepted, 15 rejected.
2. Open a rejected record to see field-level evidence (field, source value, transform, rule, code).
3. Optionally run the determinism check: the result hash matches.

## 5. Approve (30 s)

1. Sign out and sign in as `approver`.
2. Open Approve, review the checklist and approve. The approval is bound to the plan hash, the dry-run hash and the source checksum.

## 6. Execute, fault, retry, reconcile, roll back (60 s)

1. Sign in as `operator` and open Execute.
2. Execute with fault injection enabled. The run fails part way through and the attempt is recorded.
3. Retry. Only unrecorded records are processed, so there are no duplicates. Reconciliation shows PASS: target counts, keys and row hashes match the dry run.
4. Sign in as `approver` and roll back the run. Reconciliation now shows 0 target rows for the run.

## 7. History and logs (30 s)

1. Open History: plan versions, approvals, attempts, retry and rollback in one timeline.
2. Open Logs and filter by a request id from a failed call to see the matching backend lines.
