import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';
const {createTransfer}=await import(pathToFileURL(process.env.SOLUTION));
const hash=b=>createHash('sha256').update(b).digest('hex');
const bytes=Buffer.from('abcdefghij'),spec={size:bytes.length,sha256:hash(bytes)};
function storage(initial=Buffer.alloc(0)){let data=Buffer.from(initial);return {commits:0,fail:false,read:()=>Buffer.from(data),commit(b){if(this.fail)throw Error('disk');data=Buffer.from(b);this.commits++;}};}
const invalid=fn=>assert.throws(fn,{code:'INVALID'});
test('normal interrupted resume and whole-file verification',()=>{const s=storage();let a=createTransfer(s,spec);assert.equal(a.write(0,bytes.subarray(0,4),hash(bytes.subarray(0,4))),4);a=createTransfer(s,spec);assert.equal(a.offset(),4);assert.equal(a.write(4,bytes.subarray(4),hash(bytes.subarray(4))),10);const b=a.finish();assert.deepEqual(b,bytes);b[0]=0;assert.deepEqual(a.finish(),bytes);});
test('critical: identical replay versus conflicting and partial overlap',()=>{const s=storage(bytes.subarray(0,6)),a=createTransfer(s,spec);assert.equal(a.write(0,bytes.subarray(0,4),hash(bytes.subarray(0,4))),6);assert.equal(s.commits,0);const bad=Buffer.from('zz');invalid(()=>a.write(1,bad,hash(bad)));const partial=bytes.subarray(4,8);invalid(()=>a.write(4,partial,hash(partial)));assert.deepEqual(s.read(),bytes.subarray(0,6));});
test('invalid chunks leave durable bytes unchanged',()=>{const s=storage(),a=createTransfer(s,spec),b=Buffer.from('a');for(const off of [-1,0.5,2,NaN])invalid(()=>a.write(off,b,hash(b)));invalid(()=>a.write(0,b,'0'.repeat(64)));invalid(()=>a.write(0,Buffer.alloc(0),hash(Buffer.alloc(0))));invalid(()=>a.write(0,Buffer.alloc(11),hash(Buffer.alloc(11))));assert.equal(s.commits,0);assert.equal(a.offset(),0);});
test('constructor, truncated and corrupt final data validation',()=>{for(const sp of [{...spec,size:-1},{...spec,size:1.5},{...spec,sha256:'bad'}])invalid(()=>createTransfer(storage(),sp));invalid(()=>createTransfer(storage(Buffer.alloc(11)),spec));invalid(()=>createTransfer(storage(bytes.subarray(0,5)),spec).finish());invalid(()=>createTransfer(storage(Buffer.alloc(10)),spec).finish());assert.deepEqual(createTransfer(storage(),{size:0,sha256:hash(Buffer.alloc(0))}).finish(),Buffer.alloc(0));});
test('critical: failed commit cannot advance acknowledged offset',()=>{const s=storage(),a=createTransfer(s,spec);s.fail=true;assert.throws(()=>a.write(0,bytes,hash(bytes)),/disk/);assert.equal(a.offset(),0);s.fail=false;assert.equal(a.write(0,bytes,hash(bytes)),10);assert.deepEqual(a.finish(),bytes);});
if(process.env.TASK==='T6'){
 test('critical: crash after durable commit before ACK, restart and replay',()=>{const s=storage();let crashes=0;const a=createTransfer(s,spec,()=>{crashes++;throw Error('crash');});assert.throws(()=>a.write(0,bytes,hash(bytes)),/crash/);assert.equal(s.read().length,10);const b=createTransfer(s,spec,()=>{crashes++;});assert.equal(b.offset(),10);assert.equal(b.write(0,bytes,hash(bytes)),10);assert.equal(s.commits,1);assert.equal(crashes,1);assert.deepEqual(b.finish(),bytes);});
 test('critical: two instances read live durable offset',()=>{const s=storage(),a=createTransfer(s,spec),b=createTransfer(s,spec);a.write(0,bytes.subarray(0,4),hash(bytes.subarray(0,4)));assert.equal(b.offset(),4);b.write(4,bytes.subarray(4),hash(bytes.subarray(4)));assert.equal(a.offset(),10);assert.deepEqual(a.finish(),bytes);});
 test('critical: finish revalidates storage rather than cached digest',()=>{const s=storage(),a=createTransfer(s,spec);a.write(0,bytes,hash(bytes));s.commit(Buffer.alloc(10));invalid(()=>a.finish());});
}
if(process.env.TASK==='T6')test('critical: real disk commit, process exit before ACK, new process replays',async()=>{
 const fs=await import('node:fs');const os=await import('node:os');const path=await import('node:path');const {spawnSync}=await import('node:child_process');
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'transfer-test-')),file=path.join(dir,'bytes');
 const commit=b=>{const tmp=file+'.tmp';const fd=fs.openSync(tmp,'w');try{fs.writeFileSync(fd,b);fs.fsyncSync(fd);}finally{fs.closeSync(fd);}fs.renameSync(tmp,file);};
 try{
  const script=`import fs from 'node:fs';import {pathToFileURL} from 'node:url';const {createTransfer}=await import(pathToFileURL(process.env.SOLUTION));const file=process.env.DATA_FILE;const storage={read:()=>fs.existsSync(file)?fs.readFileSync(file):Buffer.alloc(0),commit(b){const fd=fs.openSync(file+'.tmp','w');fs.writeFileSync(fd,b);fs.fsyncSync(fd);fs.closeSync(fd);fs.renameSync(file+'.tmp',file);}};const spec=JSON.parse(process.env.SPEC);const a=createTransfer(storage,spec,()=>process.exit(73));a.write(0,Buffer.from('abcdefghij'),spec.sha256);process.exit(74);`;
  const child=spawnSync(process.execPath,['--input-type=module','--eval',script],{env:{...process.env,DATA_FILE:file,SPEC:JSON.stringify(spec)},timeout:5000,encoding:'utf8'});
  assert.equal(child.status,73,child.stderr);assert.deepEqual(fs.readFileSync(file),bytes);let count=0;
  const storage={read:()=>fs.readFileSync(file),commit(b){count++;commit(b);}};
  const restarted=createTransfer(storage,spec,()=>assert.fail('replay must not commit'));assert.equal(restarted.write(0,bytes,hash(bytes)),10);assert.equal(count,0);assert.deepEqual(restarted.finish(),bytes);
 }finally{fs.rmSync(dir,{recursive:true,force:true});}
});
