"""Verify hidden tests accept reference solutions and reject incomplete starters."""
import os,subprocess,json,sys,tempfile,argparse
from pathlib import Path
root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--docker',action='store_true');args=parser.parse_args()
results=[]
def run_suite(path,task,suite):
 if args.docker:
  command=['docker','run','--rm','--network=none','--read-only','--cap-drop=ALL','--security-opt=no-new-privileges','--pids-limit','64','--memory','512m','--cpus','1','--tmpfs','/tmp:rw,noexec,nosuid,size=32m','-e',f'TASK={task}','-e','SOLUTION=/opt/deps/solution.mjs','-v',f'{path}:/opt/deps/solution.mjs:ro','-v',f'{root/"private-tests"}:/opt/deps/private-tests:ro','agent-skills-test:locked','node','--test','--test-reporter=tap',f'/opt/deps/private-tests/{suite}.mjs']
  return subprocess.run(command,capture_output=True,text=True,timeout=45)
 env=os.environ.copy();env.update(SOLUTION=str(path),TASK=task)
 return subprocess.run(['node','--test','--test-reporter=tap',str(root/f'private-tests/{suite}.mjs')],env=env,capture_output=True,text=True,timeout=20)
for task in [f'T{i}' for i in range(1,7)]:
 suite='payment' if task in ['T1','T2'] else 'react' if task in ['T3','T4'] else 'transfer'
 for label,path,want in [('reference',root/f'selfcheck/references/{task}.mjs',0),('starter',root/f'tasks/{task}/starter/solution.mjs',1)]:
  p=run_suite(path,task,suite)
  ok=p.returncode==want;results.append({'task':task,'candidate':label,'expected_exit':want,'actual_exit':p.returncode,'verified':ok})
  print(task,label,'OK' if ok else 'FAILED')
  if not ok:print(p.stdout,p.stderr)
(root/'reports').mkdir(exist_ok=True);(root/('reports/docker-selfcheck.json' if args.docker else 'reports/selfcheck.json')).write_text(json.dumps(results,indent=2))
# Each mutation removes one real safeguard from a passing implementation.
mutations={
 'T1':("if(old)return old.fp===fp?old.promise:Promise.reject(error('CONFLICT'));", ""),
 'T2':("if(old.version!==undefined&&event.version<=old.version)return;", ""),
 'T3':("if(active)set", "if(true)set"),
 'T4':("if(e.gen===gen)", "if(true)"),
 'T5':("hash(bytes)!==digest||", ""),
 'T6':("offset:()=>storage.read().length", "offset:()=>0")
}
for task,(before,after) in mutations.items():
 source=(root/f'selfcheck/references/{task}.mjs').read_text()
 assert before in source,(task,'mutation no longer applies')
 with tempfile.TemporaryDirectory(dir=root/'selfcheck') as tmp:
  path=Path(tmp)/'solution.mjs';path.write_text(source.replace(before,after))
  suite='payment' if task in ['T1','T2'] else 'react' if task in ['T3','T4'] else 'transfer'
  p=run_suite(path,task,suite)
  ok=p.returncode==1 and 'not ok' in p.stdout
  results.append({'task':task,'candidate':'single-safeguard-mutation','verified':ok,'actual_exit':p.returncode})
  print(task,'mutation','REJECTED' if ok else 'MISSED')
(root/('reports/docker-selfcheck.json' if args.docker else 'reports/selfcheck.json')).write_text(json.dumps(results,indent=2))
if not all(r['verified'] for r in results):sys.exit(1)
