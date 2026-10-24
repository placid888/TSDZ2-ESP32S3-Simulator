"""Read-only access to an explicitly published local offline STM8 build."""
import json
import re
from pathlib import Path
from stm8_build import inspect_hex, UPSTREAM, REVISION


class Stm8Artifacts:
    def __init__(self, root):
        self.root = Path(root)

    def report(self):
        data = json.loads((self.root / 'build-report.json').read_text(encoding='utf-8'))
        if not isinstance(data, dict) or data.get('status') != 'passed':
            raise ValueError('離線編譯報告未通過')
        if data.get('repository') != UPSTREAM or data.get('revision') != REVISION:
            raise ValueError('離線編譯來源不符目前支援版本')
        if data.get('programmed') is not False or data.get('hardware_verified') is not False:
            raise ValueError('離線編譯報告的驗證範圍不符')
        if not isinstance(data.get('compiler_version'), str) or not re.fullmatch(r'[0-9a-f]{64}', data.get('compiler_sha256', '')):
            raise ValueError('缺少編譯器版本或校驗資料')
        if not isinstance(data.get('warning_lines'), list) or not all(isinstance(x, str) for x in data['warning_lines']):
            raise ValueError('編譯警告資料無效')
        image = inspect_hex(self.root / 'firmware.hex')
        if data.get('image') != image:
            raise ValueError('韌體檔與編譯報告校驗不符')
        return data

    def snapshot(self, repository):
        try:
            report = self.report()
            version = re.search(r'\b\d+\.\d+\.\d+\s+#\d+', report['compiler_version'])
            return {'available': True, 'artifact_checked': True, 'source_matches': repository == report['repository'],
                    'revision': report['revision'], 'firmware_version': report.get('firmware_version_macro'),
                    'compiler_version': 'SDCC ' + version[0] if version else report['compiler_version'].splitlines()[0],
                    'image': report['image'], 'warnings': report['warning_lines'],
                    'programmed': False, 'hardware_verified': False, 'error': None}
        except FileNotFoundError:
            return {'available': False, 'artifact_checked': False, 'error': '尚無完整的 STM8 離線編譯產物'}
        except (OSError, ValueError, TypeError, AttributeError, KeyError) as exc:
            return {'available': False, 'artifact_checked': False, 'error': '離線產物無法驗證：' + str(exc)}
