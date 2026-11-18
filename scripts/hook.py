import sys,json
from pathlib import Path
p=Path('/capture/skill-events.jsonl')
event=json.load(sys.stdin)
with p.open('a',encoding='utf-8') as f:f.write(json.dumps(event,ensure_ascii=False)+'\n')
