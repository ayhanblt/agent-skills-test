"""Independent tests for T10–T15. The candidate never receives this file."""
from contextlib import contextmanager
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import tempfile
from threading import Lock, Thread
import time
import uuid

from openpyxl import load_workbook
from PIL import ImageChops
from pypdf import PdfReader
import pypdfium2


def run(command, *, cwd, env, timeout=90, check=True, input=None):
    if command[0] in ('node','python3'):
        runtime = Path(env['PATH'].split(os.pathsep)[0]).parents[1]
        chrome = Path(env['PILOT_CHROME']).parent
        home = Path.home()
        scratch = Path(env['TMPDIR'])
        expr = lambda value: '(subpath '+json.dumps(str(value))+')'
        public = [runtime/'python', runtime/'npm', chrome]
        profile = ('(version 1)(allow default)'
                   f'(deny file-read* {expr(home)})(allow file-read-metadata {expr(home)})'
                   '(allow file-read* '+ ' '.join(map(expr,public))+')'
                   '(deny file-write*)'
                   f'(allow file-write* {expr(scratch)} {expr(cwd)} (literal "/dev/null"))'
                   '(deny network*) (allow network* (local unix-socket))')
        if any(Path(arg).name == 'render.mjs' for arg in command[1:]):
            profile += '(allow network* (local ip "localhost:*"))(allow network-outbound (remote ip "localhost:*"))'
        if env.get('BASE_URL'):
            port = env['BASE_URL'].rsplit(':',1)[1]
            if not port.isdigit():
                raise ValueError('Unexpected local browser endpoint')
            profile += f'(allow network-outbound (remote ip "localhost:{port}"))'
        command = ['/usr/bin/sandbox-exec','-p',profile,*command]
    result = subprocess.run([str(item) for item in command], cwd=cwd, env=env, input=input,
                            text=True, capture_output=True, timeout=timeout)
    if check and result.returncode:
        raise RuntimeError(f'{Path(command[0]).name} exited {result.returncode}: {result.stderr[-4000:]}')
    return result


def evidence(work, name):
    file = work / name
    if not file.is_file() or file.is_symlink() or not file.resolve().is_relative_to(work.resolve()):
        raise ValueError(f'Missing {name}')
    if file.stat().st_size > 32 * 1024 * 1024:
        raise ValueError(f'Oversized {name}')
    return file


def t10(work, _env):
    filled = evidence(work, 'completed.pdf')
    data = json.loads(evidence(work, 'evidence.json').read_text())
    expected = {'water': 1298, 'gas': 427, 'electric': 13319}
    fields = PdfReader(filled).get_fields()
    correct = fields is not None and all(str(fields.get(k, {}).get('/V')) == str(v)
                                         for k, v in dict(expected, job='MX-17').items())
    crop = []
    with pypdfium2.PdfDocument(work/'form.pdf') as empty, pypdfium2.PdfDocument(filled) as result:
        empty.init_forms()
        result.init_forms()
        a = empty[0].render(scale=2, draw_annots=True).to_pil().convert('RGB')
        b = result[0].render(scale=2, draw_annots=True).to_pil().convert('RGB')
        for i in range(4):
            y = int((empty[0].get_height() - (733 - i * 48)) * 2)
            region = (328, y + 6, 700, y + 34)
            crop.append(sum(pixel < 245 for pixel in b.crop(region).convert('L').getdata())
                        > sum(pixel < 245 for pixel in a.crop(region).convert('L').getdata()) + 20
                        or ImageChops.difference(a.crop(region), b.crop(region)).getbbox() is not None)
        return {'editable_correct_fields': correct, 'one_page': len(result) == 1,
                'field_interiors_changed': all(crop), 'readings': data.get('readings') == expected,
                'source_pages': data.get('job') == 'MX-17' and
                data.get('pages') == {'water': 2, 'gas': 3, 'electric': 5}}


def recalc(path, stage, env):
    out = stage/'result'
    out.mkdir(exist_ok=True)
    run(['/Applications/LibreOffice.app/Contents/MacOS/soffice', f'-env:UserInstallation={(stage/"profile").as_uri()}',
         '--headless','--convert-to','xlsx','--outdir',out,path], cwd=stage, env=env)
    return load_workbook(out/path.name, data_only=True)


def t11(work, env):
    path = evidence(work, 'completed.xlsx')
    wb = load_workbook(path)
    cached = load_workbook(path, data_only=True)
    lines = wb['Lines']
    expected = {'BK1': ('Music',120), 'BK2': ('Theatre',80), 'BK3': ('Music',-20),
                'BK4': ('Theatre',0), 'BK5': ('Music',25)}
    records = [row for row in list(lines.values)[1:] if row[0]]
    wanted = [('Fees',205), ('Commission',20.5), ('Net',184.5)]
    summary = lambda book: [(book['Summary'].cell(i,1).value,book['Summary'].cell(i,2).value) for i in range(1,4)]
    initial = summary(cached)
    with tempfile.TemporaryDirectory(dir=work) as folder:
        stage = Path(folder)
        wb['Inputs']['B1'] = 0.2
        wb.save(stage/'changed.xlsx')
        rerun = summary(recalc(stage/'changed.xlsx', stage, env))
    return {'bookings': len(records) == 5 and {r[0]: (r[1],r[2] or 0) for r in records} == expected,
            'input_assumption': load_workbook(path)['Inputs']['B1'].value == 0.1,
            'line_formulas': len(records) == 5 and all(all(str(v).startswith('=') for v in r[3:5]) for r in records),
            'cached_values': initial == wanted, 'recalculates': rerun == [('Fees',205),('Commission',41),('Net',164)]}


def t12(work, env, references):
    evidence(work, 'render.mjs')
    initial = evidence(work, 'delivery.mp4')
    second = work/'judge-input.json'
    shutil.copyfile(references/'pilot-T12.json', second)
    run(['node','render.mjs',second.name,'judge.mp4'], cwd=work, env=env, timeout=160)
    def sample(file, second, filt):
        args = ['ffmpeg','-v','error','-ss',str(second),'-i',file,'-vf',filt,'-frames:v','1',
                '-f','rawvideo','-pix_fmt','rgb24','-']
        return subprocess.check_output([str(x) for x in args], cwd=work, env=env, timeout=20)
    def inspect(file, spec):
        probe = json.loads(run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',file],
                               cwd=work,env=env).stdout)
        v = next(x for x in probe['streams'] if x['codec_type'] == 'video')
        colors, captions = [], []
        for second, key in [(2,'firstColor'),(6,'secondColor')]:
            got = sample(file, second, 'crop=2:2:10:10,scale=1:1')
            expected = bytes.fromhex(spec[key].lstrip('#'))
            colors.append(len(got)==3 and max(abs(x-y) for x,y in zip(got,expected)) < 25)
            band = sample(file, second, 'crop=1280:180:0:540,scale=320:45')
            captions.append(sum(min(band[i:i+3])>200 for i in range(0,len(band),3))>35)
        pcm = subprocess.check_output(['ffmpeg','-v','error','-i',str(file),'-map','0:a:0','-ac','1',
                                        '-ar','8000','-f','s16le','-'], env=env, timeout=20)
        from array import array
        samples = array('h', pcm)
        peak = lambda start, end: max((abs(n) for n in samples[int(start*8000):int(end*8000)]), default=0)
        return {'format': v['width']==1280 and v['height']==720 and v['codec_name']=='h264'
                and v['avg_frame_rate']=='24/1' and abs(float(probe['format']['duration'])-10)<0.06,
                'transition': all(colors), 'visible_caption_band': all(captions),
                'chime_timing': peak(1.05,1.45)>1000 and peak(0,0.85)<300 and peak(2,9)<300}
    public = inspect(initial, json.loads((work/'input.json').read_text()))
    unseen = inspect(evidence(work,'judge.mp4'),json.loads(second.read_text()))
    return {'public': public, 'unseen': unseen, 'caption_text_review': 'pending_blind_review'}


PAGE = """<!doctype html><title>Event registration</title><h1>Event registration</h1>
<p id="status" role="status">1 seat available</p><button>Book seat</button>
<script>document.querySelector('button').onclick=async()=>{
const r=await fetch('/book',{method:'POST'});
const d=await r.json();
document.querySelector('#status').textContent=d.booking;
};</script>"""


@contextmanager
def event_app(mode='correct'):
    trace = []
    lock = Lock()
    booked = set()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def reply(self, body, mime, cookie=None):
            self.send_response(200)
            self.send_header('Content-Type',mime)
            if cookie:
                self.send_header('Set-Cookie',f'visitor={cookie}; Path=/; SameSite=Lax')
            self.end_headers()
            self.wfile.write(body.encode())
        def do_GET(self):
            if self.path != '/':
                self.send_error(404)
                return
            cookie = self.headers.get('Cookie','').removeprefix('visitor=') or uuid.uuid4().hex
            trace.append(('get',cookie,'available' if not booked else 'sold out'))
            self.reply(PAGE if not booked else PAGE.replace('1 seat available','Sold out'),'text/html',cookie)
        def do_POST(self):
            if self.path != '/book':
                self.send_error(404)
                return
            cookie = self.headers.get('Cookie','').removeprefix('visitor=')
            if mode=='delayed':
                time.sleep(.6)
            with lock:
                won = not booked or cookie in booked or mode=='broken'
                if won:
                    booked.add(cookie)
                trace.append(('post',cookie,'confirmed' if won else 'sold out'))
            self.reply(json.dumps({'booking':'Confirmed' if won else 'Sold out'}),'application/json')
    with ThreadingHTTPServer(('127.0.0.1',0),Handler) as server:
        thread = Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            yield f'http://127.0.0.1:{server.server_port}', trace
        finally:
            server.shutdown();thread.join()


def t13(work, env):
    path = evidence(work,'test.mjs')
    outcomes = {}
    for mode in ('correct','delayed','broken'):
        with event_app(mode) as (url, trace):
            try:
                result = run(['node',path],cwd=work,env=dict(env,BASE_URL=url),timeout=32,check=False)
            except subprocess.TimeoutExpired:
                outcomes[mode] = False
                continue
            started = [visitor for action,visitor,status in trace if action=='get' and status=='available']
            posts = [visitor for action,visitor,_ in trace if action=='post' and visitor]
            distinct = len(set(posts)) == len(posts) == 2 and set(posts) <= set(started)
            outcomes[mode] = distinct and ((result.returncode != 0) == (mode=='broken'))
    return outcomes


@contextmanager
def database(stage, env):
    # Unix socket in the per-attempt directory, no TCP listener or external database.
    pg = stage/'pg'
    sock = stage/'sock'
    sock.mkdir()
    password = stage/'pg-secret'
    password.write_text(secrets.token_hex(24))
    password.chmod(0o600)
    data = dict(env,PGHOST=str(sock),PGDATABASE='postgres',PGUSER='pilot',PGPORT='5432',PGPASSWORD=password.read_text())
    run(['initdb','-D',pg,'-U','pilot','-A','scram-sha-256','--pwfile',password,'--no-locale'],cwd=stage,env=data)
    password.unlink()
    (pg/'pg_hba.conf').write_text('local all candidate trust\nlocal all pilot scram-sha-256\n')
    run(['pg_ctl','-D',pg,'-l',stage/'pg.log','-o',f"-c listen_addresses='' -k {sock}",'-w','start'],cwd=stage,env=data)
    try:
        sql(stage,data,'CREATE ROLE candidate LOGIN')
        yield data, sock/'.s.PGSQL.5432'
    finally:
        run(['pg_ctl','-D',pg,'-m','immediate','-w','stop'],cwd=stage,env=data,check=False)


def sql(work, env, source):
    return run(['psql','-X','-qAt','-v','ON_ERROR_STOP=1','-c',source],cwd=work,env=env,timeout=30).stdout.strip()


def t14(work, env, starter):
    # Use a separate evaluator cluster; the candidate cluster isn't a source of truth.
    query = evidence(work,'query.sql').read_text().strip().rstrip(';')
    index = (work/'index.sql').read_text().strip().rstrip(';') if (work/'index.sql').is_file() else ''
    if not re.match(r'^select\s',query,re.I) or ';' in query or '\\' in query or '$1' not in query:
        return {'read_only_query_shape': False}
    if index and (not re.match(r'^create\s+index\s',index,re.I) or ';' in index or '\\' in index):
        return {'index_shape': False}
    original = """SELECT id, patron, requested_at FROM reservation
                  WHERE branch_id=$1 AND status='waiting' ORDER BY requested_at,id LIMIT 20"""
    schema = (starter/'schema.sql').read_text()
    judge_schema = schema.replace('15000','36000').replace('i % 23 = 0','i % 19 = 0')
    tested = []
    with tempfile.TemporaryDirectory(prefix='p14-',dir='/private/tmp') as folder:
        with database(Path(folder),env) as (db,_):
            for data in (schema,judge_schema):
                sql(work,db,'DROP TABLE IF EXISTS reservation;'+data)
                sql(work,db,'ALTER TABLE reservation OWNER TO candidate')
                candidate_db = dict(db,PGUSER='candidate',PGPASSWORD='')
                baseline = []
                for i in (1,4,12):
                    decl = f'PREPARE check_q(int) AS {original}; '
                    before = sql(work,db,decl+f'EXECUTE check_q({i})')
                    plan = json.loads(sql(work,db,decl+f'EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) EXECUTE check_q({i})'))[0]['Plan']
                    baseline.append((i,before,plan.get('Shared Hit Blocks',0)+plan.get('Shared Read Blocks',0)))
                if index:
                    sql(work,candidate_db,index)
                current = []
                for i,before,blocks in baseline:
                    decl = f'PREPARE check_q(int) AS {query}; '
                    after = sql(work,candidate_db,decl+f'EXECUTE check_q({i})')
                    plan = json.loads(sql(work,candidate_db,decl+f'EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) EXECUTE check_q({i})'))[0]['Plan']
                    cost = plan.get('Shared Hit Blocks',0)+plan.get('Shared Read Blocks',0)
                    current.append({'branch':i,'same_rows': before==after, 'baseline_blocks':blocks,'candidate_blocks':cost})
                tested.append(current)
            sizes = int(sql(work,db,"SELECT coalesce(sum(pg_relation_size(indexrelid)),0) FROM pg_index WHERE indrelid='reservation'::regclass AND NOT indisprimary"))
    return {'same_rows_and_order': all(x['same_rows'] for t in tested for x in t),
            'fewer_blocks': all(sum(x['candidate_blocks'] for x in t) < .75*sum(x['baseline_blocks'] for x in t) for t in tested),
            'index_budget':sizes<1200000,'index_bytes':sizes,'plans':tested}


def t15(work,env,starter):
    for file in ('app.py','test_regression.py'):
        evidence(work,file)
    cases = [
        ('2026-04-01T06:42:00+00:00','America/Los_Angeles','2026-03-31'),
        ('2026-03-31T20:05:00+00:00','Asia/Kolkata','2026-04-01'),
        ('2026-03-09T06:30:00+00:00','America/Los_Angeles','2026-03-08'),
        ('2026-11-01T09:30:00+00:00','America/Los_Angeles','2026-11-01'),
        ('2026-06-01T04:00:00+03:00','Pacific/Honolulu','2026-05-31'),
        ('2026-07-15T12:00:00+00:00','UTC','2026-07-15'),
    ]
    code = f'from app import bucket\nimport json\nprint(json.dumps([bucket(v,z) for v,z,_ in {cases!r}]))'
    got = json.loads(run(['python3','-c',code],cwd=work,env=env,timeout=20).stdout)
    fixed = run(['python3','-m','unittest','test_regression'],cwd=work,env=env,timeout=20,check=False)
    with tempfile.TemporaryDirectory(dir=work) as folder:
        base = Path(folder)
        shutil.copyfile(starter/'app.py',base/'app.py')
        shutil.copyfile(work/'test_regression.py',base/'test_regression.py')
        broken = run(['python3','-m','unittest','test_regression'],cwd=base,env=env,timeout=20,check=False)
    return {'hidden_dates': got == [expected for _,_,expected in cases],
            'test_passes_fix': fixed.returncode==0, 'test_fails_original_by_assertion': broken.returncode!=0 and 'AssertionError' in broken.stderr,
            'diagnosis_present': (work/'diagnosis.md').is_file()}
