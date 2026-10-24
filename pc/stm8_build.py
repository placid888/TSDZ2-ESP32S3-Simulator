"""Offline, pinned upstream STM8 build. Never opens hardware or runs upstream scripts."""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

UPSTREAM = 'https://github.com/TSDZ2-ESP32/TSDZ2-Smart-EBike'
REVISION = '3df3083ad220856eb416692aa6d5ad73f5fdd1fc'
LIB_SOURCES = 'iwdg itc clk gpio uart2 tim1 tim2 tim3 tim4 exti adc1 flash'.split()
APP_SOURCES = 'common torque_sensor uart pwm motor wheel_speed_sensor brake pas adc timers ebike_app lights'.split()
SOURCES = [f'STM8S_StdPeriph_Lib/src/stm8s_{name}.c' for name in LIB_SOURCES] + [f'{name}.c' for name in APP_SOURCES]
FLAGS = ['-mstm8', '-Ddouble=float', '--std-c99', '--nolospre', '--opt-code-speed', '--peep-asm', '--peep-file', 'peep.txt', '--out-fmt-ihx']


def inspect_hex(path):
    """Check record checksums, termination, overlaps and absolute data addresses."""
    memory = {}; base = 0; eof = False
    for line in Path(path).read_text(encoding='ascii').splitlines():
        if not line.strip():
            continue
        if eof or not line.startswith(':'):
            raise ValueError('Invalid Intel HEX record order')
        try:
            record = bytes.fromhex(line[1:])
        except ValueError as exc:
            raise ValueError('Invalid Intel HEX encoding') from exc
        if len(record) < 5 or len(record) != record[0] + 5 or sum(record) % 256:
            raise ValueError('Invalid Intel HEX length/checksum')
        count, address, kind = record[0], int.from_bytes(record[1:3], 'big'), record[3]
        data = record[4:-1]
        if kind == 0:
            for offset, value in enumerate(data):
                absolute = base + address + offset
                if absolute in memory:
                    raise ValueError('Overlapping Intel HEX data')
                memory[absolute] = value
        elif kind == 1 and count == 0 and address == 0:
            eof = True
        elif kind in (2, 4) and count == 2 and address == 0:
            base = int.from_bytes(data, 'big') << (4 if kind == 2 else 16)
        elif kind in (3, 5) and count == 4 and address == 0:
            pass
        else:
            raise ValueError('Unsupported/malformed Intel HEX record')
    if not eof or not memory:
        raise ValueError('Intel HEX missing data or end record')
    return {'data_bytes': len(memory), 'minimum_address': min(memory), 'maximum_address': max(memory),
            'sha256': hashlib.sha256(Path(path).read_bytes()).hexdigest()}


def build(source, compiler, output):
    source = Path(source).resolve(); compiler = Path(compiler).resolve(); output = Path(output).resolve()
    if not compiler.is_file():
        raise ValueError('SDCC executable not found')
    def git(*args):
        return subprocess.check_output(['git', '-C', str(source), *args], text=True).strip()
    revision = git('rev-parse', 'HEAD')
    if revision != REVISION or git('status', '--porcelain', '--untracked-files=all'):
        raise ValueError('Expected clean, pinned upstream revision ' + REVISION)
    if output == source or output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError('Build output must be separate from upstream checkout')
    output.mkdir(parents=True, exist_ok=False)
    shutil.copytree(source / 'src', output / 'src')
    shutil.copy2(source / 'LICENSE', output / 'LICENSE.upstream')
    work = output / 'src'
    report = {'status': 'failed', 'repository': UPSTREAM, 'revision': revision,
              'compiler_path': str(compiler), 'compiler_sha256': hashlib.sha256(compiler.read_bytes()).hexdigest(),
              'flags': FLAGS, 'programmed': False, 'hardware_verified': False,
              'official_binary_equivalence_verified': False}
    report['source_sha256'] = {str(p.relative_to(work)).replace('\\', '/'): hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in sorted(work.rglob('*')) if p.is_file()}
    report['warning_lines'] = []
    started = time.monotonic()
    environment = os.environ.copy()
    environment['PATH'] = str(compiler.parent) + os.pathsep + environment.get('PATH', '')
    with (output / 'build.log').open('w', encoding='utf-8') as log:
        def run(args):
            log.write(json.dumps(args) + '\n'); log.flush()
            result = subprocess.run(args, cwd=work, env=environment, capture_output=True, text=True, errors='replace', timeout=180)
            log.write(result.stdout + result.stderr); log.flush()
            report['warning_lines'].extend(line for line in (result.stdout + result.stderr).splitlines() if 'warning' in line.lower())
            if result.returncode:
                raise RuntimeError(f'Compiler returned {result.returncode}; see build.log')
            return result.stdout + result.stderr
        try:
            report['compiler_version'] = run([str(compiler), '--version']).strip()
            header = (work / 'main.h').read_text()
            match = re.search(r'^#define\s+FW_VERSION\s+(\d+)', header, re.M)
            report['firmware_version_macro'] = int(match[1]) if match else None
            common = [str(compiler), '-ISTM8S_StdPeriph_Lib/inc', '-I.', *FLAGS]
            for name in SOURCES:
                run([*common, '-c', '-o', str(Path(name).with_suffix('.rel')), name])
            run([*common, 'main.c', *[str(Path(name).with_suffix('.rel')) for name in SOURCES]])
            report['image'] = inspect_hex(work / 'main.ihx')
            shutil.copy2(work / 'main.ihx', output / 'firmware.hex')
            report['status'] = 'passed'
        except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
            report['error'] = str(exc)
        finally:
            report['duration_s'] = round(time.monotonic() - started, 2)
            (output / 'build-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--sdcc', required=True)
    parser.add_argument('--output', required=True, help='New directory; existing directories are never overwritten')
    args = parser.parse_args()
    result = build(args.source, args.sdcc, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result['status'] == 'passed' else 1)
