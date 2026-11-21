# Ledger fixture v1

POST /api/financial-events with id, paymentId, kind, amount, currency, ref (null except reversal). For all kinds amount is an integer in [1,100000000] and currency is USD matching the payment. Unknown payment is 404. Malformed/unsupported events are 400. GET /api/ledger/{paymentId} returns journal rows (eventId, account, debit, credit, currency), in application order with debit before credit, or 404. Payment state remains independent of the ledger apart from an uncertain event's status check.

| kind | debit | credit | prerequisites |
|---|---|---|---|
| capture | processor | merchant | one per payment, amount equals payment amount |
| uncertain | processor | merchant | same capture semantics, but check local provider status; 202 while pending and retry same event after the provider reports paid |
| refund | merchant | processor | capture exists, total refunds cannot exceed captured amount; no active settlement |
| settle | cash | processor | capture exists and amount equals captured minus refunded; no active settlement |
| reverse | processor | cash | ref identifies one applied settlement for this payment, amount equals it and it was not reversed |

Refund, settle and reverse with a missing prerequisite are durably queued and return 202. After any applied event drain eligible waiting entries for that payment in original arrival order, repeating until no progress; an ineligible entry does not block eligible later entries. If it becomes impossible under the business rules, mark it rejected without ledger rows. An incompatible, nonwaiting event returns 409. A reverse pointing to a known wrong-kind or wrong-payment event is incompatible. Identical event replay returns current status (200 applied, 202 waiting, 409 rejected) and never adds a second pair. Same ID with changed payload is 409. An uncertain event pending provider status is rechecked only when the same event is posted again. Reject stale or over-limit state in the same transaction as the ledger and event changes.

Ledger rows are immutable after commit, including against UPDATE and DELETE at the storage boundary. Each applied event must add exactly two equal and opposite rows in one transaction. In local fault mode, X-Simulate-Fault: ledger-after-debit returns 503 after inserting the first row and before inserting the second; the whole request, including status and any drained entries, rolls back. Retry must work.
