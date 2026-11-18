import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url));
const python=process.env.PYTHON||(process.platform==='win32'?'python':'python3');
for(const args of [['scripts/selfcheck.py'],['-m','unittest','discover','-s','selfcheck','-p','test_*.py']]){
 const p=spawnSync(python,args,{cwd:root,stdio:'inherit'});
 if(p.error)throw p.error;if(p.status!==0)process.exit(p.status||1);
}
