Receivables Copilot
Product Requirements Document + Technical Design Spec
MVP for WhatsApp-first AR Morning Brief and Collections Memory
Version 1.0
Date: 2 April 2026
Authoring basis: low-cost MVP, customer-controlled data in Google Drive, excellent retrieval UX

This document combines the business PRD and the implementation-oriented technical design for a first production MVP.
Part I — Product Requirements Document (PRD)
1. Product Overview
Summary: Receivables Copilot is a WhatsApp-first assistant for small businesses that sends a daily ageing summary, helps the collector log what happened with each customer, and builds customer-wise collections memory over time.
User: Primary user: the person who actually follows up for payment — owner, accountant, collections executive, office admin, or sales coordinator.
Job: Core job to be done: “Every morning, tell me where my receivables stand and help me track what each customer said so I know who to follow up with next.”
Wedge: The MVP is not an ERP, invoicing engine, or autonomous collections bot. It is a daily action layer plus a memory system.
2. Why This MVP
Problem: Receivables are often managed through Tally exports, WhatsApp chats, calls, notebooks, and memory. The breakdown is not just missed reminders; it is loss of case memory.
Insight: A simple morning ageing split on WhatsApp is already a major unlock. That makes the morning brief the front door, with logging and memory as the retention engine.
Hypothesis: If the product ingests receivables data from the customer’s Google Drive, sends a clear morning summary, and makes it very easy to log outcomes like “promised Friday” or “paid 20k”, users will build a habit around it.
3. Product Goals
Primary: Create a daily collections habit for the user.
Secondary: Preserve customer-specific payment context, reduce missed follow-ups, convert messy updates into structured data, and create the foundation for later automation.
Non-goals: Do not build direct Tally integration, customer-facing reminder campaigns, payment links, reconciliation, full accounting sync-back, team workflows, legal escalation flows, or heavy analytics in MVP.
4. Personas
Primary: Owner-collector: runs or closely oversees cash flow, reviews outstanding dues frequently, follows up manually, and values simplicity over software depth.
Secondary: Accountant or collections operator: executes follow-ups, tracks oral promises, and currently updates things manually or inconsistently.
5. Scope
Capabilities: The MVP ingests receivables data from files stored in Google Drive, parses and normalizes Tally exports or similar spreadsheets, generates customer-wise and ageing-wise summaries, sends a daily WhatsApp brief, allows user queries and updates, logs updates into customer timelines, and provides lightweight operational insights.
Channels: WhatsApp is the primary interface. Google Drive is the primary raw-data store and customer-owned system of record. The backend stores only operational metadata, normalized indexes, state, and event history needed for performance and reliability.
6. Core Product Flows
Onboarding: User connects Google Drive, selects a receivables source file, maps columns if needed, sets briefing time and ageing buckets, and receives the first WhatsApp summary.
Brief: Every morning the user gets total outstanding, ageing buckets, top overdue accounts, and “needs attention” cases with short reply actions.
Drilldown: User can ask for “show Gupta”, “show 90+”, “top overdue”, “who promised this week?”, and similar structured queries.
Logging: User replies with updates like “1 promised Friday”, “Mehta paid 20000”, or a short voice note. The system extracts structured fields, asks a clarification only if needed, stores the event, and updates next follow-up.
Timeline: For each customer the system maintains a concise timeline with latest promise, last note, broken promises, and next action date.
7. Functional Requirements
Ingestion: Support Google Drive file picker, CSV/XLSX ingestion, recurring refresh from the same file, and user-assisted schema mapping on first import.
Normalization: Normalize imported data into a canonical schema with customer_name and amount_outstanding required; due_date and invoice_reference strongly preferred.
Summary: Generate total outstanding, bucket split, top overdue list, promises due, stale follow-ups, and a short attention queue.
Updates: Support controlled outcome types: paid_full, paid_partial, promise_to_pay, asked_to_call_later, unreachable, dispute_raised, no_response, wrong_contact, and other.
Retrieval: Support customer search, ageing bucket query, promise-due query, stale-follow-up query, and top-overdue query.
8. Non-Functional Requirements
Perf: Daily summary generation must comfortably support up to 10,000 open cases per tenant. Common retrieval questions on WhatsApp should usually respond within 5 seconds.
Reliability: System must handle duplicate webhooks, idempotent ingest, reminder retry, and Drive refresh retry.
Security: Raw files remain in customer-owned Google Drive. Backend stores operational copies and indexes only. All credentials and sensitive metadata must be encrypted.
Privacy: No training on customer financial data. Clear tenant boundaries. Ability to purge cached copies and derived indexes if customer disconnects.
9. Success Metrics
Primary: Percentage of days the user engages after receiving the morning brief; logged updates per user per week; share of active cases with at least one update over 2 weeks.
Secondary: Customer drilldowns requested, promise tracking coverage, stale cases reduced over time, and repeated weekly active usage.
Signal: Strong value signal: “I start my day with this message.”
10. Open Questions for Pilot
Questions: How often do users update outcomes by WhatsApp? Do they prefer free text or voice? How clean are Tally exports? Do they want per-invoice or customer-total tracking first? How much freshness is required beyond daily sync?
11. Example Morning Brief
• Receivables as of today
• Total outstanding: Rs 12.4L
• 0–30 days: Rs 3.1L | 31–60 days: Rs 2.7L | 61–90 days: Rs 2.0L | 90+ days: Rs 4.6L
• Needs attention: 1) Gupta Traders — Rs 48,500 — 67 days overdue  2) Mehta Agencies — Rs 1,20,000 — promised yesterday  3) Shree Distributors — Rs 32,000 — no update in 9 days
• Reply options: “show Gupta”, “show 90+”, “1 promised Friday”, “2 paid 50000”, “3 dispute”
12. MVP Release Definition
• Customer can connect Google Drive.
• Customer can point the app to one receivables spreadsheet.
• System can generate and send a daily ageing summary on WhatsApp.
• User can ask customer-level drilldowns.
• User can log updates like “promised Friday” and “paid 20k”.
• Those updates change future follow-up and summaries.
• The user trusts that the system remembers what happened.
 
Part II — Technical Design Specification
Design principles: keep raw business data with the customer in Google Drive, keep infrastructure inexpensive, favor deterministic logic over unnecessary AI, and make retrieval answers fast, trustworthy, and grounded in structured state.
1. System Architecture
• WhatsApp Integration Service: receives inbound messages, sends morning briefs and reminders, and tracks webhook idempotency.
• Google Drive Integration Service: manages OAuth, file metadata, scheduled refresh, and source selection.
• Ingestion and Normalization Pipeline: parses XLSX/CSV, applies schema mapping, validates fields, and creates versioned import snapshots.
• Collections Case Service: owns customers, receivable cases, state transitions, event append, and derived summaries.
• Scheduling Service: generates morning briefs and promise-follow-up reminders.
• AI Service: handles intent classification, free-text extraction, and compact summarization only when deterministic parsing is insufficient.
• Query Service: answers retrieval questions using SQL-first structured retrieval and light summarization.
• Operational Database: PostgreSQL for transactional data plus Redis for cache, idempotency, and queues.
2. Cost-Conscious Stack Choices
Layer	Choice	Why
Backend API	FastAPI (Python)	Cheap to host, strong ecosystem for data + AI orchestration, fast iteration.
Primary DB	PostgreSQL	Reliable, low-cost, SQL-first retrieval, JSONB support, no need for a vector DB in MVP.
Cache / Queue	Redis	Low-cost support for idempotency, short-lived cache, and background jobs.
Background Jobs	Celery + Redis	Cheaper and simpler than heavier workflow engines for MVP.
Raw file storage	Google Drive	Data stays with customer; reduces app-side storage and trust burden.
Processing artifacts	Ephemeral local/S3-compatible temp store	Only temporary files during parse/transcribe steps.
Search	Postgres indexes + full-text	Best cost-performance for structured queries.
Observability	Basic metrics + logs + error alerts	Enough for MVP without enterprise monitoring spend.

3. Data Ownership and Storage Model
• Raw source spreadsheets remain in the customer’s Google Drive.
• The application stores minimal operational copies: normalized receivable rows, case state, customer profiles, event history, reminders, and AI audit metadata.
• The app may optionally write processed snapshots or generated reports back into the customer’s Drive for transparency.
• The source of truth for raw files is Drive. The source of truth for live application behavior is the structured operational database.
4. Core Data Model
Entity	Purpose	Key fields
tenants	Business-level isolation	business_name, timezone, morning_brief_time, ageing_config_json
users	WhatsApp-linked operators	tenant_id, whatsapp_phone, role
drive_sources	Connected source files/folders	google_file_id, schema_mapping_json, last_synced_at
import_snapshots	Versioned daily imports	snapshot_version, sync_status, source_modified_at, summary_stats_json
customers	Debtors/parties	customer_name, phone_number, external_customer_code
receivable_cases	Live due items	customer_id, invoice_reference, due_date, amount_outstanding, status, next_follow_up_date
case_events	Immutable timeline events	event_type, event_timestamp, structured_payload_json, raw_message_id
raw_messages	Inbound/outbound message audit	whatsapp_message_id, text_body, transcript_text, raw_payload_json
reminders	Scheduled brief and follow-up jobs	reminder_type, scheduled_for, status
customer_profiles	Derived operational summary	total_outstanding, promise_break_count, last_contact_at, latest_summary

5. Ingestion Pipeline
• Fetch selected file from Google Drive.
• Detect file type and sheet/tab.
• Apply stored schema mapping or user-assisted mapping if first import.
• Validate required fields and normalize dates, currency amounts, and strings.
• Create an import snapshot and attach summary stats.
• Upsert customers and receivable cases.
• Mark stale/closed cases carefully; do not auto-delete historical cases.
• Publish refreshed aggregates for morning brief generation.
6. Canonical Schemas
Schema	Required fields	Preferred fields	Optional fields
Receivable import	customer_name, amount_outstanding	due_date, invoice_reference	invoice_date, overdue_days, phone_number, salesperson, notes
Case update	customer resolution, outcome_type	promised_date or paid_amount when relevant	reason_code, contact_person, free_text_note, suggested_next_follow_up_date
Morning brief	total_outstanding, ageing buckets, attention list	promises due, stale cases	delta vs yesterday

7. Retrieval Design — Highest Priority UX
• Retrieval must be SQL-first, not RAG-first. Most user questions are structured: by customer, ageing, promise due, stale follow-up, or amount overdue.
• Use indexed lookups on tenant_id, customer_name, overdue bucket, next_follow_up_date, status, and latest promise date.
• For “show Gupta”, retrieve the matching customer, active cases, latest events, and derived profile, then build the answer from templates or a constrained summarizer.
• For ranking queries like “top overdue”, compute directly from structured rows. No LLM should invent ordering or numbers.
• Use AI only to produce compact natural-language phrasing once the record set is already chosen deterministically.
• Cache frequent summary objects such as today’s morning brief, customer timeline summaries, and stale-case lists.
8. AI Usage
• Use deterministic parsing first for common phrases such as “Gupta promised Friday”, “Mehta paid 20000”, and “show 90+”.
• Call an LLM only for ambiguous, multi-clause, or free-form updates and for compact summaries.
• Use speech-to-text only for voice notes; then feed transcript through the same extraction pipeline.
• Use OCR only as a helper when invoice screenshots or proof images are included. OCR is not the core MVP wedge.
• Never treat model output as the source of truth. Store parsed JSON with confidence, raw message reference, and validation result.
• If a critical field is low-confidence — customer match, promised date, paid amount — ask one short clarification question before committing.
9. Recommended Model Strategy
Task	Preferred approach	Low-cost fallback
Intent classification	Rule-based parser + small LLM fallback	Pure rules for common commands
Case update extraction	High-quality structured-output LLM	Smaller cheaper model for retries on non-critical messages
Voice transcription	Hosted speech-to-text with good Indian English support	Queue for async processing; offer text-first UX initially
Summary generation	Template + deterministic stats, optional tiny LLM polish	Pure templates
OCR	Basic OCR only when needed	Ask user for missing values instead of over-engineering OCR

10. Scheduling Logic
• Morning brief is sent daily after the latest successful file sync.
• If refresh fails, use the last successful snapshot and explicitly mention freshness in the message.
• Promise-to-pay updates create a reminder on the promised date at a sensible follow-up hour.
• Asked-to-call-later, partial payment, and dispute updates each trigger simple rule-based next-step logic.
• A stale case is one with no update for N days or a missed promise; stale cases feed the attention queue.
11. API Surface
• POST /webhooks/whatsapp — ingest inbound messages and status updates.
• POST /drive/connect — store OAuth connection.
• POST /drive/sources — register a file or folder as source.
• POST /imports/run — trigger manual sync.
• GET /summary/today — generate or return cached morning summary.
• GET /customers/{id}/timeline — structured customer retrieval for app and WhatsApp responses.
• POST /cases/{id}/events — append a structured user/system event.
• POST /ai/extract — internal service endpoint for parse workflows.
12. Evals and Quality Gates
• Intent classification eval: measure command classification accuracy and confusion matrix across summary queries, drilldowns, and update messages.
• Structured extraction eval: measure exact or near-exact extraction for customer name, outcome type, promised date, paid amount, reason code, and follow-up date.
• Summary quality eval: verify no hallucinated numbers and correct ranking against the current snapshot.
• End-to-end task eval: given a source snapshot and a user update, ensure the correct case is resolved, the right event is written, and the reminder schedule is updated appropriately.
• Online quality metrics: clarification rate, correction rate after parse, wrong-customer-match rate, and latency of common retrieval questions.
13. Suggested Launch Thresholds
Metric	Target before closed beta
Intent classification accuracy	> 95% on common commands
Paid amount extraction accuracy	> 95%
Date extraction accuracy for relative phrases	> 85%
Wrong customer match rate	< 2% on evaluated set
Numeric hallucination rate in summaries	Near zero
Typical retrieval latency	< 5 seconds

14. Reliability, Security, and Privacy
• Store OAuth secrets and sensitive credentials encrypted at rest.
• Use tenant isolation in all queries and indexes.
• Maintain immutable raw message records and immutable case events for auditability.
• Minimize what is sent to LLMs; avoid unnecessary financial detail in prompts where possible.
• Provide a disconnect flow that revokes Drive access and purges cached operational artifacts according to retention policy.
15. Rollout Plan
• Phase 0: concierge pilot with 5–10 businesses; manual file mapping and close inspection of parse quality.
• Phase 1: closed beta MVP with one Drive source per tenant, daily brief, customer drilldowns, and update logging.
• Phase 2: self-serve mapping reuse, better voice support, folder mode, and stronger operational analytics.
16. Final Technical Recommendation
• Keep raw source data in Google Drive.
• Use PostgreSQL as the backbone for fast retrieval and event history.
• Use Redis and simple background workers for scheduling and sync jobs.
• Do not introduce a vector database in MVP.
• Treat retrieval UX as a data-modeling and indexing problem first, not an AI problem.
• Use AI narrowly for extraction and response polish, with strong confidence thresholds and correction loops.
