"""从工程根目录调用本地初始化CLI，不依赖PYTHONPATH。"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.cli import main

if __name__ == '__main__':
    raise SystemExit(main())
