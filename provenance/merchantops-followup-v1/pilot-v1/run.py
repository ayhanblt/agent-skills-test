"""Prepare and run the 18-row local pilot without editing the frozen study."""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import random
import re
import secrets
import shutil
import tempfile
from threading import Thread
import time

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[2]
EXTENSION = PROJECT / 'provenance/merchantops-v2-extension'
RUNS = PROJECT / 'pilot/merchantops-followup-v1'
FREEZE = ROOT / 'pilot-freeze.json'
SKILLS = {'T7': 'agent-browser', 'T8': 'statistical-source-comparability', 'T9': 'grilling'}
MODELS = ('claude-sonnet-5-5', 'claude-haiku-5-5')
PRODUCTS = {
    'bos-c': ('Boston Logan International Airport', 'USW00014739', '1991–2020', 'monthly', False),
    'bos-h': ('Boston Logan International Airport', 'USW00014739', '1981–2010', 'monthly', True),
    'bos-d': ('Boston Logan International Airport', 'USW00014739', '1991–2020', 'daily', True),
    'near-c': ('Boston-area training station', 'USW00000001', '1991–2020', 'monthly', True),
}
# A later question needs the outcome of the previous adjudication round.
DEPENDENT = {'duplicate', 'timeout'}
CRITICAL = {'handoff', 'authorization', 'duplicate', 'timeout', 'refund'}


def harness():
    spec = importlib.util.spec_from_file_location('frozen_extension_harness', EXTENSION / 'run.py')
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    runner.ROOT = ROOT
    return runner


def rows():
    matrix = [{'task': task, 'model': model, 'condition': condition, 'repeat': 1,
               'target_skill': skill, 'case': {'T7': 'boston-archive', 'T8': 'generated-vs-collected',
                                               'T9': 'cancellation-handoff'}[task]}
              for task, skill in SKILLS.items() for model in MODELS for condition in 'ABC']
    random.Random(20261121).shuffle(matrix)
    for index, row in enumerate(matrix, 1):
        row['run_id'] = f'P-{index:02d}'
    return matrix


def json_file(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fingerprint(runner):
    files = [p for p in ROOT.rglob('*') if p.is_file() and p != FREEZE
             and '__pycache__' not in p.parts and not p.name.startswith('.')]
    original = [EXTENSION / 'run.py']
    original.extend(p for key in SKILLS.values() for p in (EXTENSION / 'skills' / key).rglob('*')
                    if p.is_file())
    return {'schema': 1, 'matrix': rows(), 'files': {str(p.relative_to(ROOT)): digest(p) for p in sorted(files)},
            'original_files': {str(p.relative_to(EXTENSION)): digest(p) for p in sorted(original)},
            'skill_link': str((ROOT / 'skills').readlink()),
            'runtime': runner.runtime()}


def product_bytes(key):
    if key == 'bos-c':
        return (ROOT / 'references/T7/current.csv').read_bytes()
    _, station, period, frequency, _ = PRODUCTS[key]
    count = 31 if frequency == 'daily' else 12
    return ('STATION,DATE,PERIOD,FREQUENCY,MLY-TAVG-NORMAL\n' + ''.join(
        f'{station},{i:02d},{period},{frequency},{10 + 2 * i}\n' for i in range(1, count + 1))).encode()


@contextmanager
def catalog():
    trace = []

    class Catalog(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            path = self.path.partition('?')[0]
            prefix, _, key = path.lstrip('/').partition('/')
            kind = 'text/html; charset=utf-8'
            if path == '/':
                links = ''.join(f'<li><a href="/product/{k}">Station normals record {n}</a> '
                                f'<span>{entry[0]} | {entry[2]} | {entry[3]}</span></li>'
                                for n, (k, entry) in enumerate(sorted(PRODUCTS.items()), 1))
                body = ('<!doctype html><title>Climate normals archive</title><h1>Station products</h1>'
                        '<p>Controlled local archive. Some alternatives are synthetic training records.</p>'
                        f'<ul>{links}</ul>').encode()
            elif key in PRODUCTS and prefix == 'product':
                name, station, period, frequency, synthetic = PRODUCTS[key]
                if synthetic:
                    source = 'Synthetic training record. Filename is not an official NOAA download.'
                else:
                    source = ('Source: archived NOAA Climate Normals CSV. Original product: '
                              'https://www.ncei.noaa.gov/data/normals-monthly/1991-2020/access/USW00014739.csv')
                body = (f'<!doctype html><title>{name}</title><h1>{name}</h1><p>{station}</p>'
                        f'<p>Reference period: {period}. Frequency: {frequency}.</p><p>{source}</p>'
                        f'<a href="/csv/{key}" download="station.csv">Download CSV</a>').encode()
            elif key in PRODUCTS and prefix == 'csv':
                kind, body = 'text/csv', product_bytes(key)
            else:
                self.send_error(404)
                return
            trace.append(path)
            self.send_response(200)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(body)))
            if kind == 'text/csv':
                self.send_header('Content-Disposition', 'attachment; filename="station.csv"')
            self.end_headers()
            self.wfile.write(body)

    with ThreadingHTTPServer(('127.0.0.1', 0), Catalog) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f'http://127.0.0.1:{server.server_port}', trace
        finally:
            server.shutdown()
            thread.join()


def artifact(root, file):
    path = root / file
    if path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(root):
        return path
    return None


def load_object(path):
    try:
        result = json_file(path)
        return result if isinstance(result, dict) else {}
    except (OSError, TypeError, ValueError):
        return {}


def score_t7(work, base, trace):
    csv_path = artifact(work, 'downloads/station.csv')
    evidence = load_object(artifact(work, 'evidence.json')) if artifact(work, 'evidence.json') else {}
    chosen = '/product/bos-c'
    download = '/csv/bos-c'
    alternate = [f'/product/{k}' for k in PRODUCTS if k != 'bos-c']
    alternative = next((p for p in alternate if evidence.get('rejected_url') == base + p), None)
    return {
        'csv_exact': csv_path is not None and digest(csv_path) == digest(ROOT / 'references/T7/current.csv'),
        'selected_product': evidence.get('station_id') == 'USW00014739'
        and str(evidence.get('period')).replace('–', '-') == '1991-2020'
        and evidence.get('frequency') == 'monthly'
        and evidence.get('catalog_url') == base + chosen and evidence.get('download_url') == base + download,
        'catalog_and_download_observed': chosen in trace and download in trace and trace.index(chosen) < trace.index(download),
        'alternative_observed': alternative is not None and alternative in trace,
        'rejection_reason_present': bool(str(evidence.get('rejection_reason') or '').strip()),
        'reason_correctness': 'pending_blind_review',
    }


def score_t8(work):
    path = artifact(work, 'evidence.json')
    answer = load_object(path).get('comparisons') if path else {}
    answer = answer if isinstance(answer, dict) else {}
    expected = json_file(ROOT / 'references/T8/expected.json')
    metrics = {}
    for key, spec in expected.items():
        entry = answer.get(key, {})
        entry = entry if isinstance(entry, dict) else {}
        metrics[key] = {
            'values': all(k in entry and not isinstance(entry[k], bool) and entry[k] == spec[k]
                          for k in ('start', 'end', 'delta')),
            'series_codes': all(isinstance(entry.get(k), str) and entry[k].casefold() == spec[k].casefold()
                                for k in ('table', 'operation', 'unit') if k in spec) if 'table' in spec else None,
            'decision': entry.get('decision') == spec['decision'],
            'source_and_reason_present': all(isinstance(entry.get(k), str) and entry[k].strip()
                                             for k in ('source', 'scope', 'reason')),
        }
    return {'comparisons': metrics, 'note_present': artifact(work, 'note.md') is not None,
            'interpretation_quality': 'pending_blind_review'}


def eligible_matches(matches, previously_answered):
    if 'handoff' in previously_answered:
        return matches
    return [[key for key in labels if key not in DEPENDENT] for labels in matches]


def skill_policy(row, outfile, prompt):
    if row['condition'] == 'C':
        prompt = f"Apply the project skill {row['target_skill']} supplied in your context to this task.\n\n{prompt}"
        outfile.write_text(prompt)
    return prompt


def isolated_skill_env(env):
    return dict(env, CLAUDE_CODE_DISABLE_BUNDLED_SKILLS='1',
                DISABLE_DOCTOR_COMMAND='1', DISABLE_PLUGIN_AUTOLOAD='1')


def isolate_skill_settings(data, condition):
    blocked = ('doctor', 'checkup', 'plugin-authoring', 'init', 'security-review')
    data.update(disableBundledSkills=True, disableClaudeAiConnectors=True,
                skillOverrides={name: 'off' for name in blocked},
                enabledPlugins={'cc-plugin-plugin-authoring@builtin': False})
    deny = data.setdefault('permissions', {}).setdefault('deny', [])
    deny.extend(f'Skill({name} *)' for name in blocked)
    if condition == 'A':
        deny.append('Skill')


def catalog_prompt(prompt, origin):
    return (prompt + f"\n\nCatalog start URL: {origin}/ . "
            "If the search session starts blank or the browser restarts, open this URL in the same session.")


class SkillIsolationError(ValueError):
    pass


def audit_skills(row, events):
    allowed = set() if row['condition'] == 'A' else {row['target_skill']}
    if row['condition'] != 'A' and row['target_skill'] == 'agent-browser':
        allowed.add('core')  # The pinned agent-browser SKILL.md declares this name.
    seen_init = False
    for line in events:
        event = json.loads(line)
        if event.get('subtype') == 'init':
            seen_init = True
            if set(event.get('skills', [])) - allowed:
                raise SkillIsolationError('Beklenmedik skill görünürlüğü tespit edildi.')
        message = event.get('message', {})
        if not isinstance(message, dict):
            continue
        for item in message.get('content', []):
            if (isinstance(item, dict) and item.get('type') == 'tool_use'
                    and item.get('name') == 'Skill' and item.get('input', {}).get('skill') not in allowed):
                raise SkillIsolationError('Hedef dışı Skill çağrısı tespit edildi.')
    if not seen_init:
        raise SkillIsolationError('Oturum başlangıç kaydı eksik.')


def execute(runner, row, attempt):
    started = time.monotonic()
    original_route = runner.route
    original_env, original_save = runner.env, runner.save
    original_agent, original_meeting = runner.agent_call, runner.meeting

    def environment():
        return isolated_skill_env(original_env())

    def save_settings(path, data):
        if path.name == 'settings.json':
            isolate_skill_settings(data, row['condition'])
        original_save(path, data)

    def agent_call(cmd, prompt, *args):
        if row['task'] == 'T7':
            prompt = catalog_prompt(prompt, runner.CATALOG)
        prompt = skill_policy(row, attempt / 'prompt.txt', prompt)
        (attempt / 'prompt.txt').write_text(prompt)
        return original_agent(cmd, prompt, *args)

    def meeting(cmd, prompt, *args):
        return original_meeting(cmd, skill_policy(row, attempt / 'prompt.txt', prompt), *args)

    runner.env, runner.save = environment, save_settings
    runner.agent_call, runner.meeting = agent_call, meeting
    seen = set()

    def route(questions, labels, command, work, env):
        matches, event = original_route(questions, labels, command, work, env)
        accepted = eligible_matches(matches, seen)
        seen.update(key for labels in accepted for key in labels)
        number = len(list(attempt.glob('routing-request-*.json'))) + 1
        runner.save(attempt / f'routing-request-{number}.json',
                    {'reported_decisions': matches, 'eligible_decisions': accepted})
        return accepted, event

    runner.route = route
    runner.score = lambda task, work, answer: (
        score_t8(work) if task == 'T8' else
        {'brief_delivered': bool(re.match(r'^\s*(?:#+\s*)?(?:\*\*)?BRIEF\b', answer, re.I)),
         'answered_critical': sorted(CRITICAL & seen), 'answered_decisions': sorted(seen),
         'confirmed_decision_grounding': 'pending_blind_review'})
    try:
        if row['task'] == 'T7':
            with catalog() as (base, trace):
                runner.CATALOG = base
                runner.DOMAINS = ['127.0.0.1']
                runner.score = lambda task, work, answer: score_t7(work, base, trace)
                try:
                    outcome = runner.run(row, attempt)
                finally:
                    runner.save(attempt / 'catalog-trace.json', {'origin': base, 'requests': trace})
        else:
            outcome = runner.run(row, attempt)
    finally:
        runner.route = original_route
        runner.env, runner.save = original_env, original_save
        runner.agent_call, runner.meeting = original_agent, original_meeting
    with (attempt / 'session.jsonl').open() as record:
        audit_skills(row, record)
    outcome['skill_isolation_verified'] = True
    outcome.update(seconds=time.monotonic() - started, attempt=attempt.name)
    outcome['stakeholder_cost_usd'] = None
    costs = [json_file(path).get('total_cost_usd') for path in attempt.glob('router-*.json')]
    if costs and None not in costs:
        outcome['stakeholder_cost_usd'] = sum(costs)
    return outcome


def blind_export(runner):
    destination = Path(tempfile.mkdtemp(prefix='blind-', dir=RUNS))
    key = {}
    for row in rows():
        slot = RUNS / row['run_id']
        if not (slot / 'complete.json').exists():
            continue
        result = json_file(slot / 'complete.json')
        source = slot / result['attempt']
        label = secrets.token_hex(6)
        key[label] = row['run_id']
        packet = destination / label
        packet.mkdir()
        files = {'T7': ('evidence.json', 'catalog-trace.json'), 'T8': ('evidence.json', 'note.md'),
                 'T9': ('answer.md',)}[row['task']]
        for name in files:
            if (source / name).is_file():
                shutil.copyfile(source / name, packet / name)
        if row['task'] == 'T9':
            decisions = sorted({item for path in source.glob('router-*.json')
                                for turn in json_file(path)['routing'] for item in turn['decision_ids']})
            router = json_file(ROOT / 'references/T9/decisions.json')
            runner.save(packet / 'stakeholder-evidence.json', {item: router[item] for item in decisions})
        runner.save(packet / 'task.json', {'task': row['task'], 'case': row['case']})
    order = sorted(key)
    runner.save(destination / 'review-order.json', {'first': order, 'second': order[::-1]})
    runner.save(destination.with_suffix('.key.json'), key)
    print(destination)


def main():
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group(required=True)
    for mode in ('plan', 'status', 'preflight', 'run', 'blind'):
        modes.add_argument('--' + mode, action='store_true')
    args = parser.parse_args()
    runner = harness()
    if args.plan:
        for row in rows():
            print(row['run_id'], row['task'], row['condition'], row['model'], row['case'])
    elif args.status:
        print(f"{sum((RUNS / r['run_id'] / 'complete.json').is_file() for r in rows())}/18 complete")
    elif args.preflight:
        from selfcheck import verify
        verify()
        if fingerprint(runner) != json_file(FREEZE):
            raise SystemExit('Pilot inputs or runtime changed')
        print('18 rows, fixture checks and runtime fingerprint OK. No model calls.')
    elif args.blind:
        if not RUNS.is_dir():
            raise SystemExit('No pilot records to export')
        blind_export(runner)
    else:
        if fingerprint(runner) != json_file(FREEZE):
            raise SystemExit('Pilot inputs or runtime changed')
        RUNS.mkdir(parents=True, exist_ok=True)
        with (RUNS / '.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise SystemExit('A pilot process is already running') from None
            for row in rows():
                slot = RUNS / row['run_id']
                if (slot / 'complete.json').is_file():
                    continue
                slot.mkdir(exist_ok=True)
                attempt = Path(tempfile.mkdtemp(prefix='attempt-', dir=slot))
                print(row['run_id'], row['task'], row['condition'], row['model'], flush=True)
                try:
                    result = execute(runner, row, attempt)
                except Exception as exc:
                    reason = str(exc) if isinstance(exc, SkillIsolationError) else type(exc).__name__
                    runner.save(attempt / 'failure.json', {'error_type': type(exc).__name__, 'reason': reason})
                    raise SystemExit(f"{row['run_id']} stopped ({reason}). Resume with --run.") from None
                runner.save(attempt / 'result.json', result)
                runner.save(slot / 'complete.json', result)


if __name__ == '__main__':
    main()
