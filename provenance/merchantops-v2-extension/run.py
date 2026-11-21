"""Run the separate 36-row Agent Skills supplement."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parent
RUNTIME = ROOT / '.runtime'
FREEZE = ROOT / 'freeze.json'
RUNS = ROOT.parents[1] / 'runs' / 'merchantops-v2-extension'
CATALOG = 'https://www.ncei.noaa.gov/access/us-climate-normals/index.html'
CHROME = '158.0.8127.36'
BROWSER = '0.43.0'
CLAUDE = '2.1.322'
ROUTER = 'claude-sonnet-5-5'
AUTH = Path.home() / 'Desktop/projects/agent-skills-test/.local/merchantops-auth'
DOMAINS = ['www.ncei.noaa.gov']


def read(path):
    return json.loads(path.read_text())


def save(path, value):
    staged = path.with_suffix(path.suffix + '.tmp')
    staged.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')
    staged.replace(path)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def env():
    data = {k: v for k, v in os.environ.items()
            if not k.startswith(('ANTHROPIC_', 'CLAUDE_CODE_', 'CLAUDECODE', 'AGENT_BROWSER_', 'OPENAI_', 'TYPESAFE_'))}
    data.update(CLAUDE_CONFIG_DIR=str(AUTH), CLAUDE_CODE_DISABLE_AUTO_MEMORY='1',
                CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC='1')
    return data


def matrix():
    with (ROOT / 'matrix.csv').open() as f:
        rows = list(csv.DictReader(f))
    keys = {(row['task'], row['model'], row['condition'], row['repeat']) for row in rows}
    expected = {(task, model, condition, repeat) for task in ('T7', 'T8', 'T9')
                for model in ('claude-sonnet-5-5', 'claude-haiku-5-5')
                for condition in 'ABC' for repeat in ('1', '2')}
    if keys != expected or len(rows) != 36 or len({row['run_id'] for row in rows}) != 36:
        raise ValueError('Invalid 36-row matrix')
    return rows


def browser_binary():
    return (RUNTIME / 'npm/node_modules/.bin/agent-browser').resolve(strict=True)


def chrome_binary():
    root = RUNTIME / f'home/.agent-browser/browsers/chrome-{CHROME}'
    return next(root.glob('**/Google Chrome for Testing'))


def fingerprint():
    paths = [ROOT / name for name in ('run.py', 'setup.sh', 'PROTOCOL.md', 'matrix.csv',
                                    'browser-package.json', 'browser-package-lock.json')]
    for folder in ('prompts', 'inputs', 'references', 'skills'):
        paths.extend(path for path in (ROOT / folder).rglob('*') if path.is_file())
    return {str(path.relative_to(ROOT)): sha(path) for path in sorted(paths)}


def runtime():
    cli = subprocess.check_output(['claude', '--version'], text=True).split()[0]
    browser = subprocess.check_output([browser_binary(), '--version'], text=True).split()[-1]
    chrome = chrome_binary()
    if cli != CLAUDE or browser != BROWSER:
        raise ValueError(f'Unexpected runtime versions: Claude {cli}, agent-browser {browser}')
    return {'claude': cli, 'browser_cli': browser, 'chrome': CHROME,
            'cli_sha256': sha(browser_binary()), 'chrome_sha256': sha(chrome)}


def arguments(model, tools, settings, mcp, turns):
    return ['claude', '-p', '--model', model, '--effort', 'medium',
            '--no-session-persistence', '--setting-sources', 'project',
            '--strict-mcp-config', '--mcp-config', str(mcp), '--settings', str(settings),
            '--permission-mode', 'dontAsk', '--tools', tools, '--max-turns', str(turns)]


def parsed_json(text):
    text = text.strip()
    if text.startswith('```'):
        text = '\n'.join(text.splitlines()[1:-1])
    return json.loads(text)


def route(questions, labels, base_command, work, process_env):
    prompt = (ROOT / 'references/T9/router.txt').read_text() + '\n' + json.dumps(questions)
    result = subprocess.run([*base_command, '--output-format', 'json'], input=prompt,
                            cwd=work, env=process_env, capture_output=True, text=True, timeout=90)
    event = parsed_json(result.stdout)
    if result.returncode or event.get('is_error'):
        raise RuntimeError(event.get('result') or 'Stakeholder router failed')
    output = parsed_json(event['result'])
    if not isinstance(output, list) or len(output) != len(questions) or any(
            not isinstance(row, list) or any(not isinstance(key, str) or key not in labels for key in row)
            for row in output):
        raise ValueError('Invalid stakeholder decisions')
    return [sorted(set(row)) for row in output], event


def result_error(event):
    if event.get('is_error'):
        description = event.get('result') or event.get('subtype', 'Unknown Claude error')
        if event.get('subtype') != 'error_max_turns':
            raise RuntimeError(description)


def sanitized(event):
    # Match inside serialized strings without consuming their closing quote or escaped newline.
    return re.sub(r'proxy-(username|password):(?:(?!\\n)[^"])*',
                  r'proxy-\1: [redacted]', json.dumps(event, ensure_ascii=False))


def agent_call(cmd, prompt, work, process_env, record):
    response = subprocess.run([*cmd, '--output-format', 'stream-json', '--verbose', '--', prompt],
                              cwd=work, env=process_env, capture_output=True, text=True, timeout=300)
    events = [json.loads(line) for line in response.stdout.splitlines() if line.startswith('{')]
    record.write('\n'.join(sanitized(event) for event in events) + '\n')
    end = next((event for event in reversed(events) if event.get('type') == 'result'), {})
    if not end:
        raise RuntimeError('Claude returned no result')
    result_error(end)
    return events, end


def meeting(cmd, prompt, work, process_env, record, judge_command, destination):
    labels = read(ROOT / 'references/T9/decisions.json')
    events, adjudications = [], []
    used = set()
    router_work = work.parent / 'router'
    router_work.mkdir()
    with subprocess.Popen([*cmd, '--input-format', 'stream-json', '--output-format', 'stream-json', '--verbose'],
                          cwd=work, env=process_env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, text=True) as agent:
        try:
            for turn in range(3):
                agent.stdin.write(json.dumps({'type': 'user', 'message': {'role': 'user', 'content': prompt}}) + '\n')
                agent.stdin.flush()
                record.write(sanitized({'type': 'pilot_stakeholder_input', 'message': prompt}) + '\n')
                for line in agent.stdout:
                    event = json.loads(line)
                    events.append(event)
                    record.write(sanitized(event) + '\n')
                    if event.get('type') == 'result':
                        break
                else:
                    raise RuntimeError('Claude ended without a dialogue response')
                result_error(event)
                response = event.get('result', '')
                section = re.search(r'^\s*(?:#+\s*)?(?:\*\*)?QUESTIONS(?:\*\*)?\s*$', response, re.M | re.I)
                questions = re.findall(r'^\s*\d+\.\s+(.+)$', response[section.end():], re.M) if section else []
                if turn == 2 or (not questions and re.match(r'^\s*(?:#+\s*)?(?:\*\*)?BRIEF\b', response, re.I)):
                    return events, event, adjudications
                if not questions:
                    prompt = 'Use numbered questions or deliver the BRIEF in the requested form.'
                    continue
                matches, router_event = route(questions, labels, judge_command, router_work, process_env)
                answers = []
                for question, ids in zip(questions, matches):
                    selected = []
                    for key in ids:
                        if key not in used and len(used) == 8:
                            continue
                        used.add(key)
                        selected.append(key)
                    reply = ' '.join(labels[key] for key in selected) or 'No answer recorded for this question. Leave it open.'
                    answers.append(reply)
                    adjudications.append({'question': question, 'decision_ids': selected, 'reply': reply})
                save(destination / f'router-{turn + 1}.json',
                     {'routing': adjudications, 'usage': router_event.get('usage'),
                      'total_cost_usd': router_event.get('total_cost_usd')})
                prompt = '\n'.join(f'{n}. {answer}' for n, answer in enumerate(answers, 1))
                if turn == 1:
                    prompt += '\nPlease deliver the BRIEF now. Label unresolved decisions.'
        finally:
            agent.terminate()


def score(task, work, answer):
    if task == 'T7':
        artifact = work / 'downloads/station.csv'
        delivery = False
        if artifact.is_file() and not artifact.is_symlink():
            expected = read(ROOT / 'references/T7/monthly-values.json')
            try:
                with artifact.open(newline='', encoding='utf-8-sig') as file:
                    rows = list(csv.DictReader(file))
                months = {str(int(row['DATE'])): row for row in rows}
                columns = set(expected['1']) & set(rows[0])
                delivery = (len(rows) == 12 and months.keys() == expected.keys()
                            and 'MLY-TAVG-NORMAL' in columns
                            and all(row['STATION'].strip() == 'USW00014739' for row in rows)
                            and all(float(row[key]) == expected[month][key]
                                    for month, row in months.items() for key in columns))
            except (IndexError, KeyError, TypeError, ValueError, UnicodeError):
                delivery = False
        evidence = work / 'catalog.txt'
        discovered = (evidence.is_file() and not evidence.is_symlink()
                      and 'boston logan' in evidence.read_text(errors='replace').lower()
                      and '14739' in evidence.read_text(errors='replace'))
        return {'functional_delivery_pass': delivery, 'catalog_station_evidence': discovered,
                'catalog_discovery_review': 'pending_blind_review'}
    if task == 'T8':
        artifact = work / 'evidence.json'
        try:
            actual = read(artifact)
            data_ok = all(isinstance(actual[field], str)
                          and re.search(rf'(?<![A-Za-z0-9_]){code}(?![A-Za-z0-9_])', actual[field], re.I)
                          for field, code in [('dataset', 'env_wasmun'), ('operation', 'GEN'), ('unit', 'KG_HAB')])
            with (ROOT / 'references/T8/official-reference.csv').open() as f:
                expected = {r['country']: [int(r['2018_kg_per_person']), int(r['2024_kg_per_person']),
                                          int(r['arithmetic_delta']), sorted(int(y) for y in r['break_years'].split(',') if y)]
                            for r in csv.DictReader(f)}
            actual_values = {key: [item['kg_2018'], item['kg_2024'], item['delta_kg'], sorted(item['break_years'])]
                             for key, item in actual['countries'].items()}
            return {'numeric_and_flags_pass': data_ok and actual_values == expected,
                    'interpretation_review': 'pending_blind_review'}
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return {'numeric_and_flags_pass': False, 'interpretation_review': 'pending_blind_review'}
    return {'brief_delivered': bool(re.match(r'^\s*(?:#+\s*)?(?:\*\*)?BRIEF\b', answer, re.I)),
            'acceptance_and_grounding_review': 'pending_blind_review'}


def run(row, destination):
    task = row['task']
    condition = row['condition']
    skill_name = row['target_skill']
    process_env = env()
    with tempfile.TemporaryDirectory(prefix='mo-ext-', dir='/private/tmp') as folder:
        stage = Path(folder)
        work = stage / 'work'
        work.mkdir()
        mcp = stage / 'mcp.json'
        save(mcp, {'mcpServers': {}})
        settings = stage / 'settings.json'
        source = ROOT / 'skills' / skill_name
        tools = ['Read', 'Bash', 'Write', 'Edit', 'Glob', 'Grep', 'Skill'] if task != 'T9' else ['Skill']
        if condition != 'A':
            installed = work / '.claude/skills' / skill_name
            shutil.copytree(source, installed)
        if task in ('T8', 'T9'):
            shutil.copytree(ROOT / 'inputs' / task, work / 'inputs')
        blocked = [str(ROOT), str(Path.home())]
        deny_files = [f'{tool}(/{path}/**)' for tool in ('Read', 'Edit', 'Write', 'Grep', 'Glob') for path in blocked]
        permissions = {'defaultMode': 'dontAsk', 'allow': tools,
                       'deny': ['WebSearch', 'WebFetch', 'Agent', 'Task', *deny_files]}
        network = {'allowedDomains': DOMAINS if task == 'T7' else []}
        filesystem = {'denyRead': blocked, 'allowWrite': [str(work)], 'denyWrite': [str(work / '.claude')]}
        browser_args = None
        browser_env = None
        try:
            if task == 'T7':
                home = stage / 'browser-home'
                home.mkdir()
                sockets = stage / 'socket'
                sockets.mkdir()
                (work / 'downloads').mkdir()
                binary = work / 'agent-browser'
                shutil.copyfile(browser_binary(), binary)
                binary.chmod(0o755)
                filesystem['denyWrite'].append(str(binary))
                process_env['PATH'] = str(work) + os.pathsep + process_env.get('PATH', '')
                if condition != 'A':
                    cli_skills = stage / 'browser-skills'
                    cli_skills.mkdir()
                    (cli_skills / 'core').symlink_to(installed, target_is_directory=True)
                    process_env['AGENT_BROWSER_SKILLS_DIR'] = str(cli_skills)
                process_env.update(AGENT_BROWSER_SOCKET_DIR=str(sockets), AGENT_BROWSER_ALLOWED_DOMAINS=','.join(DOMAINS),
                                   AGENT_BROWSER_DOWNLOAD_PATH=str(work / 'downloads'))
                browser_env = dict(process_env, HOME=str(home), AGENT_BROWSER_EXECUTABLE_PATH=str(chrome_binary()))
                browser_args = [str(binary), '--session', 'search']
                subprocess.run([*browser_args, 'open', CATALOG], env=browser_env, check=True, capture_output=True, timeout=35)
                network['allowUnixSockets'] = [str(next(sockets.glob('*.sock')))]
            if task == 'T8':
                filesystem['denyWrite'].append(str(work / 'inputs'))
            save(settings, {'permissions': permissions, 'sandbox': {'enabled': True, 'failIfUnavailable': True,
                            'allowUnsandboxedCommands': False, 'autoAllowBashIfSandboxed': True,
                            'filesystem': filesystem, 'network': network}})
            cmd = arguments(row['model'], ','.join(tools), settings, mcp, 24 if task == 'T7' else 12)
            if condition == 'C':
                cmd.extend(['--append-system-prompt-file', str(installed / 'SKILL.md')])
            prompt = (ROOT / 'prompts' / f'{task}.txt').read_text()
            if task == 'T9':
                prompt += '\n' + '\n'.join(path.read_text() for path in sorted((work / 'inputs').glob('*.md')))
            (destination / 'prompt.txt').write_text(prompt)
            with (destination / 'session.jsonl').open('w') as record:
                if task == 'T9':
                    def expire(_signal, _frame):
                        raise TimeoutError('Stakeholder dialogue exceeded 360 seconds')
                    previous_alarm = signal.signal(signal.SIGALRM, expire)
                    signal.alarm(360)
                    try:
                        events, result, _ = meeting(cmd, prompt, work, process_env, record,
                                                 arguments(ROUTER, '', settings, mcp, 1), destination)
                    finally:
                        signal.alarm(0)
                        signal.signal(signal.SIGALRM, previous_alarm)
                else:
                    events, result = agent_call(cmd, prompt, work, process_env, record)
            answer = result.get('result', '')
            (destination / 'answer.md').write_text(answer)
            for file in ('downloads/station.csv', 'catalog.txt', 'evidence.json', 'note.md'):
                candidate = work / file
                if candidate.is_file() and not candidate.is_symlink() and candidate.resolve().is_relative_to(work):
                    shutil.copyfile(candidate, destination / candidate.name)
            evaluated = score(task, work, answer)
            actual = sorted({event['message']['model'] for event in events if event.get('type') == 'assistant'
                             and isinstance(event.get('message', {}).get('model'), str)
                             and event['message']['model'].startswith('claude-')})
            if actual != [row['model']]:
                raise ValueError(f'Requested model {row["model"]}, observed {actual}')
            results = [event for event in events if event.get('type') == 'result']
            use = [event.get('usage') for event in results]
            costs = [event.get('total_cost_usd') for event in results]
            calls = [item.get('input', {}).get('skill') for event in events
                     for item in event.get('message', {}).get('content', [])
                     if isinstance(item, dict) and item.get('type') == 'tool_use' and item.get('name') == 'Skill']
            return {'row': row, 'actual_models': actual, 'metrics': evaluated, 'skill_calls': calls,
                    'preload_sha256': sha(source / 'SKILL.md') if condition == 'C' else None,
                    'usage': use, 'reported_cost_usd': sum(costs) if costs and None not in costs else None,
                    'terminal_subtype': result.get('subtype')}
        finally:
            if browser_args:
                subprocess.run([*browser_args, 'close'], env=browser_env, capture_output=True, timeout=15)


def main(argv=None):
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    for name in ('status', 'plan', 'preflight', 'freeze', 'run'):
        mode.add_argument('--' + name, action='store_true')
    mode.add_argument('--smoke', choices=['T7', 'T8', 'T9'])
    args = parser.parse_args(argv)
    rows = matrix()
    if args.status:
        completed = sum((RUNS / r['run_id'] / 'complete.json').exists() for r in rows)
        print(f'{completed}/36 complete. Freeze: {FREEZE.exists()}')
        return
    if args.preflight:
        with tempfile.TemporaryDirectory(prefix='mo-ext-preflight-') as folder:
            work = Path(folder)
            settings = work / 'settings.json'
            mcp = work / 'mcp.json'
            save(settings, {})
            save(mcp, {'mcpServers': {}})
            cases = read(ROOT / 'references/T9/router-cases.json')
            labels = read(ROOT / 'references/T9/decisions.json')
            values, event = route([q for q, _ in cases], labels, arguments(ROUTER, '', settings, mcp, 1), work, env())
            record = {'router_pass': values == [sorted(v) for _, v in cases], 'actual': values,
                      'usage': event.get('usage'), 'total_cost_usd': event.get('total_cost_usd')}
            save(ROOT / 'verification/t9-router-smoke.json', record)
            if not record['router_pass']:
                raise ValueError('T9 router failed its regression checks')
        print(runtime())
        return
    if args.smoke:
        runtime()
        task = args.smoke
        row = next(row for row in rows if row['task'] == task
                   and row['condition'] == ('C' if task == 'T9' else 'A')
                   and row['model'] == ('claude-haiku-5-5' if task == 'T9' else 'claude-sonnet-5-5'))
        pilots = ROOT / 'verification' / 'runtime-pilot'
        pilots.mkdir(exist_ok=True)
        attempt = Path(tempfile.mkdtemp(prefix=f'{task}-', dir=pilots))
        outcome = run(row, attempt)
        save(attempt / 'result.json', outcome)
        print(json.dumps(outcome['metrics']), attempt)
        return
    current = {'files': fingerprint(), 'runtime': runtime()}
    if args.freeze:
        router = read(ROOT / 'verification/t9-router-smoke.json')
        browser = read(ROOT / 'verification/t7-catalog-smoke.json')
        dialogue = read(ROOT / 'verification/t9-dialogue-smoke.json')
        if not router['router_pass'] or not browser['catalog_route_verified'] or not dialogue['routing_verified']:
            raise ValueError('Required pilot checks did not pass')
        if FREEZE.exists() and read(FREEZE) != current:
            raise ValueError('A different freeze already exists')
        save(FREEZE, current)
        print('Frozen: 36 additional runs')
        return
    if not FREEZE.is_file() or current != read(FREEZE):
        raise ValueError('Freeze missing or frozen inputs/runtime changed')
    if args.plan:
        for row in rows:
            print(row['run_id'], row['model'], row['task'], row['condition'], row['repeat'])
        return
    lock = RUNS / '.active'
    lock.parent.mkdir(exist_ok=True)
    lock.mkdir()
    try:
        for row in rows:
            slot = lock.parent / row['run_id']
            slot.mkdir(exist_ok=True)
            if (slot / 'complete.json').exists():
                continue
            attempt = Path(tempfile.mkdtemp(prefix='attempt-', dir=slot))
            print(f'{row["run_id"]}: {row["task"]}/{row["condition"]} {row["model"]} repeat {row["repeat"]}', flush=True)
            start = time.monotonic()
            try:
                outcome = run(row, attempt)
            except Exception as exc:
                save(attempt / 'failure.json', {'row': row, 'failure': str(exc), 'seconds': time.monotonic()-start})
                raise
            outcome['seconds'] = time.monotonic()-start
            outcome['attempt'] = attempt.name
            save(attempt / 'result.json', outcome)
            save(slot / 'complete.json', outcome)
    finally:
        lock.rmdir()


if __name__ == '__main__':
    main()
