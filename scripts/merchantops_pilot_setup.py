"""Install pinned pilot tools locally. This command never calls a model."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

PROJECT = Path(__file__).resolve().parents[1]
TOOLS = PROJECT/'.local/pilot-tools'
PINS = PROJECT/'provenance'


def call(*args):
    subprocess.run([str(a) for a in args], check=True)


def main():
    TOOLS.mkdir(parents=True,exist_ok=True)
    py = TOOLS/'python/bin/python3'
    if not py.is_file():
        call('uv','venv','--python','python3',TOOLS/'python')
    call('uv','pip','sync','--python',py,PINS/'pilot-python.lock')
    npm = TOOLS/'npm'
    npm.mkdir(exist_ok=True)
    lock = PINS/'pilot-npm-lock.json'
    shutil.copyfile(lock,npm/'package-lock.json')
    data = json.loads(lock.read_text())
    (npm/'package.json').write_text(json.dumps({'dependencies':data['packages']['']['dependencies']})+'\n')
    call('npm','ci','--ignore-scripts','--prefix',npm)
    chrome = TOOLS/'chrome'
    if not chrome.exists():
        browser = Path.home()/'Library/Caches/ms-playwright/chromium_headless_shell-1223/chrome-headless-shell-mac-arm64'
        if not browser.is_dir():
            raise SystemExit('Restore pinned Chromium headless shell (Playwright revision 1223) from the pilot machine.')
        shutil.copytree(browser, chrome)
    skills = TOOLS/'skills'
    skills.mkdir(exist_ok=True)
    for name,pin in json.loads((PINS/'pilot-skill-sources.json').read_text()).items():
        with tempfile.TemporaryDirectory() as stage:
            root = Path(stage)
            call('git','-C',root,'init','-q')
            call('git','-C',root,'fetch','--depth','1',pin['source'],pin['commit'])
            call('git','-C',root,'checkout','-q','--detach','FETCH_HEAD')
            destination = skills/name
            if destination.exists():
                shutil.rmtree(destination)
            shutil.copytree(root/pin['path'],destination)
    call('swiftc','-module-cache-path',TOOLS/'swift-cache',
         PROJECT/'tasks/T10/starter/ocr.swift','-o',TOOLS/'ocr')
    print('Pinned tools installed. Run scripts/merchantops_pilots.py --preflight.')


if __name__ == '__main__':
    main()
