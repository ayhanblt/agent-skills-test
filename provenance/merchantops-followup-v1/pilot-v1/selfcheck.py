"""Offline reference and counterexample checks for the pilot."""
from collections import Counter
import csv
import io
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from urllib.request import urlopen

from run import (ROOT, PRODUCTS, audit_skills, catalog, eligible_matches, json_file, rows,
                 score_t7, score_t8, skill_policy)


def verify():
    assert len(rows()) == 18
    assert Counter((r['task'], r['model'], r['condition']) for r in rows()).most_common(1)[0][1] == 1
    for row in rows():
        listed = [] if row['condition'] == 'A' else [row['target_skill']]
        init = json.dumps({'subtype': 'init', 'skills': listed})
        audit_skills(row, [init])
        builtin = json.dumps({'message': {'content': [
            {'type': 'tool_use', 'name': 'Skill', 'input': {'skill': 'init'}}
        ]}})
        try:
            audit_skills(row, [init, builtin])
        except ValueError:
            pass
        else:
            raise AssertionError('Built-in command was accepted')
    with TemporaryDirectory() as temp:
        file = Path(temp) / 'prompt.txt'
        for row in rows():
            prompt = skill_policy(row, file, 'Public task')
            assert (row['target_skill'] in prompt) == (row['condition'] == 'C')
    t8_source = json_file(ROOT / 'inputs/T8/eurostat.json')
    assert t8_source['size'] == [1, 1, 1, 4, 7]
    assert t8_source['dimension']['unit']['category']['index'] == {'KG_HAB': 0}
    assert t8_source['dimension']['wst_oper']['category']['index'] == {'GEN': 0}
    countries = t8_source['dimension']['geo']['category']['index']
    years = t8_source['dimension']['time']['category']['index']
    assert t8_source['status'][str(countries['IE'] * 7 + years['2020'])] == 'b'
    assert eligible_matches([['handoff', 'timeout', 'duplicate', 'authorization']], set()) == [
        ['handoff', 'authorization']]
    assert eligible_matches([['timeout'], ['duplicate']], {'handoff'}) == [['timeout'], ['duplicate']]
    assert {'handoff', 'duplicate', 'timeout'} <= json_file(ROOT / 'references/T9/decisions.json').keys()

    with TemporaryDirectory() as temp:
        work = Path(temp).resolve()
        (work / 'downloads').mkdir()
        with catalog() as (origin, trace):
            assert '1981–2010' in urlopen(origin).read().decode()
            for key in PRODUCTS:
                assert urlopen(f'{origin}/product/{key}').status == 200
            positive = urlopen(origin + '/csv/bos-c').read()
            values = list(csv.DictReader(io.StringIO(positive.decode('utf-8-sig'))))
            assert len(values) == 12 and {r['STATION'] for r in values} == {'USW00014739'}
            csv_output = work / 'downloads/station.csv'
            csv_output.write_bytes(positive)
            evidence = {'station_id': 'USW00014739', 'period': '1991-2020', 'frequency': 'monthly',
                        'catalog_url': origin + '/product/bos-c', 'download_url': origin + '/csv/bos-c',
                        'rejected_url': origin + '/product/bos-h', 'rejection_reason': 'Wrong period'}
            (work / 'evidence.json').write_text(json.dumps(evidence))
            result = score_t7(work, origin, trace)
            assert all(value is True for key, value in result.items() if key != 'reason_correctness')
            for key in ('bos-h', 'bos-d', 'near-c'):
                csv_output.write_bytes(urlopen(f'{origin}/csv/{key}').read())
                assert not score_t7(work, origin, trace)['csv_exact']
            shutil.copyfile(ROOT / 'references/T7/current.csv', csv_output)
            assert not score_t7(work, origin, [])['catalog_and_download_observed']
            csv_output.unlink()
            assert not score_t7(work, origin, trace)['csv_exact']

        expected = json_file(ROOT / 'references/T8/expected.json')
        for geo in ('DK', 'IE'):
            case = expected[f'{geo}-person']
            for name, year in [('start', '2018'), ('end', '2024')]:
                assert t8_source['value'][str(countries[geo] * 7 + years[year])] == case[name]
            assert case['end'] - case['start'] == case['delta']
        for entry in expected.values():
            entry.update(scope='test', source='test', reason='test')
        (work / 'note.md').write_text('Fixture only')
        output = work / 'evidence.json'
        output.write_text(json.dumps({'comparisons': expected}))
        assert all(all(value is not False for value in entry.values())
                   for entry in score_t8(work)['comparisons'].values())
        expected['DK-person']['unit'] = 'TONNE'
        expected['IE-person']['decision'] = 'comparable'
        expected['DK-total'].update(start=1930000, end=1810000, delta=-120000, decision='comparable')
        expected['SE-total'].update(start=False, end=0, delta=0)
        output.write_text(json.dumps({'comparisons': expected}))
        scores = score_t8(work)['comparisons']
        assert not scores['DK-person']['series_codes'] and not scores['IE-person']['decision']
        assert not scores['SE-total']['values'] and not scores['DK-total']['values']


if __name__ == '__main__':
    verify()
    print('18 cases, archived values, decoys, scoring and dependent decisions verified offline.')
