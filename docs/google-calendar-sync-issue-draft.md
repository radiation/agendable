## Problem / Motivation
Users currently need to manage meetings in two places: their calendar and Agendable. This creates duplicate effort and drift risk when events are rescheduled or canceled externally.

## Proposed solution
Implement Google Calendar import/sync in phased rollout:

1. **Phase 1 (this issue scope): foundation + ingest mirror**
   - Persist per-user calendar connection state (tokens, scopes, sync token, watch metadata).
   - Persist mirrored external event metadata keyed by Google event IDs.
   - Add sync service abstraction and incremental sync flow primitives.
   - Keep behavior one-way and non-destructive (Google -> mirror tables only).
2. **Phase 2 (follow-up): link mirror events to meeting series/occurrences**
   - Deterministic upsert mapping from mirrored events into Agendable meetings.
   - Handle reschedules/cancellations and recurring instances.
3. **Phase 3 (follow-up): push notifications + operational hardening**
   - `events.watch` channel lifecycle management.
   - Retry/backoff and observability for sync workers.

## In-meeting impact
- Reduces prep friction by eliminating duplicate meeting setup.
- Improves confidence that in-meeting context matches current calendar reality.
- Sets up real-time freshness improvements for shared meeting views.

## Alternatives considered
- Manual CSV/ICS import only: lower complexity, but no ongoing update propagation.
- Build task synchronization first: less immediate user value than meeting source-of-truth alignment.

## Non-goals
- Bi-directional edits from Agendable back to Google Calendar.
- Immediate task auto-creation from calendar events.
- Full attendee reconciliation in this phase.

## Acceptance criteria
- [ ] DB migration adds calendar connection + external event mirror tables.
- [ ] Repositories support querying/upserting connection and mirrored events.
- [ ] Google sync service contract exists and can ingest batches idempotently into mirror tables.
- [ ] OIDC scope config supports optional calendar readonly consent.
- [ ] Tests cover repository behavior and sync mirror upsert path.

## Rollout / risk notes
- Default feature flag remains off (`AGENDABLE_GOOGLE_CALENDAR_SYNC_ENABLED=false`).
- Token handling is persisted in DB; follow-up should add encryption-at-rest/KMS in long-lived envs.
- Keep meeting/task mutation out of initial rollout to minimize user-facing risk.

## Additional context
- Existing OIDC integration and external identity tables are already in place.
- This issue intentionally creates a strong persistence/service foundation so Phase 2 can focus only on mapping logic.
