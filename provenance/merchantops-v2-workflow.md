# MerchantOps V2

MerchantOps runs on macOS using the existing research repository. The V1 runner, tasks and pilot evidence are unchanged. The V2 starter lives in `tasks/merchantops`; task contracts and the T6 Core overlay share the existing `tasks/T1`–`tasks/T6` hierarchy. Independently built references live under `selfcheck/merchantops`, and tests under `private-tests/merchantops`. Neither is copied into an agent workspace. T2 starts with the same independent local payments simulator as the starter. T6 starts with the verified T5 Core + Creation implementation, never an earlier experimental run.

Run these commands from the project root:

```sh
npm ci --prefix tasks/merchantops/web
python3 scripts/merchantops.py verify
python3 scripts/merchantops.py preflight
python3 scripts/merchantops.py pilot-batch
python3 scripts/merchantops.py judge
```

Preflight uses the normal locally authenticated Claude subscription in `.local/merchantops-auth` and the existing TypeSafe key. The Claude process uses its supported login. Its Bash tool has strict native macOS isolation, and file tools have explicit denials for project records and private files. A harmless canary must be denied by both Bash and Read before pilots start. Build and evaluation subprocesses use a separate restrictive macOS profile, with loopback-only evaluation networking. Pilot artifacts are Git-ignored in `pilot/`, `scoring/`, and `reports/`.

The corrected pilot writes under `merchantops-v2-recheck` in those directories. The first calibration and its diagnosis retain their original paths. All revised runs pin the .NET polling watcher and a per-run Claude scratch directory. Preflight starts a real API in each model's Bash tool, checks loopback health, and verifies that the runner removes the detached server before evaluation or the next run.

T6 now combines its server implementation with a public document delivery, using the same task identifier. The prompt includes a search phrase and document description. The accepted source and file digest are checked independently. A loopback-only document box forwards requests to the candidate API and drops the first successful partial upload response. The box records the offset check, continuation on the same upload, and completed bytes. The server tests, document discovery, and recovery trace are reported separately. Web access is enabled for T6 only, with downloads restricted to the public NASA Science host.

Evaluation retains the first log and retries once when VSTest reports its known portable symbol reader crash. A repeated adapter crash stops evaluation as an infrastructure error. Ordinary failed assertions are scored without retry.

A installs no study skill. B installs only the matching specialist skill and logs detected natural Skill invocation. C installs the same skill and supplies its exact bytes in appended system context before the equal user prompt. This is controlled content delivery, not a claim of a native Skill tool invocation. The separate smoke test checks the native Skill path. Candidate output, code, identity, skill load, time, usage, API-equivalent estimate and tests are retained. No actual per-run subscription charge is inferred.

The updated T6 pilot rechecks six model/condition cells under `merchantops-v2-t6-web`. T2 and T4 evidence from the prior pilot stays under `merchantops-v2-recheck`. No model or condition identity is sent to Jev. T6 full success requires the independent server tests and the observed document delivery. The main plan remains 72 runs, with 12 for T6.

## Frozen main experiment

Run from the project root.

```sh
python3 scripts/merchantops_main.py --plan
python3 scripts/merchantops_main.py --run
```

The first command validates the freeze and lists the 72 rows without invoking Claude. The second runs the fixed order, writes a per-row manifest and raw attempt evidence under `runs/merchantops-v2/`, and updates `summary.json`. A completed row stays complete on restart. The agent time or turn limit is recorded as a separate terminal outcome. An infrastructure or subscription failure stops the batch with that row pending, so the same command can resume after recovery.
