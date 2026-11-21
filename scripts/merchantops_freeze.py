"""Seal and verify the native MerchantOps V2 main experiment plan."""
import argparse
from collections import Counter
from hashlib import sha256
import json
import os
from pathlib import Path
import random
import subprocess
import tempfile

import merchantops as m

exp = m.exp
ROOT = m.ROOT
LOCK = ROOT/'provenance/merchantops-v2-freeze.json'
TASKS = tuple(m.CONFIG['skills'])


def runtime():
    return {
        'claude_code': exp.call([m.CLAUDE,'--version']),
        'dotnet': exp.call(['dotnet','--version'],cwd=ROOT/'tasks/merchantops'),
        'node': exp.call(['node','--version']),
        'npm': exp.call(['npm','--version']),
    }


def matrix():
    rows = [dict(model=model,task=task,condition=condition,rep=rep,web_enabled=task=='T6')
            for model in exp.MODELS.values() for task in TASKS for condition in exp.CFG['conditions']
            for rep in range(1,exp.CFG['repetitions']+1)]
    counts = Counter((row['model'],row['task'],row['condition']) for row in rows)
    if len(rows)!=72 or len(counts)!=36 or set(counts.values())!={2}:
        raise ValueError('The approved experiment requires 72 runs with two repeats per cell')
    random.Random(exp.CFG['seed']).shuffle(rows)
    return [dict(id=f'{index:02}',**row) for index,row in enumerate(rows,1)]


def check(data):
    if data['input_id']!=m.fingerprint() or data['freeze_tool_sha256']!=exp.sha(Path(__file__)):
        raise ValueError('Frozen MerchantOps inputs changed')
    if data['matrix']!=matrix() or data['runtime']!=runtime():
        raise ValueError('Frozen matrix or runtime changed')
    for relative,digest in data['evidence'].items():
        if exp.sha(ROOT/relative)!=digest:
            raise ValueError(f'Frozen calibration evidence changed: {relative}')


def seal():
    if LOCK.exists():
        check(exp.read(LOCK))
        print(LOCK)
        return
    conditions = exp.CFG['conditions']
    pre = m.PILOTS/'merchantops-v2-preflight.json'
    validated = m.REPORTS/'validation/summary.json'
    correction_path = m.PILOTS/'observer-repair.json'
    correction = m.observer_repair()
    if correction.get('preflight_sha256')!=exp.sha(pre) or correction.get('validation_sha256')!=exp.sha(validated):
        raise ValueError('Current T6 verification and observer repair do not match')
    checks = exp.read(validated)['cases']
    if len(checks)!=14 or not all(case['verified'] for case in checks.values()):
        raise ValueError('The six tasks and references must be verified')
    preflight = exp.read(pre)
    if set(preflight['web_models'])!=set(exp.MODELS.values()):
        raise ValueError('Both models must pass T6 web preflight')
    evidence = [pre,validated,correction_path,m.REPORTS/'pilot-results.json',m.WEB_FIXTURE]
    for folder in preflight['web_models'].values():
        proof = m.PILOTS/folder/'manifest.json'
        if not exp.read(proof).get('web_smoke_passed'):
            raise ValueError('T6 public web capability was not verified')
        evidence.append(proof)
    old_report = ROOT/'reports/merchantops-v2-recheck/pilot-results.json'
    evidence.append(old_report)
    old_pilots = ROOT/'pilot/merchantops-v2-recheck'
    expected = {(model,task,c) for model in exp.MODELS.values() for task in ('T2','T4') for c in conditions}
    old_cells=set()
    for row in exp.read(old_report)['rows']:
        if row['task'] not in ('T2','T4'):
            continue
        base = old_pilots/row['run']
        path = base/'manifest.json'
        manifest = exp.read(path)
        if (not manifest.get('session_ok') or manifest.get('status')!='evaluated'
                or manifest.get('snapshot_id')!=checks[f"{row['task']}-starter"]['source_id']):
            raise ValueError(f'Invalid carried-forward pilot: {base.name}')
        old_cells.add((manifest['requested_model'],manifest['task'],manifest['condition']))
        evidence.extend((path,base/'evidence-index.json',base/'jev-evaluation.json'))
    cells = m.selected()
    if old_cells!=expected or set(cells)!={(model,'T6',c) for model in exp.MODELS.values() for c in conditions}:
        raise ValueError('Current T6 and unchanged T2/T4 pilot cells are incomplete')
    for base,row in cells.values():
        if row.get('snapshot_id')!=checks['T6-starter']['source_id']:
            raise ValueError(f'Wrong T6 snapshot: {base.name}')
        evidence.extend(base/name for name in ('manifest.json','evidence-index.json','jev-evaluation.json','delivery.json'))
    fixture = exp.read(m.WEB_FIXTURE)
    pdf = subprocess.check_output(['/usr/bin/curl','-fsS','--max-time','20','--max-filesize','1048576',fixture['source']])
    if len(pdf)!=fixture['bytes'] or sha256(pdf).hexdigest()!=fixture['sha256']:
        raise ValueError('The pinned T6 web document changed')
    with tempfile.TemporaryDirectory(prefix='merchantops-freeze-') as temporary:
        for task in TASKS:
            app = Path(temporary)/task
            m.materialize(ROOT,task,app)
            if m.source_id(app)!=checks[f'{task}-starter']['source_id']:
                raise ValueError(f'{task} source differs from the verified snapshot')
    tools = runtime()
    if tools['claude_code']!=preflight['harness']:
        raise ValueError('Claude Code changed after preflight')
    data = {
        'schema':'merchantops-v2-freeze/1','frozen_utc':exp.now(),'input_id':m.fingerprint(),
        'freeze_tool_sha256':exp.sha(Path(__file__)),'runtime':tools,'seed':exp.CFG['seed'],
        'mode':'sequential native macOS','effort':exp.CFG['effort'],'max_turns':m.CONFIG['max_turns'],
        'agent_timeout_seconds':m.CONFIG['timeout_seconds'],
        'conditions':{'A':'no skill','B':'installed for automatic selection','C':'exact skill content preloaded'},
        'models':exp.MODELS,'judge':{'model':exp.CFG['judge_model'],'passes':2,'confidence_threshold':0.8},
        'functional_scoring':{'T1-T5':'independent build, regressions and hidden tests',
                              'T6':'independent server tests and verified web-document delivery with resumed upload'},
        'snapshots':{task:checks[f'{task}-starter']['source_id'] for task in TASKS},
        't6_document':fixture,'matrix':matrix(),
        'evidence':{path.relative_to(ROOT).as_posix():exp.sha(path) for path in evidence},
    }
    check(data)
    with tempfile.NamedTemporaryFile(dir=LOCK.parent,prefix='merchantops-freeze-',encoding='utf-8',
                                     mode='w',delete=False) as output:
        staged=Path(output.name)
        try:
            json.dump(data,output,indent=2,ensure_ascii=False)
            output.write('\n')
            output.flush()
            os.fsync(output.fileno())
            os.link(staged,LOCK)
        finally:
            staged.unlink()
    print(LOCK)


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true',help='Verify an existing lock without writing')
    if parser.parse_args().check:
        check(exp.read(LOCK))
        print('Verified: 72 frozen MerchantOps V2 runs')
    else:
        seal()
