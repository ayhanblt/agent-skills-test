"""Verify the baseline and every independent task snapshot/reference locally."""
from concurrent.futures import ThreadPoolExecutor
import hashlib, json
from pathlib import Path
import tempfile
from merchantops_eval import evaluate, materialize
from experiment import ROOT, save

def source_id(root):
    digest=hashlib.sha256()
    for path in sorted(p for p in root.rglob('*') if p.is_file()):
        digest.update(path.relative_to(root).as_posix().encode()+b'\0')
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()

def verify():
    from merchantops import REPORTS, clean_workspace_processes, env_for, fingerprint, isolation
    output=REPORTS/'validation'
    output.mkdir(parents=True,exist_ok=True)
    def one(entry):
        case, task, reference, core = entry
        with tempfile.TemporaryDirectory(prefix='merchantops-check-') as tmp:
            work=Path(tmp);app=work/'app'
            materialize(ROOT,task,app,reference)
            identity=source_id(app)
            env=env_for(work)
            prefix=isolation(work,False,env)
            target=output/case
            target.mkdir(exist_ok=True)
            try:
                result=evaluate(ROOT,'T5' if core else task,app,work/'logs',core_only=core,prefix=prefix,env=env)
            finally:
                if (work/'logs').exists():
                    for log in (work/'logs').iterdir():
                        (target/log.name).write_bytes(log.read_bytes())
                clean_workspace_processes(work,target/'process-cleanup.json')
        expected=reference or core or task is None
        regressions=all(result.get(k)==0 for k in ('api_build','web_types','web_build','api_regression','web_regression'))
        verified=regressions and result['functional_success']==expected
        print(case, 'OK' if verified else 'FAIL', result,flush=True)
        return case,dict(result,verified=verified,source_id=identity,expected_full_pass=expected)
    entries=[('base',None,False,False),('T6-core','T6',False,True)]
    for task in [f'T{i}' for i in range(1,7)]:
        entries += [(task+'-starter',task,False,False),(task+'-reference',task,True,False)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=dict(pool.map(one,entries))
    save(output/'summary.json',{'input_id':fingerprint(),'cases':results})
    if not all(r['verified'] for r in results.values()):
        raise SystemExit(f'MerchantOps reference or regression verification failed; see {output}')
if __name__=='__main__':verify()
