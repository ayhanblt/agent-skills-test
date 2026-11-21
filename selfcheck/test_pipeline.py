import importlib.util,json,tempfile,unittest,shutil,os,subprocess
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
 def test_matrix_has_72_unique_balanced_cells(self):
  rows=e.matrix();self.assertEqual(72,len(rows));self.assertEqual(72,len({(x['model'],x['task'],x['condition'],x['rep']) for x in rows}));self.assertEqual(rows,e.matrix())
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
  (run/'session.jsonl').write_text(json.dumps({'type':'assistant','message':{'model':e.MODELS['sonnet'],'content':[]}})+'\n'+json.dumps({'type':'result','is_error':False})+'\n')
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
 def test_secrets_are_local_and_do_not_change_research_fingerprint(self):
  fingerprint=e.input_id()
  (self.root/'.env').write_text('TYPESAFE_API_KEY="fake-local-key"\n')
  with patch.dict(os.environ,{'TYPESAFE_API_KEY':''}):self.assertEqual(e.typesafe_key(),'fake-local-key')
  self.assertEqual(e.input_id(),fingerprint)
 def test_subscription_mount_does_not_pass_api_keys_or_archive_credentials(self):
  run=e.prepare('T1','A',True)
  def fake_run(args,**kwargs):
   self.assertIn(f'{e.AUTH_VOLUME}:/auth:ro',args)
   self.assertIn('--tmpfs',args)
   self.assertIn(f'{run/"claude"}:/native',args)
   self.assertNotIn('ANTHROPIC_API_KEY',args)
   self.assertNotIn('TYPESAFE_API_KEY',args)
   self.assertNotIn('CLAUDE_CODE_OAUTH_TOKEN',args)
   for event in [{'type':'assistant','message':{'model':e.MODELS['sonnet'],'content':[]}},{'type':'result','is_error':False,'total_cost_usd':0.123,'usage':{'input_tokens':20}}]:kwargs['stdout'].write(json.dumps(event)+'\n')
   return subprocess.CompletedProcess(args,0)
  with patch.dict(os.environ,{'ANTHROPIC_API_KEY':'must-not-be-used','CLAUDE_CODE_OAUTH_TOKEN':''}),patch.object(e,'call',return_value='image-id'),patch.object(e.subprocess,'run',side_effect=fake_run):e.launch(run)
  m=e.read(run/'manifest.json');self.assertTrue(m['session_ok']);self.assertIsNone(m['telemetry']['cost_usd']);self.assertEqual(m['telemetry']['api_equivalent_cost_usd'],0.123)
 def test_finish_captures_changes_committed_by_agent(self):
  run=e.prepare('T1','A',True)
  work=run/'workspace'
  (work/'solution.mjs').write_text('// agent implementation\n')
  (work/'CONTRACT.md').write_text('changed outside allowed files\n')
  e.call(['git','-C',work,'add','.'])
  e.call(['git','-C',work,'-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','agent changes'])
  manifest=e.read(run/'manifest.json')
  manifest.update(status='captured',image_id='test-image')
  e.save(run/'manifest.json',manifest)
  original_run=subprocess.run
  def fake_run(args,**kwargs):
   if args[0]=='docker':return subprocess.CompletedProcess(args,0,'TAP version 13\n# tests 6\n# pass 6\n','')
   return original_run(args,**kwargs)
  with patch.object(e.subprocess,'run',side_effect=fake_run):e.finish(run)
  self.assertIn('+// agent implementation',(run/'changes.patch').read_text())
  self.assertIn('CONTRACT.md',e.read(run/'manifest.json')['project_violations'])
 def test_pilot_cannot_use_preflight_from_a_different_image(self):
  e.save(self.root/'config/runtime-verification.json',{'image_id':'image-one'})
  with patch.object(e,'call',return_value='image-two'):
   with self.assertRaisesRegex(ValueError,'Run preflight'):e.verified_image()
 def test_model_isolation_keeps_prompt_and_starter_identical(self):
  sonnet=e.prepare('T2','C',True,model=e.MODELS['sonnet'])
  haiku=e.prepare('T2','C',True,model=e.MODELS['haiku'])
  a,b=[e.read(p/'manifest.json') for p in (sonnet,haiku)]
  for field in ('baseline_commit','prompt_sha256','injected_skill_sha256','effort_requested'):
   self.assertEqual(a[field],b[field])
  self.assertEqual(e.read(haiku/'launch/settings.json')['model'],e.MODELS['haiku'])
  b['exit_code']=0
  e.save(haiku/'manifest.json',b)
  for observed,expected in [(e.MODELS['sonnet'],False),(e.MODELS['haiku'],True)]:
   events=[{'type':'assistant','message':{'model':observed,'content':[]}},{'type':'result'}]
   (haiku/'session.jsonl').write_text(''.join(json.dumps(event)+'\n' for event in events))
   e.capture(haiku)
   self.assertEqual(e.read(haiku/'manifest.json')['session_ok'],expected)
 def test_pilot_gate_requires_both_models(self):
  complete={(e.MODELS['sonnet'],task,condition):('old/path','hash')
            for task in e.PILOT_TASKS for condition in 'ABC'}
  with patch.object(e,'verified_image',return_value='image'),patch.object(e,'valid_pilots',return_value=complete):
   with self.assertRaisesRegex(ValueError,'claude-haiku-5-5'):e.pilot_verify('Calibration')
 def test_report_does_not_mix_models(self):
  e.report()
  rows=e.read(self.root/'reports/aggregates.json')
  self.assertEqual(36,len(rows))
  self.assertEqual(18,len([a for a in rows if a['model']==e.MODELS['haiku']]))
if __name__=='__main__':unittest.main()
