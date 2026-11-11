"""One-command development sample; no production queue/database changes."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from zoneinfo import ZoneInfo
from inspect_pdf_macos import inspect_pdf

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--browser', default='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
    parser.add_argument('--font', default='/System/Library/Fonts/Supplemental/Arial Unicode.ttf')
    parser.add_argument('--node', default=shutil.which('node'))
    parser.add_argument('--questions-per-row', type=int, choices=[1, 2, 3, 4, 5], default=2)
    parser.add_argument('--solutions-per-row', type=int, choices=[1, 2, 3, 4, 5], default=1)
    args = parser.parse_args()
    if not args.node or not Path(args.browser).is_file() or not Path(args.font).is_file():
        raise SystemExit('请确认Node、Chromium/Chrome与字体存在；可用参数指定路径')
    root = ROOT / 'backend/var/pdf-samples'
    root.mkdir(parents=True, exist_ok=True)
    date = datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d-')
    directory = Path(tempfile.mkdtemp(prefix=date, dir=root))
    print(f'开发样张目录：{directory}', flush=True)
    try:
        subprocess.run([args.node, str(ROOT / 'node_modules/vite/bin/vite.js'), 'build', '--config', 'print/vite.config.ts'],
                       cwd=ROOT, check=True, timeout=60)
        subprocess.run([sys.executable, str(ROOT / 'scripts/prepare_print_sample.py'), '--output', str(directory / 'input.json'),
                        '--questions-per-row', str(args.questions_per_row), '--solutions-per-row', str(args.solutions_per_row)],
                       cwd=ROOT, check=True, timeout=20)
        subprocess.run([args.node, str(ROOT / 'scripts/pdf_probe.mjs'), '--browser', args.browser,
                        '--font', args.font, '--input', str(directory / 'input.json'), '--output', str(directory / 'pdf')],
                       cwd=ROOT, check=True, timeout=90)
        report = {kind: inspect_pdf(directory / 'pdf' / f'{kind}.pdf') for kind in ('student', 'solution')}
        if report['solution']['pages'] <= report['student']['pages']:
            raise ValueError('解析版未增加独立答案页面')
        (directory / 'parsed-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({'status': 'pdf_samples_parsed', 'directory': str(directory),
                          'student_pages': report['student']['pages'], 'solution_pages': report['solution']['pages'],
                          'visual_review': 'pending', 'production_ready': False}, ensure_ascii=False))
    except (subprocess.SubprocessError, OSError, ValueError) as error:
        raise SystemExit(f'开发验证未完成（{type(error).__name__}）；检查上方输出。未开放用户出卷。') from None


if __name__ == '__main__':
    main()
