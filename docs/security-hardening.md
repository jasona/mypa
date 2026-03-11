# Security Hardening Plan

This document captures the current abuse-risk review for the Persistent Agent Daemon and a phased implementation plan to reduce the most important attack vectors without breaking the core scheduling workflow.

## Primary Risks

- Untrusted inbound email can currently influence privileged tool use.
- Telegram inbound messages are not restricted to an approved operator chat.
- Email replies can be redirected to arbitrary recipients.
- Calendar update and delete operations are not bound to assistant-owned events.
- AgentMail replay handling is not atomic, which can duplicate side effects.
- Public HTTP endpoints and stored payloads reveal more than they should.
- Large or repeated inputs can drive unnecessary token and API spend.

## Phase 0: Safe Defaults

Goal: make configuration mistakes less dangerous.

### Changes

- Fail closed in production when `AGENTMAIL_WEBHOOK_SECRET` is missing.
- Optionally require `TELEGRAM_ADMIN_CHAT_ID` in production.
- Warn or fail startup when `AGENTMAIL_INBOX_ADDRESS` is unset.
- Reduce `/health` output in production to a minimal status response.
- Add explicit hardening config values:
  - `TELEGRAM_ALLOWED_CHAT_IDS`
  - `EMAIL_TRUSTED_DOMAINS`
  - `EMAIL_TRUSTED_SENDERS`
  - `EMAIL_REQUIRE_APPROVAL_FOR_MUTATIONS`
  - `MAX_EMAIL_BODY_CHARS`
  - `MAX_TOOL_CALLS_PER_RUN`

### Acceptance Criteria

- Production cannot start with an unauthenticated public webhook.
- Production health responses do not expose dependency posture.

## Phase 1: Lock Down Telegram

Goal: ensure only the operator can control the assistant from Telegram.

### Changes

- Enforce inbound allowlisting for Telegram `chat_id`.
- Default to `TELEGRAM_ADMIN_CHAT_ID` if no explicit allowlist is provided.
- Restrict inbound usage to private chats unless explicitly enabled.
- Log unauthorized access attempts without sending sensitive replies.

### Acceptance Criteria

- Only approved chats can reach Claude or calendar tools.
- Random Telegram users cannot use the bot as an operator interface.

## Phase 2: Put Email Behind Guardrails

Goal: stop arbitrary inbound email from autonomously driving privileged actions.

### Changes

- Split email handling into trust levels:
  - Untrusted email: summarize and notify only.
  - Trusted email: allow limited scheduling automation.
  - Approved thread: allow broader actions after operator approval.
- Add sender and domain trust checks.
- Require approval before email-originated `reply_email`, `create_event`, `update_event`, or `delete_event` unless policy allows them.

### Acceptance Criteria

- Untrusted senders cannot autonomously send replies or change calendar state.
- Trusted senders can still use the workflow within policy limits.

## Phase 3: Constrain Outbound Email

Goal: prevent exfiltration and abuse through the reply path.

### Changes

- Restrict reply recipients to addresses already present in the thread.
- Validate `to` and `cc` against original participants.
- Remove or strictly limit `bcc`.
- Remove or strictly limit custom `reply_to`.
- Normalize and validate outbound addresses before calling AgentMail.

### Acceptance Criteria

- The assistant cannot silently add attacker-controlled recipients.
- Email replies stay bound to the original conversation participants.

## Phase 4: Bind Calendar Mutations to Owned Records

Goal: prevent unrelated event tampering.

### Changes

- Store assistant-created Google `event_id` values per thread.
- Only allow `update_event` and `delete_event` for events linked to the current thread.
- Avoid exposing broad raw upcoming event payloads when summarized context is sufficient.

### Acceptance Criteria

- The assistant cannot modify or delete unrelated calendar events.
- Event mutation requires an auditable thread-to-event link.

## Phase 5: Fix Replay and Idempotency

Goal: stop duplicate side effects from retries or repeated deliveries.

### Changes

- Claim `event_id` before processing begins.
- Track statuses such as `received`, `processing`, `completed`, and `failed`.
- Skip work when an event is already in progress or completed.
- Add idempotency around external side effects like replies and event creation.

### Acceptance Criteria

- AgentMail retries do not create duplicate replies or meetings.
- Replayed webhook deliveries are safely ignored.

## Phase 6: Minimize Untrusted Data

Goal: reduce prompt-injection impact and shrink data leakage.

### Changes

- Truncate email bodies before sending them to the LLM.
- Strip quoted history and signatures more aggressively.
- Treat inbound email content as untrusted quoted data in prompts.
- Truncate or redact `dead_letters` payloads.
- Avoid sharing unnecessary email content into Telegram notifications.

### Acceptance Criteria

- Large or malicious emails cost less to process.
- Sensitive content is less likely to be retained or forwarded unnecessarily.

## Phase 7: Add Abuse Controls

Goal: resist brute-force usage and resource exhaustion.

### Changes

- Add webhook request size limits.
- Add rate limits for public HTTP routes.
- Add limits on LLM tool-call count per request.
- Bound `check_availability` date ranges and calendar ID counts.
- Consider cool-downs for repeated Telegram requests.

### Acceptance Criteria

- Large inputs and repeated requests cannot easily burn token or API budgets.
- Expensive calendar queries are kept within safe bounds.

## Phase 8: Observability and Operator Controls

Goal: make abuse visible and give the operator a safe override path.

### Changes

- Send Telegram alerts for unauthorized Telegram access attempts.
- Alert on rejected email mutation attempts and replay bursts.
- Add operator approval commands such as per-thread approval.
- Record audit reasons for why an action was allowed or denied.

### Acceptance Criteria

- Policy decisions are visible and auditable.
- The operator can safely approve or deny exceptional cases.

## Recommended Implementation Order

1. Telegram inbound allowlist
2. Fail-closed AgentMail webhook secret handling
3. Production-safe `/health`
4. Email recipient restrictions
5. Email trust tiers and approval gate
6. Thread-bound calendar mutation rules
7. Atomic idempotency
8. Prompt and data minimization
9. Rate limiting and request size controls
10. Audit and operator approval UX

## Suggested First Milestone

The best first milestone is:

1. Add Telegram inbound allowlisting
2. Fail closed when `AGENTMAIL_WEBHOOK_SECRET` is missing in production
3. Reduce `/health` output in production
4. Restrict outbound email recipients to current thread participants
5. Document the new security settings in `.env.example` and `docs/environment.md`

This set delivers the largest immediate risk reduction with the least workflow disruption.
