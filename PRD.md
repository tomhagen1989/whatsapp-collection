Receivables Copilot
Product Requirements Document + Technical Design Spec
MVP for WhatsApp-first AR Morning Brief and Collections Memory
Version 1.1
Date: 2 April 2026
Authoring basis: LLM-forward MVP, customer-controlled data in Google Drive, invoice-level truth, customer-level UX

This document combines the business PRD and the implementation-oriented technical design for the first production MVP.

Part I - Product Requirements Document (PRD)
1. Product Overview
Summary: Receivables Copilot is a WhatsApp-first assistant for small businesses that sends a daily ageing summary, helps the collector log what happened with each customer, and builds customer-wise collections memory over time.
User: The primary user is the person who actually follows up for payment - owner, accountant, collections executive, office admin, or sales coordinator.
Job: "Every morning, tell me where my receivables stand and help me track what each customer said so I know who to follow up with next."
Wedge: The MVP is not an ERP, invoicing engine, or autonomous collections bot. It is a daily action layer plus a memory system.

2. Product Direction
LLM posture: Use LLMs broadly for conversational understanding, extraction, summarization, and recommendation. Keep deterministic validation around customer identity, invoice selection, dates, paid amounts, and all summary numbers.
Provider posture: Route LLM traffic through OpenRouter so the team can switch models easily without changing application code.
User experience: WhatsApp is the primary daily surface. A small web onboarding console exists for Drive connection, source selection, schema mapping, and manual sync.
Storage model: Store receivables at invoice level and derive customer-level timelines, summaries, and next actions from that structured state.
Input modes: Text is the only primary input mode in MVP. Voice notes are explicitly deferred.

3. Goals and Non-goals
Primary goal: Create a daily collections habit for the user.
Secondary goals: Preserve customer-specific payment context, reduce missed follow-ups, convert messy updates into structured data, and recommend the next best follow-up.
Non-goals: Direct Tally integration, customer-facing reminder campaigns, payment links, reconciliation, full accounting sync-back, legal escalation workflows, or autonomous outbound actions.

4. Core Flows
Onboarding: User connects Google Drive, chooses a receivables file, maps columns if needed, sets briefing time, and runs the first sync.
Morning brief: Every morning the user gets total outstanding, ageing buckets, top overdue accounts, promises due, stale cases, and a suggested next action.
Drilldown: User can ask for "show Gupta", "show 90+", "top overdue", "who promised this week?", and free-form variants of those intents.
Logging: User replies with updates like "1 promised Friday" or "Mehta paid 20000". The system extracts the intent with an LLM, verifies the critical facts, asks for clarification when needed, and writes immutable events to the timeline.
Timeline: For each customer the system maintains the latest promise, last note, broken promises, next action date, and recent event history.

5. Functional Requirements
Ingestion: Support Google Drive file selection, CSV/XLSX ingestion, recurring refresh from the same file, and user-assisted schema mapping.
Normalization: Normalize into a canonical schema with customer_name and amount_outstanding required, due_date and invoice_reference strongly preferred.
Identity: Match customers by external code first, then phone number, then normalized customer name. The same customer should reconcile across imports whenever possible.
Reconciliation: Each import creates a versioned snapshot. Rows missing from the latest import are soft-closed, changed balances update the active case, and reappearing rows reopen the case under the same source identity when possible.
Summary: Generate total outstanding, bucket split, top overdue list, promises due, stale follow-ups, and a short attention queue.
Updates: Support paid_full, paid_partial, promise_to_pay, asked_to_call_later, unreachable, dispute_raised, no_response, wrong_contact, and other.
Recommendations: Suggest who needs follow-up next and optionally draft a short collector-facing action suggestion. Do not autonomously send customer-facing messages.
Retrieval: Support customer search, ageing bucket query, promise-due query, stale-follow-up query, top-overdue query, and natural-language paraphrases of those requests.

6. Non-functional Requirements
Performance: Daily summary generation must support at least 10,000 open cases per tenant. Common retrieval questions should usually respond within 5 seconds.
Reliability: Handle duplicate webhooks, idempotent imports, reminder retries, and Drive refresh retries.
Security: Raw files remain in customer-owned Google Drive. Backend stores only operational copies, indexes, state, and event history. Credentials and sensitive metadata must be encrypted.
Privacy: No training on customer financial data. Maintain clear tenant boundaries. Support purge of cached artifacts when a customer disconnects.

7. Success Metrics
Primary: Percentage of days the user engages after the morning brief, logged updates per user per week, and share of active cases with at least one update over 2 weeks.
Secondary: Drilldowns requested, promise tracking coverage, stale cases reduced over time, repeated weekly active usage, and recommendation acceptance rate.
Signal: "I start my day with this message."

8. MVP Release Definition
- Customer can connect Google Drive.
- Customer can point the app to one receivables spreadsheet.
- System can generate and send a daily ageing summary on WhatsApp.
- User can ask customer-level drilldowns.
- User can log updates like "promised Friday" and "paid 20k".
- Those updates change future follow-up and summaries.
- The assistant can recommend the next best follow-up.
- The user trusts that the system remembers what happened.

Part II - Technical Design Specification
1. Architecture
- FastAPI backend with a small web onboarding console.
- PostgreSQL as the operational source of truth.
- Redis plus Celery for background jobs, idempotency, and scheduling.
- Google Drive integration for source-file access.
- WhatsApp webhook integration for inbound and outbound messages.
- OpenRouter-backed orchestration service for parsing, summarization, and recommendations.
- Deterministic verification service for identity, invoice, amount, and summary checks.

2. Core Data Model
- tenants: business isolation, timezone, briefing time, ageing config.
- users: WhatsApp-linked operators.
- drive_connections: encrypted Drive OAuth state per tenant.
- drive_sources: connected source files and schema mapping.
- import_snapshots: versioned imports with status and summary stats.
- customers: debtors with normalized identity fields.
- receivable_cases: invoice-level operational records with status and follow-up state.
- case_events: immutable case timeline.
- raw_messages: inbound and outbound audit trail.
- reminders: scheduled briefs and follow-ups.
- customer_profiles: derived operational summary per customer.
- pending_confirmations: write previews awaiting confirmation when confidence is not high enough.

3. Retrieval and AI Design
- Use the LLM as the default conversational layer.
- Route model calls through OpenRouter to keep model choice flexible.
- Retrieve candidate records deterministically before composing answers.
- Never allow the LLM to invent totals, bucket splits, rankings, amounts, or invoice state.
- Ask for clarification when customer match, invoice match, promised date, or paid amount is ambiguous.
- Cache or precompute repeated brief structures where useful, but keep the structured database as the source of truth.

4. Scheduling Logic
- Morning brief is generated after the latest successful import.
- If refresh fails, use the last successful snapshot and explicitly mention freshness.
- Promise-to-pay and follow-up outcomes create reminders.
- Stale cases and missed promises feed the attention queue.

5. Launch Thresholds
- Intent classification accuracy > 95 percent on common commands.
- Paid amount extraction accuracy > 95 percent.
- Wrong customer match rate < 2 percent on evaluated cases.
- Numeric hallucination rate in summaries near zero.
- Typical retrieval latency < 5 seconds.

6. Rollout
- Phase 0: concierge pilot with 5-10 businesses and close operator feedback.
- Phase 1: closed beta MVP with one Drive source per tenant, daily brief, drilldowns, and update logging.
- Phase 2: stronger self-serve mapping, richer recommendations, and deeper analytics.
