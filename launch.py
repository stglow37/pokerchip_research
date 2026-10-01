"""Small standard-library launcher; optional machine-local interpreter config."""
import json,sys,subprocess
from pathlib import Path
root=Path(__file__).resolve().parent
python=root/'.venv/Scripts/python.exe'
if not python.exists() and (root/'runtime.local.json').exists():
    python=Path(json.loads((root/'runtime.local.json').read_text(encoding='utf8'))['python'])
if not python.exists():
    print('Run SETUP.cmd once, then RUN.cmd. Python 3.14 is supported.');raise SystemExit(1)
result=subprocess.run([str(python),str(root/'run_gui.py'),*sys.argv[1:]],cwd=root)
raise SystemExit(result.returncode)
