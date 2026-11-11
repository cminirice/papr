"""Development CLI for the shared cross-platform PDF inspector (legacy CLI filename); no database changes."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.services.pdf_inspection import inspect_pdf


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pdf', nargs='+', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps({str(path): inspect_pdf(path) for path in args.pdf}, ensure_ascii=False, indent=2))
    except (ValueError, OSError) as error:
        raise SystemExit(f'PDF检查失败：{error}') from None


if __name__ == '__main__':
    main()
