---
name: resumable-upload-protocol-specialist
description: Use for tus 1.0.0 resumable HTTP uploads, Creation and Checksum extensions, byte offsets, or durable crash recovery.
---

# Resumable upload protocol

- First map method, mandatory headers, body boundaries and response headers from the declared tus version. OPTIONS describes only implemented extensions. HEAD exposes authoritative offset and must avoid caching. PATCH advances from the exact current offset, not the client's estimate. Retry after a missing ACK begins with HEAD; replay at an old offset conflicts.
- Bind persisted metadata to the authenticated owner and declared length. Validate integer lengths/offsets and body bounds without wraparound. Hold the same per-resource write guard while deciding the offset and updating bytes/metadata.
- In the Checksum extension, parse algorithm and base64 strictly, verify digest length, and hash exactly the incoming PATCH bytes. Treat an unknown algorithm or malformed header separately from a valid digest mismatch. Neither failure advances the durable offset.
- Establish a commit boundary and enumerate visibility at each failure point. For payload and metadata in separate stores, write bytes, flush them durably, commit metadata, then ACK. On restart a tail beyond committed metadata is speculative; distinguish it from a file shorter than committed metadata. Reconcile before accepting a write or handing out final bytes. Do not silently acknowledge corrupted committed state.
- Verify lost ACK, duplicate PATCH, bad checksum, interrupted writes and restart with actual bytes and offsets. Check the frozen protocol facts and local storage constraints before generalizing.
