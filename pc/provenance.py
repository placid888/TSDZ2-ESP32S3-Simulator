"""Fingerprint executing PC sources once, independent of later checkout changes."""
import hashlib
import platform
from pathlib import Path

def source_identity(root=None):
    root=Path(root) if root else Path(__file__).parent
    files=sorted([p for p in root.glob('*.py') if not p.name.startswith('test_')]+list((root/'web').glob('*.*')))
    digest=hashlib.sha256()
    for path in files:
        name=path.relative_to(root).as_posix().encode()
        data=path.read_bytes()
        digest.update(len(name).to_bytes(4,'big')+name+len(data).to_bytes(8,'big')+data)
    return {'source_sha256':digest.hexdigest(),'python_version':platform.python_version()}
