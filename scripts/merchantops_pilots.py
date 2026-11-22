"""Single entry point for the 18 T7–T9 and 36 T10–T15 pilot runs."""
import argparse
from contextlib import ExitStack
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import time

PROJECT = Path(__file__).resolve().parents[1]
OLD = PROJECT/'provenance/merchantops-followup-v1/pilot-v1/run.py'
RUNTIME = PROJECT/'.local/pilot-tools'
PYTHON = RUNTIME/'python/bin/python3'
CHROME = RUNTIME/'chrome/chrome-headless-shell'
REFERENCE = PROJECT/'private-tests'
FREEZE = PROJECT/'provenance/pilot-t10-t15.json'
SKILL_PIN = PROJECT/'provenance/pilot-skill-sources.json'
RUNS = PROJECT/'pilot'
TASKS = dict(zip((f'T{i}' for i in range(10,16)),
                 ('pdf','xlsx','remotion-best-practices','playwright-cli',
                  'supabase-postgres-best-practices','systematic-debugging')))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


old = load('pilot_t7_t9', OLD)


def matrix():
    rows = [dict(task=t, target_skill=s, condition=c, model=m, repeat=1)
            for t,s in TASKS.items() for c in 'ABC' for m in old.MODELS]
    random.Random(20261122).shuffle(rows)
    for i,row in enumerate(rows,1):
        row['run_id'] = f'P-{i+18:02}'
    return rows


def starter(task):
    return PROJECT/'tasks'/task/'starter'


def ready(row):
    return (RUNS/row['run_id']/'complete.json').is_file()


def tool_path(inherited):
    # Terminal shells do not all load Homebrew or Claude's per-user bin directory.
    entries = [str(Path.home()/'.local/bin'), '/opt/homebrew/bin', '/opt/homebrew/sbin',
               '/usr/local/bin', '/usr/bin', '/bin', '/usr/sbin', '/sbin']
    entries.extend(path for path in inherited.split(os.pathsep) if path)
    return os.pathsep.join(dict.fromkeys(entries))


def baseline(runner):
    public = [p for t in TASKS for p in starter(t).iterdir() if p.is_file()]
    private = [REFERENCE/'pilot_grade.py',REFERENCE/'pilot-T12.json',
               PROJECT/'scripts/merchantops_pilots.py',PROJECT/'scripts/merchantops_pilot_selfcheck.py',
               SKILL_PIN, PROJECT/'provenance/pilot-npm-lock.json', PROJECT/'provenance/pilot-python.lock',
               *sorted((PROJECT/'selfcheck').glob('pilot-*'))]
    skill_files = [p for name in TASKS.values() for p in (RUNTIME/'skills'/name).rglob('*') if p.is_file()]
    assert all((RUNTIME/'skills'/name/'SKILL.md').is_file() for name in TASKS.values())
    lock = PROJECT/'provenance/pilot-npm-lock.json'
    assert old.digest(lock) == old.digest(RUNTIME/'npm/package-lock.json')
    packages = subprocess.check_output([PYTHON,'-c',
        'import importlib.metadata as m; print("\\n".join(sorted((d.metadata["Name"].lower()+"=="+d.version) for d in m.distributions())))'],
        text=True).splitlines()
    assert packages == (PROJECT/'provenance/pilot-python.lock').read_text().splitlines()
    runtime = {}
    for cmd in (['node','--version'],['ffmpeg','-version'],['ffprobe','-version'],
                ['postgres','--version'],[PYTHON,'--version']):
        line = subprocess.check_output(cmd,text=True).splitlines()[0]
        runtime[Path(cmd[0]).name] = line
    return {'schema':1, 'matrix':matrix(),'files':{str(p.relative_to(PROJECT)):old.digest(p)
            for p in sorted(public+private+skill_files)},'runtime':runtime,'ocr_sha256':old.digest(RUNTIME/'ocr'),'pilot_headless_sha256':old.digest(CHROME),'browser_runtime':runner.runtime()}


def local_env(runner, stage, work):
    safe = {k:v for k,v in runner.env().items() if k in ('PATH','LANG','LC_ALL','TZ')}
    chrome = str(CHROME)
    settings = dict(safe, HOME=str(stage),TMPDIR=str(stage),
                    PATH=f'{RUNTIME}/python/bin:{RUNTIME}/npm/node_modules/.bin:'+tool_path(safe.get('PATH','')),
                    PILOT_CHROME=chrome, PLAYWRIGHT_MCP_EXECUTABLE_PATH=chrome,
                    PYTHONDONTWRITEBYTECODE='1')
    if work.name == 'work':
        (work/'node_modules').symlink_to(RUNTIME/'npm/node_modules',target_is_directory=True)
    return settings


def grade_candidate(grade, row, work, env):
    dispatch = {'T10':grade.t10, 'T11':grade.t11,
                'T12':lambda w,e: grade.t12(w,e,REFERENCE),
                'T13':grade.t13, 'T14':lambda w,e:grade.t14(w,e,starter('T14')),
                'T15':lambda w,e:grade.t15(w,e,starter('T15'))}
    try:
        return dispatch[row['task']](work,env)
    except (ValueError, OSError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError) as error:
        return {'evaluation_error': type(error).__name__, 'detail': str(error)[:750]}


def execute(runner, grade, row, attempt):
    started = time.monotonic()
    task, condition, skill = (row[k] for k in ('task','condition','target_skill'))
    with tempfile.TemporaryDirectory(prefix='p10-',dir='/private/tmp') as folder, ExitStack() as stack:
        stage = Path(folder)
        work = stage/'work'
        shutil.copytree(starter(task),work)
        direct = local_env(runner,stage,work)
        if task == 'T10':
            shutil.copyfile(RUNTIME/'ocr',work/'ocr')
            (work/'ocr').chmod(0o755)
        target = work/'.claude/skills'/skill
        if condition != 'A':
            shutil.copytree(RUNTIME/'skills'/skill,target)
        tools = ['Read','Bash','Write','Edit','Glob','Grep'] + (['Skill'] if condition != 'A' else [])
        network = {'allowedDomains':['127.0.0.1','localhost'] if task in ('T12','T13') else [],
                   'allowLocalBinding':task in ('T12','T13')}
        agent_extra = {}
        if task == 'T13':
            agent_extra['BASE_URL'], trace = stack.enter_context(grade.event_app())
        if task == 'T14':
            dbdir = stage/'db'; dbdir.mkdir()
            db, socket = stack.enter_context(grade.database(dbdir,direct))
            grade.sql(work,db,(starter(task)/'schema.sql').read_text())
            grade.sql(work,db,'ALTER TABLE reservation OWNER TO candidate')
            agent_extra.update({k:db[k] for k in ('PGHOST','PGDATABASE','PGPORT')})
            agent_extra['PGUSER'] = 'candidate'
            network['allowUnixSockets'] = [str(socket)]
        home = str(Path.home())
        settings = stage/'settings.json'
        mcp = stage/'mcp.json'
        runner.save(mcp,{'mcpServers':{}})
        hidden = [str(PROJECT/'private-tests'),str(PROJECT/'provenance'),str(PROJECT/'pilot'),str(PROJECT/'runs'),
                  str(PROJECT/'reports'),str(PROJECT/'scoring'),str(RUNTIME/'skills'),str(PROJECT/'selfcheck')]
        deny = ['Agent','Task','WebSearch','WebFetch','Skill(init *)','Skill(security-review *)']
        deny += [f'{tool}(/{path}/**)' for path in hidden for tool in ('Read','Grep','Glob','Edit','Write')]
        config = {
                    'permissions':{'defaultMode':'dontAsk','allow':tools,'deny':deny},
                    'sandbox':{'enabled':True,'failIfUnavailable':True,'allowUnsandboxedCommands':False,
                    'autoAllowBashIfSandboxed':True,
                    'filesystem':{'denyRead':[home,*hidden,str(stage/'db/pg')],
                                  'allowRead':[str(RUNTIME/'python'),str(RUNTIME/'npm'),
                                               str(CHROME.parent),
                                               str(runner.AUTH),str(Path.home()/'.local/bin'),
                                               str(work)],
                                  'allowWrite':[str(work)], 'denyWrite':[str(work/'.claude')]},
                    'network':network}}
        old.isolate_skill_settings(config,condition)
        runner.save(settings,config)
        cmd = runner.arguments(row['model'],','.join(tools),settings,mcp,22)
        prompt = (work/'TASK.md').read_text()
        (attempt/'prompt.txt').write_text(prompt)
        if condition == 'C':
            prompt = old.skill_policy(row,attempt/'prompt.txt',prompt)
            cmd.extend(['--append-system-prompt-file',str(target/'SKILL.md')])
        configuration = runner.env()
        configuration.update({k:v for k,v in direct.items() if k != "HOME"})
        configuration.update(agent_extra)
        configuration = old.isolated_skill_env(configuration)
        with (attempt/'session.jsonl').open('w') as record:
            events, result = runner.agent_call(cmd,prompt,work,configuration,record)
        with (attempt/'session.jsonl').open() as record:
            old.audit_skills(row,record)
        models = {event['message'].get('model') for event in events if event.get('type')=='assistant'
                  and isinstance(event.get('message',{}).get('model'),str)
                  and event['message']['model'].startswith('claude-')}
        if models != {row['model']}:
            raise ValueError('Candidate model identity did not match')
        (attempt/'answer.md').write_text(result.get('result') or '')
        artifacts = attempt/'artifacts'; artifacts.mkdir()
        for file in work.rglob('*'):
            relative = file.relative_to(work)
            if (not file.is_file() or file.is_symlink() or not file.resolve().is_relative_to(work)
                or any(p.startswith('.') or p in ('node_modules','__pycache__') for p in relative.parts)
                or (starter(task)/relative).is_file() and old.digest(file) == old.digest(starter(task)/relative)
                or file.stat().st_size > 32*1024*1024):
                continue
            destination = artifacts/relative
            destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(file,destination)
        measured = grade_candidate(grade,row,work,direct)
        outcome = {'row':row,'actual_model':next(iter(models)),'skill_isolation_verified':True,
                   'target_skill_calls':[a.get('input',{}).get('skill') for e in events
                       for a in e.get('message',{}).get('content',[]) if isinstance(a,dict) and a.get('name')=='Skill'],
                   'preload_sha256':old.digest(target/'SKILL.md') if condition=='C' else None,
                   'metrics':measured, 'telemetry':{'usage':result.get('usage'),
                      'api_equivalent_cost_usd':result.get('total_cost_usd'),'seconds':time.monotonic()-started},
                   'terminal_subtype':result.get('subtype'), 'attempt':attempt.name}
        return outcome


def main():
    parser = argparse.ArgumentParser()
    some = parser.add_mutually_exclusive_group(required=True)
    for arg in ('plan','status','preflight','run'):
        some.add_argument('--'+arg,action='store_true')
    args = parser.parse_args()
    rows = matrix()
    if args.status:
        old_count = sum((old.RUNS/r['run_id']/'complete.json').is_file() for r in old.rows())
        new_count = sum(map(ready,rows))
        print(f'{old_count+new_count}/54 · T7–T9 {old_count}/18 · T10–T15 {new_count}/36')
        return
    if args.plan:
        print('T7–T9')
        for r in old.rows()+rows:
            print(r['run_id'],r['task'],r['condition'],r['model'])
        return
    if not PYTHON.is_file():
        raise SystemExit('Missing .local/pilot-tools; see README.md for setup.')
    if Path(sys.prefix) != PYTHON.parent.parent:
        os.execv(str(PYTHON),[str(PYTHON),__file__,*sys.argv[1:]])
    os.environ['PATH'] = tool_path(os.environ.get('PATH', ''))
    runner = old.harness()
    try:
        current = baseline(runner)
    except FileNotFoundError as error:
        raise SystemExit(f"Required pilot tool not found: {error.filename}. See provenance/pilot.md.") from None
    if current != old.json_file(FREEZE):
        raise SystemExit('T10–T15 pilot files or runtime differ from the recorded pilot setup.')
    if args.preflight:
        subprocess.run([sys.executable,str(OLD),'--preflight'],check=True)
        subprocess.run([sys.executable,str(PROJECT/'scripts/merchantops_pilot_selfcheck.py')],check=True)
        return
    RUNS.mkdir(exist_ok=True)
    with (RUNS/'.batch.lock').open('a') as lock:
        try:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('Pilot batch already active') from None
        upstream = subprocess.run([sys.executable,str(OLD),'--run'])
        if upstream.returncode:
            raise SystemExit(upstream.returncode)
        grade = load('pilot_grade',REFERENCE/'pilot_grade.py')
        for row in rows:
            if ready(row):
                continue
            slot = RUNS/row['run_id']
            slot.mkdir(exist_ok=True)
            attempt = Path(tempfile.mkdtemp(prefix='attempt-',dir=slot))
            print(row['run_id'],row['task'],row['condition'],row['model'],flush=True)
            try:
                outcome = execute(runner,grade,row,attempt)
            except Exception as exc:
                # Avoid persisting CLI error payloads, which can include account information.
                runner.save(attempt/'failure.json',{'row':row,'error_type':type(exc).__name__})
                raise SystemExit(f"{row['run_id']} stopped ({type(exc).__name__}). Resume with --run.") from None
            runner.save(attempt/'result.json',outcome)
            runner.save(slot/'complete.json',outcome)


if __name__ == '__main__':
    main()
