---
name: react-async-patterns
description: Implement React asynchronous search and shared cache lifecycles, including stale results, cancellation and retries.
---

# React Async Patterns

Separate the identity of a request from the order in which its promise settles. Guard every asynchronous write, including errors and finally handlers, against superseded generations. Abort is a resource optimization; correctness must survive transports that ignore abort. Clean up subscriptions on unmount.

For shared caches, distinguish subscriber lifetime from request lifetime. Do not let one component cancel work still needed by another. Tag retries with a new generation; an old completion must not replace it or clear its loading state. Prefer the project's cache and subscription API. Libraries are useful when already approved, but a small application may require no new dependency. Verify behavior under React Strict Mode, key changes, unmounts, reverse completion order and stale rejection. Use deferred promises rather than sleeps to control races.
