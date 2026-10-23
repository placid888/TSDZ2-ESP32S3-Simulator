"""One-click local launcher; reuses an already running bench service."""
import json
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
URL = 'http://127.0.0.1:8765'
def ready():
    try:
        with urllib.request.urlopen(URL+'/api/state', timeout=1) as response:
            return 'connected' in json.load(response)
    except Exception:
        return False

def main():
    if not ready():
        import serial  # fail clearly before hiding the service process
        with (ROOT/'server.log').open('a') as stdout, (ROOT/'server-error.log').open('a') as stderr:
            subprocess.Popen([sys.executable, str(ROOT/'server.py')], cwd=ROOT,
                stdout=stdout, stderr=stderr,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        for _ in range(40):
            if ready():
                break
            time.sleep(.25)
        else:
            raise RuntimeError('Service did not start; see pc/server-error.log')
    webbrowser.open(URL)

if __name__ == '__main__':
    main()
