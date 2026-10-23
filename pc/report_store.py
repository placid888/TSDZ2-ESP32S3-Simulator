"""Read-only saved report access; filenames never become arbitrary paths."""
import json
import math
import re
from pathlib import Path

def finite_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError('非有限數字')
    return number

class ReportStore:
    def __init__(self, root):
        self.root = Path(root)

    def read(self, name):
        if not isinstance(name, str) or not re.fullmatch(r'[0-9]{8}-[0-9]{6}-[0-9]{6}\.json', name):
            raise ValueError('報告名稱無效')
        path = self.root / name
        if path.is_symlink() or path.resolve().parent != self.root.resolve():
            raise ValueError('報告路徑無效')
        if path.stat().st_size > 5_000_000:
            raise ValueError('報告過大')
        with path.open(encoding='utf-8-sig') as stream:
            report = json.load(stream, parse_float=finite_float, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('非有限數字')))
        if not isinstance(report, dict) or report.get('schema') != 1 or report.get('status') not in ('passed','failed','cancelled'):
            raise ValueError('不支援的報告格式')
        for field in ('steps','points'):
            if not isinstance(report.get(field,[]),list) or any(not isinstance(row,dict) for row in report.get(field,[])):
                raise ValueError('報告明細無效')
        return report

    def listing(self):
        items, skipped = [], 0
        for path in sorted(self.root.glob('*.json'), reverse=True):
            try:
                r = self.read(path.name)
                items.append({'id':path.name, 'name':r.get('name','測試報告'), 'kind':r.get('kind','sequence'),
                              'status':r['status'], 'started_at':r.get('started_at'),
                              'stop_confirmed':bool(r.get('stop_confirmed')), 'checks':len(r.get('steps',[])),
                              'points':len(r.get('points',[]))})
            except (OSError, ValueError, TypeError):
                skipped += 1
        return {'reports':items, 'skipped':skipped}
