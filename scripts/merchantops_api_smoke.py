"""Start a real MerchantOps API inside Claude Bash and leave it for host cleanup."""
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from urllib.error import URLError
from urllib.request import urlopen

scratch = Path(tempfile.gettempdir()).resolve()
run = Path(os.environ['CLAUDE_CODE_TMPDIR']).resolve()
if os.environ.get('DOTNET_USE_POLLING_FILE_WATCHER') != '1' or not scratch.is_relative_to(run):
    raise SystemExit('Claude Bash did not receive the pinned watcher and per-run scratch directory')

subprocess.run(['dotnet','build','api','--no-restore','-v','quiet'],check=True,timeout=35)
api = Path('api/bin/Debug/net10.0/MerchantOps.dll').resolve()
# Keep the process cwd available to lsof until the harness terminates it.
directory = Path(tempfile.mkdtemp(prefix='merchantops-api-',dir=scratch))
log = directory/'api.log'
with log.open('w') as output:
    child = subprocess.Popen(['dotnet',str(api),'--urls','http://127.0.0.1:0'],cwd=directory,
                             stdin=subprocess.DEVNULL,stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
deadline = time.monotonic()+15
try:
    while time.monotonic()<deadline and child.poll() is None:
        host = re.search(r'Now listening on: (http://127\.0\.0\.1:\d+)',log.read_text(errors='replace'))
        if host:
            try:
                with urlopen(host[1]+'/health',timeout=1) as response:
                    if response.status==200 and b'"ready"' in response.read():
                        print(f'MERCHANTOPS_API_READY_{sys.argv[1]}_{child.pid}')
                        sys.exit(0)
            except (URLError,TimeoutError):
                pass
        time.sleep(.2)
except Exception:
    child.terminate()
    raise
if child.poll() is None:
    child.terminate()
raise SystemExit('The API did not become healthy inside Claude Bash')
