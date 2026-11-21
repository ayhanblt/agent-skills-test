---
name: react-consistency-specialist
description: Use for TanStack Query v5 optimistic payments, concurrent mutations and cache consistency, or HTTP ETag and If-Match editor conflicts.
---

# React consistency

- Inventory the query keys that show the same server facts and the monotonic version or aggregate that makes late responses detectable. Treat abort as insufficient for correctness when work can settle anyway.
- In TanStack Query v5, let onMutate cancel relevant reads before a speculative update. Return per-operation context for onError/onSettled. With concurrent work, a single whole-cache snapshot rollback can erase a separate success. Track each operation, remove only its contribution, and reconcile both detail and list against the latest authoritative fact once overlapping work settles. Explicit retry creates a new attempt at a known failed operation rather than resending successful writes.
- Store the validator alongside the editor's initial snapshot; an unrelated refetch cannot retag an existing edit. On the API, use strong If-Match comparison and evaluate it inside the same write guard that advances the revision. A failed predicate leaves current data untouched.
- On conflict, retain draft fields, refresh canonical data, and require a deliberate user action to edit or resubmit against a newer validator. Carry the revision beside mutation and query results; an older response should not overwrite a newer revision in any subscribed cache.
- Test with deferred promises and two actors: optimistic success plus failed peer, stale refetch, stale tag, explicit rebase, stale mutation response. Check accessible error and retry controls.
