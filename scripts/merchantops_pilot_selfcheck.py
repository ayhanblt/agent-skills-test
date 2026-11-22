"""Sample reference outcomes and selected counterexamples, without model calls."""
import argparse
from pathlib import Path
import csv
import json
import shutil
import tempfile
from merchantops_pilots import PROJECT, REFERENCE, local_env, matrix, old, load, starter, TASKS


def verify(task, work, env, grade):
    if task == 'T10':
        from pypdf import PdfReader, PdfWriter
        writer = PdfWriter(clone_from=work/'form.pdf')
        writer.update_page_form_field_values(writer.pages[0],
            {'job':'MX-17','water':'1298','gas':'427','electric':'13319'},auto_regenerate=False)
        writer.write(work/'completed.pdf')
        evidence = {'job':'MX-17','readings':{'water':1298,'gas':427,'electric':13319},
                    'pages':{'water':2,'gas':3,'electric':5}}
        (work/'evidence.json').write_text(json.dumps(evidence))
        positive = grade.t10(work,env)
        assert all(positive.values()), positive
        evidence['pages']['electric'] = 4
        (work/'evidence.json').write_text(json.dumps(evidence))
        assert not grade.t10(work,env)['source_pages']
    elif task == 'T11':
        from openpyxl import load_workbook
        wb = load_workbook(work/'budget.xlsx')
        seen = set()
        for i,row in enumerate(csv.DictReader((work/'bookings.csv').open()),2):
            booking = row['id']
            if booking in seen:
                continue
            seen.add(booking)
            for col,value in enumerate([booking,row['category'],int(row['fee'] or 0)],1):
                wb['Lines'].cell(i,col,value)
        wb.save(work/'ref.xlsx')
        grade.recalc(work/'ref.xlsx',work,env)
        shutil.copyfile(work/'result/ref.xlsx',work/'completed.xlsx')
        positive = grade.t11(work,env)
        assert all(positive.values()),positive
        wb = load_workbook(work/'completed.xlsx')
        wb['Summary']['B3'] = 184.5
        wb.save(work/'completed.xlsx')
        assert not grade.t11(work,env)['recalculates']
    elif task == 'T12':
        for name in ('render.mjs','video.jsx'):
            shutil.copyfile(PROJECT/'selfcheck'/('pilot-'+name),work/name)
        assets = work/'public';assets.mkdir()
        shutil.copyfile(work/'chime.wav',assets/'chime.wav')
        grade.run(['node','render.mjs','input.json','delivery.mp4'],cwd=work,env=env,timeout=160)
        positive = grade.t12(work,env,REFERENCE)
        assert all(positive['public'].values()) and all(positive['unseen'].values()),positive
    elif task == 'T13':
        shutil.copyfile(PROJECT/'selfcheck/pilot-test.mjs',work/'test.mjs')
        positive = grade.t13(work,env)
        assert all(positive.values()),positive
        (work/'test.mjs').write_text('process.exit(1)')
        assert not any(grade.t13(work,env).values())
    elif task == 'T14':
        (work/'index.sql').write_text("CREATE INDEX queue ON reservation(branch_id, requested_at, id) WHERE status='waiting'")
        positive = grade.t14(work,env,starter(task))
        assert all(positive[k] for k in ('same_rows_and_order','fewer_blocks','index_budget')),positive
        (work/'index.sql').unlink()
        assert not grade.t14(work,env,starter(task))['fewer_blocks']
    else:
        (work/'app.py').write_text('from datetime import datetime\nfrom zoneinfo import ZoneInfo\n'
            'def bucket(timestamp, zone):\n    return datetime.fromisoformat(timestamp).astimezone(ZoneInfo(zone)).date().isoformat()\n')
        (work/'test_regression.py').write_text('import unittest\nfrom app import bucket\n'
            'class Test(unittest.TestCase):\n    def test_boundary(self):\n'
            '        self.assertEqual(bucket("2026-04-01T06:42:00+00:00","America/Los_Angeles"), "2026-03-31")\n')
        (work/'diagnosis.md').write_text('UTC date used before local conversion.')
        positive = grade.t15(work,env,starter(task))
        assert all(positive.values()),positive
        (work/'test_regression.py').write_text('import unittest\n')
        assert not grade.t15(work,env,starter(task))['test_fails_original_by_assertion']
    print(task, 'reference and applicable counterexample checks passed', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('task',nargs='*')
    args = parser.parse_args()
    if set(args.task) - TASKS.keys():
        parser.error("Choose T10 through T15")
    grade = load('pilot_grade',REFERENCE/'pilot_grade.py')
    runner = old.harness()
    assert len(matrix()) == 36 and len(old.rows()) == 18
    for task in args.task or TASKS:
        with tempfile.TemporaryDirectory(dir='/private/tmp',prefix='v54-') as folder:
            stage = Path(folder)
            work = stage/'work'
            shutil.copytree(starter(task),work)
            env = local_env(runner,stage,work)
            verify(task,work,env,grade)
