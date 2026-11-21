"""Wait for a MerchantOps batch, then resume after verified five-hour quota resets."""
from collections import Counter
from datetime import datetime
import fcntl
import json
import os
import subprocess
import sys
import time
from zoneinfo import ZoneInfo

from merchantops_main import MAIN, exp, freeze


def batch_active():
    path=MAIN/'.run-lock'
    if not path.is_file():
        return False
    with path.open('rb') as lock:
        try:
            fcntl.flock(lock,fcntl.LOCK_SH|fcntl.LOCK_NB)
        except BlockingIOError:
            return True
    return False


def five_hour_reset(slot):
    attempt=max((slot/'attempts').glob('merchantops-v2-*'),
                key=lambda path:path.stat().st_mtime,default=None)
    if attempt is None or not (attempt/'evidence-index.json').is_file():
        return None
    row=exp.read(attempt/'manifest.json')
    reason=(row.get('failure_reason') or '').lower()
    if row.get('session_ok') or 'limit' not in reason:
        return None
    rate={}
    with (attempt/'session.jsonl').open(encoding='utf-8') as stream:
        for line in stream:
            try:
                event=json.loads(line)
            except ValueError:
                continue
            if event.get('type')=='rate_limit_event':
                rate=event.get('rate_limit_info') or {}
    reset=rate.get('resetsAt')
    if (rate.get('status')=='rejected' and rate.get('rateLimitType')=='five_hour'
            and isinstance(reset,int) and reset>0):
        return reset
    return None


def wait_until(target):
    while target>time.time():
        time.sleep(min(30,max(0,target-time.time())))


def supervise(matrix):
    restarts=Counter()
    while True:
        if batch_active():
            print('Ana deney çalışıyor. Bu pencere duruşu bekliyor.',flush=True)
            while batch_active():
                time.sleep(10)
        pending=next((row for row in matrix if not (MAIN/row['id']/'manifest.json').is_file()),None)
        if pending is None:
            print('72 koşunun tamamı sonuçlandı.',flush=True)
            return 0
        run_id=pending['id']
        reset=five_hour_reset(MAIN/run_id)
        if reset is None:
            raise SystemExit(f'{run_id}/72 bekliyor. Son duruş için doğrulanmış 5 saatlik limit kaydı bulunamadı.')
        if restarts[reset]>=2:
            raise SystemExit('Aynı yenilenme saati için Claude iki kez daha limit bildirdi. Bekleyici durdu.')
        stamp=datetime.fromtimestamp(reset,ZoneInfo('Europe/Istanbul'))
        target=max(reset+20,time.time()+(60 if restarts[reset] else 0))
        print(f'{run_id}/72 abonelik limitinde. Bildirilen yenilenme {stamp:%d.%m %H:%M} İstanbul saati.',flush=True)
        wait_until(target)
        if batch_active() or (MAIN/run_id/'manifest.json').is_file():
            continue
        print(f'{run_id}/72 için deney sürdürülüyor.',flush=True)
        restarts[reset]+=1
        result=subprocess.run([sys.executable,'-u','-B',str(freeze.ROOT/'scripts/merchantops_main.py'),'--run'],
                              cwd=freeze.ROOT)
        if result.returncode==0:
            return 0
        if result.returncode!=os.EX_TEMPFAIL and not batch_active():
            return result.returncode


def main():
    if not MAIN.is_dir():
        raise SystemExit('Ana deney kaydı henüz oluşmadı.')
    with (MAIN/'.resume-lock').open('a') as lock:
        try:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise SystemExit('Otomatik devam bekleyicisi zaten çalışıyor.') from error
        return supervise(exp.read(freeze.LOCK)['matrix'])


if __name__=='__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
