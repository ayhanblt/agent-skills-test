"""MerchantOps V2 pilot workflow. V1 runner and records remain in place."""
import argparse
from collections import Counter
from contextlib import ExitStack, suppress
import hashlib
import json
import os
from pathlib import Path
import random
import re
import shlex
import shutil
import signal
import statistics
import subprocess
import sys
import tempfile
import time
import uuid
from urllib.request import Request
import xml.etree.ElementTree as ET

import experiment as exp
from merchantops_eval import evaluate, clean_copy, hydrate_web, materialize
from merchantops_t6_web import assess_delivery, document_box
from merchantops_verify import verify, source_id

ROOT = exp.ROOT
CONFIG = exp.read(ROOT/'config/merchantops.json')
AUTH = ROOT/'.local/merchantops-auth'
CLAUDE = Path.home()/'.local/bin/claude'
EVIDENCE = 'merchantops-v2-t6-web'
PILOTS = ROOT/'pilot'/EVIDENCE
REPORTS = ROOT/'reports'/EVIDENCE
TASKS = ('T6',)
PLANNED = len(exp.MODELS)*len(TASKS)*3
WEB_FIXTURE = ROOT/'private-tests/merchantops/t6-web.json'
CATALOG = ROOT/'skills/merchantops'
SANDBOX = '/usr/bin/sandbox-exec'

def fingerprint():
    files={}
    for folder in ('tasks/merchantops','private-tests/merchantops','skills/merchantops','selfcheck/merchantops'):
        clean={'node_modules','bin','obj','dist','data','__pycache__','.DS_Store'}
        for base, dirs, names in os.walk(ROOT/folder):
            dirs[:] = [d for d in dirs if d not in clean]
            for name in names:
                p=Path(base)/name
                files[p.relative_to(ROOT).as_posix()]=exp.sha(p)
    for task in CONFIG['skills']:
        for p in (ROOT/f'tasks/{task}/merchantops').rglob('*'):
            if p.is_file():files[p.relative_to(ROOT).as_posix()]=exp.sha(p)
    for f in ('scripts/merchantops.py','scripts/merchantops_api_smoke.py','scripts/merchantops_t6_web.py','scripts/merchantops_eval.py',
              'scripts/merchantops_verify.py','scripts/experiment.py','config/merchantops.json','config/experiment.json'):
        files[f]=exp.sha(ROOT/f)
    return hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()

def env_for(run, live=False):
    env={k:v for k,v in os.environ.items() if not k.startswith(
        ('ANTHROPIC_', 'CLAUDE_CODE_', 'TYPESAFE_', 'OPENAI_', 'MO_'))}
    env['PATH']=os.pathsep.join((str(CLAUDE.parent),'/opt/homebrew/bin','/usr/local/bin',env.get('PATH','/usr/bin:/bin')))
    for key in ('TMPDIR','DOTNET_CLI_HOME','NUGET_HTTP_CACHE_PATH'):
        folder=run/key.lower()
        folder.mkdir(exist_ok=True)
        env[key]=str(folder)
    env.update(DOTNET_NOLOGO='1',DOTNET_CLI_TELEMETRY_OPTOUT='1',NUGET_PACKAGES=str(Path.home()/'.nuget/packages'),
               DOTNET_USE_POLLING_FILE_WATCHER='1', MSBUILDDISABLENODEREUSE='1',
               UseSharedCompilation='false', NO_COLOR='1')
    if live:
        env.update(CLAUDE_CONFIG_DIR=str(AUTH),CLAUDE_CODE_DISABLE_AUTO_MEMORY='1',
                   CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC='1', CLAUDE_CODE_TMPDIR=str(run),
                   ASPNETCORE_URLS='http://127.0.0.1:0')
    return env

def profile(run, live):
    # Use a writable temporary root, and deny readings of the user's home except pinned runtimes and a dedicated Claude login.
    def path_clause(kind,path):return f'({kind} {json.dumps(str(path.resolve()))})'
    home=Path.home()
    readable=[home/'.nuget/packages',CLAUDE.resolve().parent]
    for p in (shutil.which('node'),shutil.which('npm'),sys.executable):
        if p and Path(p).resolve().is_relative_to(home):readable.append(Path(p).resolve().parent.parent)
    clauses=['(version 1)','(allow default)',f'(deny file-read* {path_clause("subpath",home)})',
             '(allow file-read* '+' '.join(path_clause('subpath',p) for p in readable if p.exists())+')',
             '(deny file-write*)', '(allow file-write* '+path_clause('subpath',run)+')']
    # .NET uses this OS-wide directory for named synchronization primitives even with TMPDIR set.
    clauses.append('(allow file-write* (subpath "/private/tmp/.dotnet") (literal "/dev/null"))')
    if not live:
        clauses+=['(deny network*)','(allow network* (local ip "localhost:*"))','(allow network-outbound (remote ip "localhost:*"))']
    return '\n'.join(clauses)

def isolation(run, live, env):
    prefix=[SANDBOX,'-p',profile(run,live)]
    good=run/'allowed';good.write_text('allowed')
    result=subprocess.run([*prefix,'/bin/cat',str(good)],env=env,capture_output=True,text=True,timeout=10)
    if result.returncode or result.stdout!='allowed':raise ValueError('Native sandbox could not read its own workspace')
    for path in [ROOT/'.env',WEB_FIXTURE,ROOT/'private-tests/merchantops/ApiTests/LedgerTests.cs',CATALOG/'payment-reconciliation-specialist/SKILL.md',
                 ROOT/'selfcheck/merchantops/references/T2/api/Ledger.cs']:
        if path.exists():
            with path.open('rb'):
                test=subprocess.run([*prefix,'/bin/cat',str(path)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=10)
            if test.returncode==0:raise ValueError('Native sandbox did not protect experiment inputs')
    return prefix

def checked_auth():
    env = {k:v for k,v in os.environ.items() if not k.startswith(('ANTHROPIC_', 'CLAUDE_CODE_'))}
    env['CLAUDE_CONFIG_DIR']=str(AUTH)
    r=subprocess.run([CLAUDE,'auth','status'],env=env,capture_output=True,text=True)
    if r.returncode or json.loads(r.stdout).get('authMethod')!='claude.ai':
        raise ValueError('Sign into the dedicated MerchantOps Claude subscription profile first')
    version=exp.call([CLAUDE,'--version'])
    if not version.startswith(exp.CFG['harness_version']+' '):raise ValueError('Unexpected Claude Code version')
    return version

def message_parts(event):
    message = event.get('message')
    content = message.get('content') if isinstance(message,dict) else None
    return content if isinstance(content,list) else []

def terminal_result(path):
    with path.open('rb') as stream:
        stream.seek(max(0,path.stat().st_size-262144))
        for line in reversed(stream.readlines()):
            try: row=json.loads(line)
            except (ValueError,UnicodeDecodeError):continue
            if isinstance(row,dict) and row.get('type')=='result':return row
    return None

def stop_agent(child):
    with suppress(ProcessLookupError):
        os.killpg(child.pid,signal.SIGTERM)
    try:child.wait(timeout=3)
    except subprocess.TimeoutExpired:
        with suppress(ProcessLookupError):
            os.killpg(child.pid,signal.SIGKILL)
        child.wait()

def workspace_processes(run):
    # Match unique workspace paths, including Claude's per-run scratch directory.
    result=subprocess.run(['/usr/sbin/lsof','-w','-a','-u',str(os.getuid()),'-d','cwd,txt','-Fpn'],
                          capture_output=True,text=True,timeout=15)
    if result.returncode or not result.stdout:
        raise RuntimeError('Cannot inspect local process working directories')
    processes=set()
    pid=None
    for line in result.stdout.splitlines():
        if line.startswith('p'):
            pid=int(line[1:])
        if pid and line.startswith('n/') and Path(line[1:]).is_relative_to(run):
            processes.add(pid)
    return processes

def clean_workspace_processes(run, evidence):
    terminated=set()
    remaining=workspace_processes(run)
    for sig in (signal.SIGTERM,signal.SIGKILL):
        if not remaining:
            break
        for pid in remaining:
            with suppress(ProcessLookupError):
                os.kill(pid,sig)
                terminated.add(pid)
        deadline=time.monotonic()+3
        while remaining and time.monotonic()<deadline:
            time.sleep(.15)
            remaining=workspace_processes(run)
    exp.save(evidence,{'terminated_pids':sorted(terminated),'remaining_pids':sorted(remaining)})
    if remaining:
        raise RuntimeError('Processes still attached to the MerchantOps workspace')
    return sorted(terminated)

def wait_for_agent(child, stream_path, timeout):
    deadline = time.monotonic()+timeout
    while time.monotonic()<deadline:
        try:return {'exit_code':child.wait(timeout=min(3,max(0.1,deadline-time.monotonic())))}
        except subprocess.TimeoutExpired:pass
        ending=terminal_result(stream_path)
        if ending is None:
            continue
        try:child.wait(timeout=6)
        except subprocess.TimeoutExpired:
            stop_agent(child)
            return {'exit_code':child.returncode,'terminal_result_before_cleanup':not ending.get('is_error'),
                    'post_result_cleanup':ending.get('subtype')}
        return {'exit_code':child.returncode}
    stop_agent(child)
    return {'exit_code':child.returncode,'failure_reason':'timeout'}

def run_agent(task,condition,model, *, smoke=None):
    base=PILOTS/('merchantops-v2-'+(smoke+'-' if smoke else '')+uuid.uuid4().hex)
    base.mkdir(parents=True)
    (base/'launch').mkdir()
    (base/'capture').mkdir()
    stage='smoke' if smoke else 'pilot'
    skill=CONFIG['skills'][task]
    source=CATALOG/skill/'SKILL.md'
    version=checked_auth()
    web_delivery=task=='T6' and not smoke
    web_enabled=web_delivery or smoke=='web'
    with tempfile.TemporaryDirectory(prefix='mo-',dir='/private/tmp') as tmp, ExitStack() as lifecycle:
        run=Path(tmp).resolve();work=run/'app'
        launch=run/'control';launch.mkdir()
        events=run/'skill-events.jsonl'
        materialize(ROOT,task,work)
        identity=source_id(work)
        fixed=dict(os.environ,GIT_AUTHOR_DATE='2026-11-19T00:00:00Z',GIT_COMMITTER_DATE='2026-11-19T00:00:00Z')
        exp.call(['git','init','-q',work])
        exp.call(['git','-C',work,'add','.'])
        exp.call(['git','-C',work,'-c','user.name=Benchmark','-c','user.email=benchmark@example.invalid','commit','-qm','MerchantOps snapshot'],env=fixed)
        baseline=exp.call(['git','-C',work,'rev-parse','HEAD'])
        if condition!='A':shutil.copytree(source.parent,work/'.claude/skills'/skill)
        if condition=='C':
            shutil.copyfile(source,launch/'forced.md')
            shutil.copyfile(source,base/'launch/forced.md')
        hook=launch/'hook.py'
        hook.write_text('import json,sys\nfrom pathlib import Path\nwith Path('+repr(str(events))+').open("a",encoding="utf-8") as out:\n    out.write(json.dumps(json.load(sys.stdin))+"\\n")\n')
        protected = run/'protected'
        protected.mkdir()
        canary = protected/'canary.txt'
        sentinel = uuid.uuid4().hex
        canary.write_text(sentinel)
        home = Path.home()
        extra_read = [str(home/'.nuget/packages')]
        for name in ('node','npm'):
            tool = shutil.which(name)
            if tool and Path(tool).resolve().is_relative_to(home):
                extra_read.append(str(Path(tool).resolve().parent.parent))
        deny = [f'{tool}(/{path}/**)' for tool in ('Read','Edit') for path in (home,protected,launch)]
        tools=['Bash','Read','Edit','Write','Glob','Grep','Skill']
        web_permissions=['WebSearch','WebFetch(domain:science.nasa.gov)'] if web_enabled else []
        settings = {
            'model':model,'effortLevel':exp.CFG['effort'],
            'permissions':{'defaultMode':'dontAsk',
                'allow':tools+web_permissions,
                'deny':['Agent','Task',*deny]+([] if web_enabled else ['WebSearch','WebFetch'])},
            'sandbox':{'enabled':True,'failIfUnavailable':True,'allowUnsandboxedCommands':False,
                'autoAllowBashIfSandboxed':True,
                'filesystem':{'denyRead':[str(home),str(protected),str(launch)],'allowRead':extra_read,
                              'allowWrite':[str(run),'/private/tmp/.dotnet'],'denyWrite':[str(protected),str(launch)]},
                'network':{'allowedDomains':['science.nasa.gov'] if web_enabled else [],'allowLocalBinding':True}},
            'hooks':{}
        }
        for event in ('PreToolUse','PostToolUse','PostToolUseFailure'):
            settings['hooks'][event]=[{'matcher':'Skill','hooks':[{'type':'command','command':shlex.quote(sys.executable)+' '+shlex.quote(str(hook))}]}]
        exp.save(launch/'settings.json',settings)
        exp.save(launch/'mcp.json',{'mcpServers':{}})
        prompt='Read CONTRACT.md and CLAUDE.md, implement the requested feature, and run appropriate local checks. Summarize the changes and checks.'
        if smoke=='api':
            smoke_script=work/'merchantops_api_smoke.py'
            shutil.copyfile(ROOT/'scripts/merchantops_api_smoke.py',smoke_script)
            evidence_token=uuid.uuid4().hex
            smoke_command=f'{shlex.quote(sys.executable)} {shlex.quote(smoke_script.name)} {evidence_token}'
            prompt=f'Use Bash to run this exact command once: {smoke_command}\nThe harness will clean up the server. Then reply READY.'
        if smoke=='skill':prompt=f'Use the native Skill tool to load {skill}. Then reply READY. Do not implement this task.'
        if smoke=='web':
            prompt=('Use WebSearch to search for NASA Hubble mission. Then use Bash to run '
                    'curl -fsS --max-time 15 https://science.nasa.gov/mission/hubble/ '
                    '-o /dev/null && echo MERCHANTOPS_PUBLIC_READ_OK. Then reply READY.')
        if smoke=='isolation':
            prompt=(f'This is a synthetic sandbox check. Call the Read tool on {canary} once and call Bash with cat {canary} once. '
                    'This file contains only a generated test marker. The reads should be denied. Then reply READY.')
        (base/'prompt.txt').write_text(prompt+'\n')
        env=env_for(run,True)
        if web_delivery:
            expected=exp.read(WEB_FIXTURE)
            box,backend,trace=lifecycle.enter_context(document_box(expected['bytes']))
            env.update(MERCHANTOPS_DOCUMENT_BOX=box,MERCHANTOPS_DELIVERY_BACKEND=backend,
                       MERCHANTOPS_DELIVERY_DATA=str(run/'delivery-data'))
        prefix=isolation(run,True,env)
        if not smoke:
            hydrate_web(ROOT,work)
        if not smoke or smoke=='api':
            with (base/'restore.log').open('w') as log:
                subprocess.run([*prefix,'dotnet','restore','api','--locked-mode','-p:NuGetAudit=false'],
                               env=env,cwd=work,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=60)
        args=[str(CLAUDE.resolve()),'-p','--model',model,'--effort',exp.CFG['effort'],'--max-turns',
              str(6 if smoke else CONFIG['max_turns']),'--output-format','stream-json','--verbose',
              '--include-partial-messages','--setting-sources','project','--settings',str(launch/'settings.json'),
              '--strict-mcp-config','--mcp-config',str(launch/'mcp.json'),'--no-session-persistence','--no-chrome',
              '--permission-mode','dontAsk','--tools',','.join(tools+(['WebSearch','WebFetch'] if web_enabled else []))]
        if condition=='C':args+=['--append-system-prompt-file',str(launch/'forced.md')]
        args.extend(['--',prompt])
        m={'id':base.name,'task':task,'task_version':CONFIG['revision'],'phase':stage,'pilot':True,'condition':condition,
           'input_id':fingerprint(),'status':'running','started_utc':exp.now(),'requested_model':model,'harness_version':version,
           'auth_mode':'claude-subscription-oauth','effort_requested':exp.CFG['effort'],'effort_observed':None,
           'baseline_commit':baseline,'snapshot_id':identity,'prompt_sha256':exp.sha(base/'prompt.txt'),'skill':skill,
           'runtime_env':{k:env[k] for k in ('DOTNET_USE_POLLING_FILE_WATCHER','ASPNETCORE_URLS')},
           'web_tools_enabled':web_enabled,
           'skill_version':CONFIG['skill_version'],'skill_sha256':exp.sha(source),'skill_bytes':source.stat().st_size,
           'target_skill_installed':condition!='A','target_skill_visible':None,
           'c_loading_mechanism':'system-context preload of exact SKILL.md' if condition=='C' else None,
           'injected_skill_sha256':exp.sha(source) if condition=='C' else None,
           'telemetry':{'tokens':None,'cost_usd':None,'api_equivalent_cost_usd':None,'duration_ms':None,'wall_seconds':None},
           'functional_success':None,'project_violations':None,'jev':None,'human_intervention':None}
        exp.save(base/'manifest.json',m)
        exp.save(base/'command.json',args)
        print(base,flush=True)
        start=time.monotonic()
        with (base/'session.jsonl').open('w') as out,(base/'stderr.txt').open('w') as err:
            child=subprocess.Popen(args,cwd=work,env=env,stdout=out,stderr=err,start_new_session=True)
            try:m.update(wait_for_agent(child,base/'session.jsonl',75 if smoke else CONFIG['timeout_seconds']))
            except BaseException:
                stop_agent(child)
                raise
            finally:
                m['telemetry']['wall_seconds']=time.monotonic()-start
                try:m['detached_pids_terminated']=clean_workspace_processes(run,base/'process-cleanup.json')
                except Exception:
                    m.update(status='cleanup-failed',failure_reason='workspace process cleanup failed')
                    exp.save(base/'manifest.json',m)
                    raise
        m.update(status='captured',ended_utc=exp.now())
        if events.exists():shutil.copyfile(events,base/'capture/skill-events.jsonl')
        exp.save(base/'manifest.json',m)
        exp.capture(base)
        m=exp.read(base/'manifest.json')
        m['skill_tool_successes'] = [
            event for event in m['skill_events']
            if event.get('hook_event_name') == 'PostToolUse'
            and (event.get('tool_input', {}).get('skill', '').split() or [''])[0].split(':')[-1] == skill
        ]
        body = source.read_text().split('---', 2)[-1].strip()
        ready_pids=set()
        searches=set()
        public_read=False
        web_search_succeeded=False
        for line in (base/'session.jsonl').read_text().splitlines():
            try:event=json.loads(line)
            except ValueError:continue
            if event.get('type')=='system' and event.get('subtype')=='init':
                catalog=event.get('skills')
                if isinstance(catalog,list):m['target_skill_visible']=skill in catalog
            for part in message_parts(event):
                if isinstance(part,dict) and part.get('type') in ('tool_use','server_tool_use') and part.get('name') in ('WebSearch','web_search'):
                    searches.add(part['id'])
                if isinstance(part,dict) and part.get('type')=='web_search_tool_result':
                    web_search_succeeded=True
                if not isinstance(part,dict) or part.get('type')!='tool_result' or part.get('is_error'):
                    continue
                web_search_succeeded |= part.get('tool_use_id') in searches
                contents=part.get('content')
                value=contents if isinstance(contents,str) else '\n'.join(x.get('text','') for x in (contents or []) if isinstance(x,dict))
                if smoke=='api':
                    ready_pids.update(int(pid) for pid in re.findall(
                        rf'MERCHANTOPS_API_READY_{evidence_token}_(\d+)\b',value))
                if smoke=='web' and 'MERCHANTOPS_PUBLIC_READ_OK' in value.splitlines():
                    public_read=True
                value='\n'.join(re.sub(r'^\s*\d+[→\t]','',line) for line in value.splitlines())
                if body in value:
                    m['direct_skill_content_reads'].append({'skill':skill,'tool_use_id':part.get('tool_use_id')})
            if event.get('type')=='result' and event.get('is_error'):
                msg=event.get('result') or next((v for v in (event.get('errors') or []) if isinstance(v,str)),None)
                m['failure_reason']=(msg if isinstance(msg,str) and msg else event.get('subtype','agent error'))[:400]
        m['target_skill_loaded_observed'] = (
            bool(m['skill_tool_successes'] or m['direct_skill_content_reads'] or m.get('c_injection_verified'))
            if m['session_ok'] else None
        )
        m['skill_loaded_observed']=m['target_skill_loaded_observed']
        if smoke=='api':
            m['api_smoke_passed']=bool(ready_pids.intersection(m['detached_pids_terminated']))
        if web_enabled:
            m['web_search_calls']=len(searches)
        if smoke=='web':
            m['web_smoke_passed']=public_read and web_search_succeeded
        if smoke=='isolation':
            stream=(base/'session.jsonl').read_text()
            called = {}
            blocked = set()
            for line in stream.splitlines():
                try:row=json.loads(line)
                except ValueError:continue
                for part in message_parts(row):
                    if not isinstance(part,dict):continue
                    if part.get('type')=='tool_use' and str(canary) in json.dumps(part.get('input',{})):
                        called[part['id']]=part.get('name')
                    if part.get('type')=='tool_result' and part.get('is_error') is True:
                        blocked.add(part.get('tool_use_id'))
            m['sandbox_smoke_passed'] = sentinel not in stream and {'Read','Bash'}<={called[id] for id in blocked if id in called}
        if not smoke:
            scoped=['.',':(exclude).claude/skills',':(exclude)delivery.pdf',':(exclude)delivery.json']
            exp.call(['git','-C',work,'add','-N','--',*scoped])
            patch=subprocess.check_output(['git','-C',str(work),'diff','--binary',baseline,'--',*scoped])
            (base/'changes.patch').write_bytes(patch)
            paths=exp.call(['git','-C',work,'diff','--name-only',baseline,'--',*scoped]).splitlines()
            blocked=('CONTRACT.md','CLAUDE.md','global.json','.gitignore','web/package.json','web/package-lock.json','api/packages.lock.json','api/MerchantOps.csproj')
            m['project_violations']=[path for path in paths if path in blocked or path.startswith(('docs/','.claude/'))]
            if condition!='A' and (not (work/'.claude/skills'/skill/'SKILL.md').is_file() or exp.sha(work/'.claude/skills'/skill/'SKILL.md')!=exp.sha(source)):
                m['project_violations'].append('installed skill modified')
            clean_copy(work,base/'workspace')
        if web_delivery:
            lifecycle.close()
            delivery=assess_delivery(run,trace,expected)
            exp.save(base/'delivery.json',delivery)
            m.update({k:delivery[k] for k in ('research_success','resumed_same_upload','delivery_success')})
        exp.save(base/'manifest.json',m)
    if not smoke and m['session_ok']:
        with tempfile.TemporaryDirectory(prefix='merchantops-eval-') as tmp:
            work=Path(tmp).resolve();app=work/'app'
            clean_copy(base/'workspace',app)
            env=env_for(work)
            prefix=isolation(work,False,env)
            try:
                result=evaluate(ROOT,task,app,work/'logs',prefix=prefix,env=env)
            finally:
                if (work/'logs').exists():
                    shutil.copytree(work/'logs',base/'tests')
                clean_workspace_processes(work,base/'evaluation-cleanup.json')
        m.update(status='evaluated',server_success=result['functional_success'],
                 functional_success=result['functional_success'] and m.get('delivery_success',True),evaluation=result)
    exp.save(base/'manifest.json',m)
    exp.save(base/'evidence-index.json',{f.relative_to(base).as_posix():exp.sha(f) for f in sorted(base.rglob('*'))
             if f.is_file() and not f.is_symlink() and f.name!='evidence-index.json'})
    return base,m

def preflight():
    fixture=exp.read(WEB_FIXTURE)
    download=subprocess.check_output(['/usr/bin/curl','-fsS','--max-time','20','--max-filesize','1048576',fixture['source']])
    if len(download)!=fixture['bytes'] or hashlib.sha256(download).hexdigest()!=fixture['sha256']:
        raise ValueError('The public T6 artifact changed since the acceptance criteria were fixed')
    proofs={}
    web_proofs={}
    for model in exp.MODELS.values():
        path,record=run_agent('T2','A',model,smoke='api')
        if not (record['session_ok'] and record.get('api_smoke_passed')):
            raise ValueError(record.get('failure_reason') or f'Model API and cleanup smoke failed: {path.name}')
        proofs[model]=path.name
        path,record=run_agent('T6','A',model,smoke='web')
        if not (record['session_ok'] and record.get('web_smoke_passed')):
            raise ValueError(record.get('failure_reason') or f'Public web smoke failed: {path.name}')
        web_proofs[model]=path.name
    path,record=run_agent('T6','B',exp.MODELS['sonnet'],smoke='skill')
    if not (record['session_ok'] and record['skill_tool_successes']):
        raise ValueError(record.get('failure_reason') or f'Native Skill load smoke failed: {path.name}')
    sandbox_path,sandbox_record=run_agent('T2','A',exp.MODELS['sonnet'],smoke='isolation')
    if not (sandbox_record['session_ok'] and sandbox_record.get('sandbox_smoke_passed')):
        raise ValueError(f'Claude tool isolation smoke did not confirm both denials: {sandbox_path.name}')
    key=exp.typesafe_key()
    body={'model':exp.CFG['judge_model'],'state':'Verified synthetic fixture.', 'questions':exp.questions(False)}
    request=Request(exp.CFG['judge_endpoint'],data=json.dumps(body).encode(),
                    headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
    with exp.open_typesafe(request,timeout=60) as response:
        judge=json.load(response)
    if judge.get('model')!=exp.CFG['judge_model'] or not all(k in judge.get('answers',{}) for k in body['questions']):
        raise ValueError('Jev identity or schema mismatch')
    exp.save(PILOTS/'merchantops-v2-preflight.json',{'input_id':fingerprint(),'models':proofs,'web_models':web_proofs,'skill_smoke':path.name,'sandbox_smoke':sandbox_path.name,
        'judge_model':judge['model'],'harness':record['harness_version'],'utc':exp.now()})

def observer_repair():
    path=PILOTS/'observer-repair.json'
    note=exp.read(path) if path.is_file() else {}
    return note if note.get('input_id')==fingerprint() else {}

def selected():
    current=fingerprint()
    corrections=observer_repair().get('runs',{})
    cells={}
    for path in sorted(PILOTS.glob('merchantops-v2-*/manifest.json'),key=lambda p:p.stat().st_mtime):
        m=exp.read(path)
        correction=corrections.get(path.parent.name)
        retained=correction and correction['manifest_sha256']==exp.sha(path)
        if m['phase']=='pilot' and (m['input_id']==current or retained) and m.get('status')=='evaluated' and m.get('session_ok'):
            if retained:
                m.update(correction['delivery'],delivery_evidence=correction['basis'])
                m['functional_success']=m['server_success'] and m['delivery_success']
            cells[(m['requested_model'],m['task'],m['condition'])]=(path.parent,m)
    return cells

def run_pilots():
    if (ROOT/'freeze.json').exists():raise ValueError('An existing freeze must be reviewed before V2 pilots')
    current=fingerprint()
    correction=observer_repair()
    pre=PILOTS/'merchantops-v2-preflight.json'
    if not pre.exists() or (exp.read(pre)['input_id']!=current and correction.get('preflight_sha256')!=exp.sha(pre)):
        raise ValueError('Run current MerchantOps preflight first')
    validation=REPORTS/'validation'/'summary.json'
    if (not validation.exists() or (exp.read(validation).get('input_id')!=current
            and correction.get('validation_sha256')!=exp.sha(validation))
            or not all(v['verified'] for v in exp.read(validation)['cases'].values())):
        raise ValueError('Verify all independent snapshots/references first')
    finished=selected()
    schedule=[(model,task,c) for model in exp.MODELS.values() for task in TASKS for c in 'ABC']
    random.Random(exp.CFG['seed']).shuffle(schedule)
    exp.save(PILOTS/'merchantops-v2-schedule.json',[dict(model=m,task=t,condition=c) for m,t,c in schedule])
    for model,task,condition in schedule:
        if (model,task,condition) in finished:continue
        print(model,task,condition,flush=True)
        root,record=run_agent(task,condition,model)
        if not record['session_ok']:raise ValueError(record.get('failure_reason') or f'Pilot session failed: {root.name}')
        print('passed' if record['functional_success'] else 'failed hidden build/checks',flush=True)

def judge_pilots():
    """Reuse TypeSafe transport and reversed choices; judgments never override tests."""
    import re
    cells=selected()
    if len(cells)!=PLANNED:raise ValueError(f'Finish all {PLANNED} valid MerchantOps pilots before blind scoring')
    out=ROOT/'scoring'/EVIDENCE
    out.mkdir(parents=True,exist_ok=True)
    map_path=out/'key.json'
    mapping=exp.read(map_path) if map_path.is_file() else {uuid.uuid4().hex[:12]:p.name for p,_ in cells.values()}
    if set(mapping.values())!={p.name for p,_ in cells.values()}:raise ValueError('Pilot identities changed since blinding')
    exp.save(map_path,mapping)
    key=exp.typesafe_key()
    for pass_no,names in enumerate((sorted(mapping),sorted(mapping,reverse=True)),1):
        for name in names:
            base=PILOTS/mapping[name]
            task=exp.read(base/'manifest.json')['task']
            patch=(base/'changes.patch').read_text(errors='replace')
            # Keep evidence about loading out of the blind packet; it is assessed separately.
            patch=re.sub(r'/(?:Users|private/tmp|private/var/folders)/[^\s\'"<>]+','[local-path]',patch)
            if re.search(r'(?i)(sk-ant-[A-Za-z0-9_-]{20,}|https://[^\s/@]+:[^\s/@]+@)',patch):
                raise ValueError(f'Blind patch {name} requires manual credential redaction')
            if len(patch)>120_000:raise ValueError(f'Blind patch {name} needs review before sending')
            task_dir=ROOT/f'tasks/{task}/merchantops'
            rules=task_dir/'overlay/CLAUDE.md'
            if not rules.exists():rules=ROOT/'tasks/merchantops/CLAUDE.md'
            state=(task_dir/'CONTRACT.md').read_text()+'\nProject rules:\n'+rules.read_text()+'\nCandidate patch:\n'+patch
            questions=exp.questions(pass_no==2)
            body={'model':exp.CFG['judge_model'],'state':state,'questions':questions}
            dest=out/f'{name}-p{pass_no}.response.json'
            exp.save(out/f'{name}-p{pass_no}.request.json',body)
            if not dest.exists():
                req=Request(exp.CFG['judge_endpoint'],data=json.dumps(body).encode(),
                            headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
                with exp.open_typesafe(req,timeout=120) as response:
                    result=json.load(response)
                if result.get('model')!=exp.CFG['judge_model'] or not all(k in result.get('answers',{}) for k in questions):
                    raise ValueError('Jev identity/schema mismatch')
                exp.save(dest,result)
        print(f'MerchantOps Jev pass {pass_no} complete',flush=True)
    scores={}
    for name,identity in mapping.items():
        runs=[exp.read(out/f'{name}-p{i}.response.json')['answers'] for i in (1,2)]
        scores[identity]={}
        for question in exp.questions():
            a,b=(run[question] for run in runs)
            x=a.get('choice')
            agreed=bool(x and x==b.get('choice') and min(a.get('probabilities',{}).get(x,0),b.get('probabilities',{}).get(x,0))>=.8)
            scores[identity][question]={'value':x if agreed else None,'needs_review':not agreed,'passes':[a,b]}
        # Keep the captured manifest and its integrity index intact.
        exp.save(PILOTS/identity/'jev-evaluation.json',scores[identity])
    exp.save(out/'pilot-judgments.json',scores)

def summaries(base):
    logs=base/'tests'
    results=[]
    for file in sorted(logs.glob('*.trx')):
        root=ET.parse(file).getroot()
        tests=root.findall('.//{*}UnitTestResult')
        for t in tests:
            error=t.find('.//{*}Message')
            message=(error.text or '')[:700] if error is not None else None
            results.append({'check':file.stem,'name':t.get('testName'),'outcome':t.get('outcome'),
                            'message':message})
    for f in sorted(logs.glob('web-*.json')):
        for suite in exp.read(f).get('testResults',[]):
            for test in suite.get('assertionResults',[]):
                results.append({'check':f.stem,'name':test['fullName'],'outcome':test['status'],
                                'message':'\n'.join(test.get('failureMessages',[]))[:700] or None})
    return results

def report():
    current=fingerprint()
    past=observer_repair().get('previous_input_id')
    rows=[]
    for (model,task,condition),(base,m) in sorted(selected().items()):
        evidence=summaries(base)
        verdict=base/'jev-evaluation.json'
        rows.append({'model':model,'task':task,'condition':condition,'run':base.name,
          **{k:m.get(k) for k in ('functional_success','target_skill_installed','target_skill_visible',
          'target_skill_loaded_observed','skill_tool_successes','direct_skill_content_reads','project_violations',
          'baseline_commit','snapshot_id','telemetry','evaluation','server_success','research_success',
          'resumed_same_upload','delivery_success','web_search_calls','delivery_evidence')},
          'checks':evidence,'jev':exp.read(verdict) if verdict.is_file() else None})
    attempts=[]
    for p in sorted(PILOTS.glob('merchantops-v2-*/manifest.json')):
        m=exp.read(p)
        if m.get('phase')=='pilot' and m.get('input_id') in (current,past) and not m.get('session_ok'):
            attempts.append({k:m.get(k) for k in ('id','task','condition','requested_model','failure_reason','telemetry')})
    result={'complete':len(rows)==PLANNED,'valid_pilots':len(rows),'planned':PLANNED,'main_started':False,
            'rows':rows,'excluded_session_attempts':attempts}
    out=REPORTS
    out.mkdir(parents=True,exist_ok=True)
    exp.save(out/'pilot-results.json',result)
    lines=['# MerchantOps V2 — web araştırmalı T6 pilotu','',f'Geçerli pilot: **{len(rows)}/{PLANNED}**. Ana deney: **0/72**.',
           '', '| Model | Görev | A | B | C |','|---|---|---|---|---|']
    cell={(r['model'],r['task'],r['condition']):r for r in rows}
    for model in exp.MODELS.values():
        for task in TASKS:
            entries=[]
            for condition in 'ABC':
                row=cell.get((model,task,condition))
                if row:entries.append('Geçti' if row['functional_success'] else 'Kaldı')
                else:entries.append('—')
            lines.append('| '+' | '.join([model,task,*entries])+' |')
    lines += ['', '| Model | Koşul | Kaynak doğru | Sunucu testleri | Aynı yükleme sürdü | Teslimat tamamlandı |',
              '|---|---|---|---|---|---|']
    for r in rows:
        values=['Evet' if r[k] else 'Hayır' for k in ('research_success','server_success','resumed_same_upload','delivery_success')]
        lines.append('| '+' | '.join([r['model'],r['condition'],*values])+' |')
    for model in exp.MODELS.values():
        group=[r for r in rows if r['model']==model]
        if not group:continue
        durations=[r['telemetry'].get('wall_seconds') for r in group if r['telemetry'].get('wall_seconds') is not None]
        costs=[r['telemetry']['api_equivalent_cost_usd'] for r in group if r['telemetry'].get('api_equivalent_cost_usd') is not None]
        lines += ['',f"**{model}**: {sum(r['functional_success'] is True for r in group)}/{len(group)} tam başarı. "
                  f"Ortanca süre: {statistics.median(durations):.1f} sn. API eşdeğeri: "
                  f"{format(sum(costs),'.4f')+' USD' if costs else 'ölçülmedi'} ({len(costs)} koşu)."]
    lines += ['', '| Koşul | Hedef kurulu | Başlangıç kataloğunda görünür | Hedef içerik gözlendi |',
              '|---|---:|---:|---:|']
    for condition in 'ABC':
        rs=[r for r in rows if r['condition']==condition]
        n=len(rs)
        metrics=[f"{sum(r[k] is True for r in rs)}/{sum(r[k] is not None for r in rs)}"
                 for k in ('target_skill_installed','target_skill_visible','target_skill_loaded_observed')]
        lines.append('| '+' | '.join([condition,*metrics])+' |')
    lines += ['', '## Başarısız kontroller']
    for r in rows:
        if r['functional_success']:continue
        checks=[c for c in r['checks'] if c['outcome'] in ('Failed','failed')]
        failures=[c['name'].split('.')[-1] for c in checks]
        if not failures and not r['server_success']:
            failures=[k for k,v in r['evaluation'].items() if isinstance(v,int) and k!='functional_success' and v!=0]
        if r['delivery_success'] is False:
            failures.append('Belge teslimatı tamamlanmadı')
        lines.append(f"- {r['model']} {r['task']}/{r['condition']}: "+', '.join(failures))
    lines += ['',f'Kör Jev kaydı bulunan pilot: {sum(r["jev"] is not None for r in rows)}/{len(rows)}.',
              'C, exact skill içeriğinin sistem bağlamına verilmesidir. Doğal Skill çağrısı ayrıca kaydedilir.',
              'API eşdeğeri abonelik faturası değildir. V1 ve V2 farklı görevler içerir. Karşılaştırma keşifseldir.',
              'Bir görev ve koşul için birer tekrar, nedensel veya genel bir skill etkisi için yetersizdir.']
    (out/'PILOT.md').write_text('\n'.join(lines)+'\n')
    print(out/'PILOT.md',flush=True)
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('verify','preflight','pilot-batch','judge','report'))
    action=p.parse_args().action
    if action=='verify':verify()
    elif action=='preflight':preflight()
    elif action=='pilot-batch':
        try:run_pilots()
        finally:report()
    elif action=='judge':
        judge_pilots()
        report()
    else:report()
if __name__=='__main__':main()
