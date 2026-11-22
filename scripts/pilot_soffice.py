#!/usr/bin/env python3
"""Run the pilot's headless LibreOffice with a per-invocation profile."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    binary = os.environ.get('PILOT_SOFFICE_BINARY')
    if not binary or not Path(binary).is_file():
        raise SystemExit('Pilot headless LibreOffice executable is unavailable.')
    with tempfile.TemporaryDirectory(prefix='profile-', dir=os.environ['PILOT_OFFICE_TEMP']) as root:
        scratch = Path(root)
        options = sys.argv[1:]
        if not any(arg.startswith('-env:UserInstallation=') for arg in options):
            options = [f'-env:UserInstallation={scratch.as_uri()}', *options]
        if '--headless' not in options:
            options = ['--headless', *options]
        env = dict(os.environ, HOME=root, TMPDIR=root, SAL_USE_VCLPLUGIN='svp')
        try:
            return subprocess.run([binary, *options], env=env, timeout=40).returncode
        except subprocess.TimeoutExpired:
            print('Headless LibreOffice did not finish within 40 seconds.', file=sys.stderr)
            return 124


if __name__ == '__main__':
    raise SystemExit(main())
