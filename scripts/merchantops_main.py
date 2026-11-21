"""Launch the frozen MerchantOps V2 matrix, one isolated run at a time."""
import argparse
from collections import Counter
import fcntl
import json
import os
import subprocess
import sys
from pathlib import Path

import merchantops as runner
import merchantops_freeze as freeze

exp = runner.exp
MAIN = runner.ROOT/'runs/merchantops-v2'


class QuotaPause(Exception):
    """The provider declined an attempt because the subscription quota was exhausted."""


def quota_rejected(attempt):
    with (attempt/'session.jsonl').open(encoding='utf-8') as stream:
        for line in stream:
            try:
                event=json.loads(line)
            except ValueError:
                continue
            if (event.get('type')=='rate_limit_event'
                    and (event.get('rate_limit_info') or {}).get('status')=='rejected'):
                return True
    return False


def recover(attempt, row, plan):
    path = attempt/'manifest.json'
    index = attempt/'evidence-index.json'
    if not (path.is_file() and index.is_file()):
        command = attempt/'command.json'
        if command.is_file():
            args = exp.read(command)
            scratch = Path(args[args.index('--settings')+1]).parent.parent
            if scratch.exists():
                raise ValueError(f'Previous attempt still has an active workspace: {attempt.name}')
        return None
    raw = exp.read(path)
    if (raw['input_id']!=plan['input_id'] or raw['snapshot_id']!=plan['snapshots'][row['task']]
            or raw['requested_model']!=row['model'] or raw['task']!=row['task']
            or raw['condition']!=row['condition'] or raw['web_tools_enabled']!=row['web_enabled']):
        raise ValueError(f'Attempt differs from frozen row {row["id"]}')
    if exp.read(index).get('manifest.json')!=exp.sha(path):
        raise ValueError(f'Run manifest integrity mismatch: {attempt.name}')
    event = runner.terminal_result(attempt/'session.jsonl') or {}
    if raw.get('session_ok') and raw.get('status')=='evaluated':
        if raw['actual_models']!=[row['model']]:
            raise ValueError(f'Unexpected model in row {row["id"]}')
        status='evaluated'
    elif (raw.get('failure_reason')=='timeout' or event.get('subtype')=='error_max_turns') and not quota_rejected(attempt):
        status='budget-exhausted'
    else:
        return None
    return dict(raw, id=row['id'], rep=row['rep'], phase='main', pilot=False, status=status,
                raw_attempt=str(attempt.relative_to(attempt.parent.parent)),
                raw_index_sha256=exp.sha(index))


def complete_row(slot, row, plan):
    manifest=slot/'manifest.json'
    if manifest.is_file():
        saved=exp.read(manifest)
        if saved!=recover(slot/saved['raw_attempt'],row,plan):
            raise ValueError(f'Main manifest integrity mismatch: {row["id"]}')
        return

    attempts=slot/'attempts'
    previous=sorted(attempts.glob('merchantops-v2-*'),key=lambda path:path.stat().st_mtime,reverse=True)
    for attempt in previous:
        result=recover(attempt,row,plan)
        if result is not None:
            exp.save(manifest,result)
            return

    print(f'{row["id"]}/72 · {row["model"]} · {row["task"]}/{row["condition"]} · repeat {row["rep"]}',flush=True)
    # Route the unchanged, frozen candidate harness to this main run's evidence directory.
    original=runner.PILOTS
    try:
        runner.PILOTS=attempts
        attempt,raw=runner.run_agent(row['task'],row['condition'],row['model'])
    finally:
        runner.PILOTS=original
    result=recover(attempt,row,plan)
    if result is None:
        reason=raw.get('failure_reason') or 'session could not be evaluated'
        if quota_rejected(attempt) or ('limit' in reason.lower() and 'resets' in reason.lower()):
            raise QuotaPause(f'Row {row["id"]} remains pending. {reason}')
        raise ValueError(f'Row {row["id"]} stopped: {reason}')
    exp.save(manifest,result)


def summary(plan):
    rows=[]
    for row in plan['matrix']:
        manifest=MAIN/row['id']/'manifest.json'
        record=exp.read(manifest) if manifest.is_file() else {}
        rows.append(dict(row,status=record.get('status','pending'),functional_success=record.get('functional_success')))
    counts=dict(Counter(row['status'] for row in rows))
    exp.save(MAIN/'summary.json',{'input_id':plan['input_id'],'counts':counts,'rows':rows})
    print('Main runs:',counts,flush=True)


def launch(plan):
    MAIN.mkdir(parents=True,exist_ok=True)
    with (MAIN/'.run-lock').open('a') as lock:
        try:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise SystemExit('A MerchantOps main batch is already running') from error
        try:
            for row in plan['matrix']:
                if runner.fingerprint()!=plan['input_id']:
                    raise ValueError('Frozen MerchantOps inputs changed during the batch')
                complete_row(MAIN/row['id'],row,plan)
        finally:
            summary(plan)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--extension', action='store_true', help='Select the 36-run extension')
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--plan',action='store_true',help='Check the freeze and print the schedule without model calls')
    mode.add_argument('--run',action='store_true',help='Run all remaining frozen rows')
    mode.add_argument('--status', action='store_true', help='Show extension progress')
    options=parser.parse_args()
    # Resolve tools in the same order as the frozen candidate environment.
    os.environ['PATH']=os.pathsep.join((str(runner.CLAUDE.parent),'/opt/homebrew/bin',
                                        '/usr/local/bin',os.environ.get('PATH',os.defpath)))
    if options.extension:
        entry = runner.ROOT / 'provenance/merchantops-v2-extension/run.py'
        action = '--plan' if options.plan else '--status' if options.status else '--run'
        raise SystemExit(subprocess.call([sys.executable, str(entry), action]))
    if options.status:
        parser.error('--status requires --extension')
    plan=exp.read(freeze.LOCK)
    freeze.check(plan)
    if options.plan:
        for row in plan['matrix']:
            print(row['id'],row['model'],row['task'],row['condition'],row['rep'],
                  'web' if row['web_enabled'] else 'local')
    else:
        try:
            launch(plan)
        except QuotaPause as error:
            parser.exit(os.EX_TEMPFAIL,
                        f'{error}\nAfter the quota resets, resume with: python3 scripts/merchantops_main.py --run\n')


if __name__=='__main__':
    main()
