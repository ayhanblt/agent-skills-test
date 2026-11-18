---
name: payment-reliability
description: Design reliable payment processing with idempotency, ambiguous outcomes, retries and webhook reconciliation.
---

# Payment Reliability

Map the payment state machine before changing code. Treat a timeout as an unknown outcome, not proof of failure. Keep a stable provider idempotency key across retries. Bind the key to a canonical request fingerprint and reject reuse for a different request. Coordinate in-flight duplicates and persist the operation identity at the durability boundary required by the application. Distinguish replayable business rejection from transport failure. Reconcile duplicate and out-of-order events using provider versions or authoritative lookup rather than arrival time. Avoid holding unrelated payments behind one global lock.

Use the project's existing store and transaction facilities. A database unique key plus transaction is a common production solution; do not introduce a database when the project contract supplies another persistence boundary. Never log raw payment credentials. Exercise concurrent duplicates, retries after an unknown outcome, and event reordering with controllable schedules. Document the guarantee boundary; do not claim cross-process exactly-once without durable coordination.
