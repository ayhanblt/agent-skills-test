import importlib.util,json,tempfile,unittest,shutil
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('experiment',ROOT/'scripts/experiment.py');e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)
class Pipeline(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
  for folder in ['tasks','skills','scripts','private-tests','config','selfcheck','provenance']:shutil.copytree(ROOT/folder,self.root/folder,ignore=shutil.ignore_patterns('__pycache__'))
  for f in ['README.md','PROTOCOL.md','RUBRIC.md','Dockerfile','.dockerignore','package.json','package-lock.json']:shutil.copy2(ROOT/f,self.root/f)
  self.previous=e.ROOT;e.ROOT=self.root
 def tearDown(self):e.ROOT=self.previous;self.temp.cleanup()
 def test_matrix_has_36_unique_balanced_cells(self):
  rows=e.matrix();self.assertEqual(36,len(rows));self.assertEqual(36,len({(x['task'],x['condition'],x['rep']) for x in rows}));self.assertEqual(rows,e.matrix())
 def test_starters_prompts_commits_and_treatments(self):
  commits=[]
  for c in 'ABC':
   run=e.prepare('T4',c,True);m=e.read(run/'manifest.json');commits.append(m['baseline_commit'])
   self.assertEqual((run/'prompt.txt').read_bytes(),(ROOT/'tasks/T4/prompt.txt').read_bytes())
   self.assertFalse((run/'workspace/private-tests').exists());self.assertFalse((run/'workspace/selfcheck').exists())
   self.assertEqual(c!='A',(run/'workspace/.claude/skills').exists())
   self.assertEqual(c=='C',(run/'launch/forced.md').exists())
   if c=='C':self.assertEqual((run/'launch/forced.md').read_bytes(),(ROOT/'skills/react-async-patterns/SKILL.md').read_bytes())
  self.assertEqual(1,len(set(commits)))
 def test_capture_keeps_missing_telemetry_null_and_distinguishes_attempt(self):
  run=e.prepare('T2','B',True);m=e.read(run/'manifest.json');m['exit_code']=0;e.save(run/'manifest.json',m)
  (run/'session.jsonl').write_text(json.dumps({'type':'assistant','message':{'model':e.CFG['model'],'content':[]}})+'\n'+json.dumps({'type':'result','is_error':False})+'\n')
  (run/'capture/skill-events.jsonl').write_text(json.dumps({'hook_event_name':'PreToolUse','tool_input':{'skill':'payment-reliability'}})+'\n')
  e.capture(run);m=e.read(run/'manifest.json');self.assertTrue(m['session_ok']);self.assertFalse(m['skill_loaded_observed']);self.assertIsNone(m['telemetry']['tokens']);self.assertIsNone(m['telemetry']['cost_usd'])
  (run/'capture/skill-events.jsonl').write_text(json.dumps({'hook_event_name':'PostToolUse','tool_input':{'skill':'payment-reliability'}})+'\n')
  e.capture(run);self.assertTrue(e.read(run/'manifest.json')['target_skill_loaded_observed'])
 def test_wrong_model_invalidates_session(self):
  run=e.prepare('T1','A',True);m=e.read(run/'manifest.json');m['exit_code']=0;e.save(run/'manifest.json',m)
  (run/'session.jsonl').write_text(json.dumps({'type':'assistant','message':{'model':'wrong','content':[]}})+'\n'+json.dumps({'type':'result'})+'\n');e.capture(run)
  m=e.read(run/'manifest.json');self.assertFalse(m['session_ok']);self.assertIsNone(m['skill_loaded_observed'])
 def test_no_main_run_before_freeze(self):
  with self.assertRaises(FileNotFoundError):e.prepare('T1','A')
 def test_immutability_gate_rejects_modified_inputs(self):
  e.save(self.root/'matrix.json',e.matrix());e.save(self.root/'pilot/verification.json',{'verified':True});e.save(self.root/'freeze.json',{'files':e.fingerprint(),'matrix_sha256':e.sha(self.root/'matrix.json'),'pilot_verification_sha256':e.sha(self.root/'pilot/verification.json'),'image_id':'sha256:test'})
  with patch.object(e,'call',return_value='sha256:test'):e.check_frozen()
  (self.root/'skills/payment-reliability/SKILL.md').write_text('modified')
  with patch.object(e,'call',return_value='sha256:test'):
   with self.assertRaises(ValueError):e.check_frozen()
 def test_jev_option_order_reversed(self):
  for k,v in e.questions().items():self.assertEqual(list(v['criteria']),list(reversed(list(e.questions(True)[k]['criteria']))))
if __name__=='__main__':unittest.main()
