# T1 — Signed provider webhook
Upgrade the existing webhook endpoint according to docs/provider-v1.md. Keep the payment and provider status endpoints working. Use raw bytes, sign before parsing, and make deduplication durable and atomic with the state update. Do not add a new library or modify the pinned fixture documentation. Run or add local tests.
