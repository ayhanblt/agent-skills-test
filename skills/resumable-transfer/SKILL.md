---
name: resumable-transfer
description: Implement resumable byte transfers with integrity, durable offsets and recovery after interrupted acknowledgements.
---

# Resumable Transfer

Define which offset is durable and which bytes it covers. Validate offset, chunk identity and digest before acknowledging any progress. Reject gaps and conflicting overlaps. Replaying an identical committed chunk should return the existing committed offset rather than append it twice.

Place the acknowledgement after the required durable commit. Atomic metadata replacement and fsync can matter for a real filesystem; use the project's storage adapter and its declared durability boundary. On recovery, reconcile persisted bytes and metadata; never trust only a client's claimed offset. Finalize only when length and whole-file digest agree. Preserve source data on validation failure and avoid silently resetting an incomplete transfer. Test interruption before and after commit, lost acknowledgement, duplicate chunks, corruption and restart. Do not add a network service or external storage if the project requires local operation.
