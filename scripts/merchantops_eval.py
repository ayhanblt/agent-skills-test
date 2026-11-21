"""Independent macOS build and evaluation for MerchantOps V2."""
import json
import os
from pathlib import Path
import shutil
import subprocess

ARTIFACTS = ('.git', '.claude', 'node_modules', 'bin', 'obj', 'dist', 'data', '.DS_Store', '__pycache__')
FORBIDDEN_PREFIXES = ('.env', '.npmrc', '.nuget')
API = {'T1':'WebhookTests','T2':'LedgerTests','T4':'DisputeTests','T5':'TusCore','T6':'TusCore|FullyQualifiedName~TusCrash'}
WEB = {'T3':'refund.test.tsx','T4':'dispute.test.tsx'}

def clean_copy(src, dest):
    def excluded(_, names):
        return {n for n in names if n in ARTIFACTS or n.startswith(FORBIDDEN_PREFIXES) or n.endswith(('.trx','.sqlite','.sqlite-wal','.sqlite-shm'))}
    for base, dirs, names in os.walk(src):
        ignore = excluded(base, dirs + names)
        dirs[:] = [d for d in dirs if d not in ignore]
        for name in dirs+[n for n in names if n not in ignore]:
            path = Path(base)/name
            if path.is_symlink() or not (path.is_dir() or path.is_file()):
                raise ValueError(f'Unsupported candidate file: {path.relative_to(src)}')
    shutil.copytree(src,dest,ignore=excluded,dirs_exist_ok=True)

def materialize(root, task, dest, reference=False):
    clean_copy(root/'tasks/merchantops',dest)
    if task:
        specific=root/f'tasks/{task}/merchantops'
        shutil.copyfile(specific/'CONTRACT.md',dest/'CONTRACT.md')
        if (specific/'overlay').exists():clean_copy(specific/'overlay',dest)
        if reference:clean_copy(root/f'selfcheck/merchantops/references/{task}',dest)

def record(command, cwd, log, *, prefix=(), env=None, timeout=120):
    with log.open('w',encoding='utf-8') as out:
        try:
            return subprocess.run([*prefix,*map(str,command)],cwd=cwd,env=env,stdout=out,
                                  stderr=subprocess.STDOUT,timeout=timeout).returncode
        except subprocess.TimeoutExpired:
            out.write('\nEvaluation timed out.\n')
            return 124

def hydrate_web(root, dest):
    source=root/'tasks/merchantops/web/node_modules'
    if not (source/'typescript/bin/tsc').exists():
        raise ValueError('Run npm ci in tasks/merchantops/web first')
    shutil.copytree(source,dest/'web/node_modules',symlinks=True)

def evaluate(root, task, app, logs, *, prefix=(), env=None, core_only=False):
    """The caller supplies a disposable candidate copy and process isolation."""
    env = dict(env or os.environ)
    logs.mkdir(parents=True,exist_ok=True)
    test_root = logs.parent/'checks'
    clean_copy(root/'private-tests/merchantops/ApiTests',test_root)
    for p in (root/'private-tests/merchantops/web').glob('*.tsx'):
        dest=app/'web/.independent'
        dest.mkdir(exist_ok=True)
        shutil.copyfile(p,dest/p.name)
    hydrate_web(root,app)

    def run(args, where, name, *, environment=None):
        return record(args,where,logs/f'{name}.log',prefix=prefix,env=environment or env)

    # Use local package cache, pinned lockfiles and explicit tool entry points.
    api_build=run(['dotnet','build','api','--nologo','-p:RestoreLockedMode=true','-p:NuGetAudit=false'],app,'api-build')
    web=app/'web'
    ts=run(['node','node_modules/typescript/bin/tsc','--noEmit'],web,'web-types')
    web_build=run(['node','node_modules/vite/bin/vite.js','build'],web,'web-build') if ts==0 else None
    result={'api_build':api_build,'web_types':ts,'web_build':web_build}

    if api_build==0:
        target=app/'api/bin/Debug/net10.0/MerchantOps.dll'
        test_env=dict(env,MO_API_DLL=str(target))
        restore=run(['dotnet','build','--nologo','-p:RestoreLockedMode=true','-p:NuGetAudit=false'],test_root,'test-build')
        result['test_build']=restore
        if restore==0:
            def test(which,name):
                args=['dotnet','test','--no-build','--no-restore','--nologo','--filter',
                      f'FullyQualifiedName~{which}','--logger','trx;LogFileName='+name+'.trx',
                      '--results-directory',logs]
                log=logs/f'{name}.log'
                for attempt in range(2):
                    code=run(args,test_root,name,environment=test_env)
                    output=log.read_text(errors='replace')
                    if not (code and 'Catastrophic failure:' in output and 'PortableSymbolReader.Dispose' in output):
                        return code
                    if attempt==1:
                        raise RuntimeError(f'VSTest symbol reader crashed twice in {name}')
                    for suffix in ('log','trx'):
                        evidence=logs/f'{name}.{suffix}'
                        if evidence.exists():
                            evidence.rename(logs/f'{name}.{suffix}.adapter-error')
            result['api_regression']=test('Regression','api-regression')
            if task in API:
                result['api_hidden']=test('TusCore' if core_only else API[task],'api-hidden')
    if ts==0 and web_build==0:
        vitest=['node','node_modules/vitest/vitest.mjs','run','--maxWorkers=1','--reporter=json']
        def web_test(name,file):
            # Disable candidate Vite configuration for independent tests.
            config=web/'.independent/vitest.config.mjs'
            config.write_text("export default {test:{environment:'jsdom',clearMocks:true},esbuild:{jsx:'automatic'}};\n")
            return run([*vitest,'--config',config,'--outputFile',logs/f'{name}.json',f'.independent/{file}'],web,name)
        result['web_regression']=web_test('web-regression','regression.test.tsx')
        if task in WEB:
            result['web_hidden']=web_test('web-hidden',WEB[task])
    result['functional_success']=all(code==0 for code in result.values())
    (logs/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    return result
