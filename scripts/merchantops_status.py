"""Show recent Claude tool activity for the latest MerchantOps main run."""
import argparse
from collections import deque
from datetime import datetime
import json
from pathlib import Path
import time

PROJECT = Path(__file__).resolve().parents[1]
RUNS = PROJECT/'runs/merchantops-v2'
FREEZE = PROJECT/'provenance/merchantops-v2-freeze.json'
TASKS = {
    'T1':'Ödeme webhook imzası ve tekrar işleme kontrolü',
    'T2':'Finansal mutabakat ve çift taraflı ledger',
    'T3':'React’te iyimser iade ve geri alma',
    'T4':'Eşzamanlı operatör güncellemeleri ve ETag',
    'T5':'tus Core ve kesintiden sonra yüklemeyi sürdürme',
    'T6':'tus checksum, çökmeden kurtarma ve web’den belge teslimi',
}
CONDITIONS = {'A':'Skillsiz','B':'Skill kurulu, seçimi ajana bırakılmış','C':'Skill içeriği baştan verilmiş'}


def status(root, matrix):
    stream=max(root.glob('[0-9][0-9]/attempts/*/session.jsonl'),
               key=lambda path:path.stat().st_mtime,default=None)
    if stream is None:
        return ['Henüz ana koşu kaydı bulunamadı.']
    slot=stream.parents[2]
    raw=stream.with_name('manifest.json')
    official=slot/'manifest.json'
    complete=official.is_file()
    record=json.loads((official if complete else raw).read_text())
    row=matrix[slot.name]
    task,condition=row['task'],row['condition']
    lines=[
        f'Koşu: {slot.name}/{len(matrix)} · {task}/{condition} · {row["rep"]}. tekrar',
        f'Model: {row["model"]}',
        f'Görev: {TASKS[task]}',
        f'Koşul: {condition} — {CONDITIONS[condition]}',
    ]
    actions=deque(maxlen=8)
    progress=None
    terminal=None
    with stream.open('rb') as handle:
        start=max(0,stream.stat().st_size-1_048_576)
        handle.seek(start)
        if start:
            handle.readline()
        for line in handle:
            try:
                event=json.loads(line)
            except (ValueError,UnicodeDecodeError):
                continue
            message=event.get('message')
            if event.get('type')=='assistant' and isinstance(message,dict):
                for part in message.get('content',[]):
                    if part.get('type')!='tool_use':
                        continue
                    args=part.get('input') or {}
                    name=part.get('name','Araç')
                    detail=args.get('description') or Path(args.get('file_path') or '').name
                    actions.append(f'{name} — {detail}' if detail else name)
                    progress=None
            elif event.get('type')=='tool_progress':
                progress=f'{event.get("tool_name","Araç")} sürüyor · {event.get("elapsed_time_seconds","?")} sn'
            elif event.get('type')=='result':
                terminal=event.get('subtype','tamamlandı')
                progress=None
    if complete and record['status']=='evaluated':
        result='geçti' if record['functional_success'] else 'kaldı'
        state=f'Değerlendirme tamamlandı · görev {result}'
    elif complete and record['status']=='budget-exhausted':
        state='Süre veya tur sınırı doldu'
    elif record.get('failure_reason'):
        state=f'Beklemede · {record["failure_reason"]}'
    elif terminal=='success' or record['status']=='captured':
        state='Ajan yanıtını verdi · bağımsız değerlendirme bekleniyor'
    elif terminal:
        state=f'Ajan oturumu sona erdi · {terminal}'
    elif progress:
        state=progress
    else:
        state='Ajan oturumu başladı · sonuç henüz kaydedilmedi'
    lines.append(f'Durum: {state}')
    if actions:
        lines.extend(['Son araç adımları',*(f'  {action}' for action in actions)])
    return lines


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--watch',action='store_true',help='Display changes every five seconds')
    options=parser.parse_args()
    matrix={row['id']:row for row in json.loads(FREEZE.read_text())['matrix']}
    previous=None
    try:
        while True:
            current=status(RUNS,matrix)
            if current!=previous:
                print(datetime.now().astimezone().strftime('%H:%M:%S'),'·',flush=True)
                print('\n'.join(current),flush=True)
                previous=current
            if not options.watch:
                break
            time.sleep(5)
    except KeyboardInterrupt:
        pass
