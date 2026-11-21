---
name: payment-reconciliation-specialist
description: Use when implementing signed payment webhooks, reliable provider event processing, or financial reconciliation and immutable double-entry ledgers.
---

# Payment reconciliation

1. Separate protocol authenticity from event identity. Capture the raw byte sequence once, bound its size, verify the keyed digest over the exact provider-defined signing input, then validate freshness and parse. Auth failures never enter the dedup queue. Test body transformations and legitimately signed duplicates separately.
2. For durable deduplication, identify what the unique key represents and what to do when the same identity carries different content. Keep the receipt of the event and its effect in the same database transaction. When interrupted before commit, the next legitimate retry must be equivalent to a first submission. Do all state-dependent reads under the transaction that performs the write.
3. Build an explicit accounting table linking business event types to their balanced legs. Use integer units, verify references and currency, and calculate available budget from the applied facts inside the write transaction. Reserve separate statuses for waiting on a missing dependency and permanently incompatible events.
4. For out-of-order events, apply deterministic eligible entries and recheck prerequisites when the transaction creates new facts. Ensure a waiting entry cannot starve unrelated eligible work. A reversal adds new compensating entries; it does not rewrite history. A provider timeout is an unknown outcome, not authorization to create a second capture.
5. Walk through same-id collision, duplicate delivery under concurrency, refund/reversal constraints, and failure after only the first would-be ledger leg. Use the project's actual protocol and accounts.
