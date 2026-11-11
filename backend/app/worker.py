"""单执行槽持久任务worker；配置PDF运行路径后先执行真实探针。"""
import argparse
from pathlib import Path
import subprocess
import signal
import sys
import time
from app.core.config import Settings
from app.core.database import make_engine
from app.core.time import beijing_now
from app.schemas.validation import ValidationReport
from app.services.content_seed import canonical
from app.services.validation_jobs import claim, finish

HARD_TIMEOUT_SECONDS = 60


def run_child(payload):
    completed = subprocess.run([sys.executable, '-m', 'app.validation_child'],
        cwd=Path(__file__).resolve().parents[1], input=canonical(payload), capture_output=True,
        text=True, timeout=HARD_TIMEOUT_SECONDS, check=True)
    return ValidationReport.model_validate_json(completed.stdout)


def run_once(engine, *, clock=beijing_now, runner=run_child):
    from app.services.preview_jobs import run_once as preview_once
    if preview_once(engine, clock=clock):
        return True
    claimed = claim(engine, clock())
    if claimed is None:
        return False
    try:
        report = runner(claimed['payload'])
    except subprocess.TimeoutExpired:
        finish(engine, claimed, clock(), error_code='ENGINE_TIMEOUT')
    except (subprocess.SubprocessError, OSError, ValueError):
        # 不记录原始stdout/stderr，避免未来内容或环境信息泄漏。
        finish(engine, claimed, clock(), error_code='VALIDATION_ENGINE_ERROR')
    else:
        finish(engine, claimed, clock(), report=report)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once', action='store_true', help='最多处理一个任务后退出')
    args = parser.parse_args()
    settings = Settings.from_env()
    engine = make_engine(settings.db_path)
    from app.services import paper_execution, paper_runtime
    fingerprint = paper_runtime.config_hash(settings)
    configured = any((settings.pdf_node, settings.pdf_browser, settings.pdf_font))
    advertised = False
    def stop(signum, frame):
        raise KeyboardInterrupt
    previous_term = signal.signal(signal.SIGTERM, stop)
    try:
        if configured:
            if not fingerprint:
                raise SystemExit("PDF配置不完整：需Node、Chromium/Chrome、字体和已构建的打印资源")
            try:
                paper_runtime.probe(settings)
            except Exception:
                raise SystemExit("PDF真实渲染/解析探针失败；未开放出卷，请先检查pdf:probe和开发样张") from None
            print("PDF真实探针通过，用户worker就绪", flush=True)
        while True:
            if fingerprint:
                if paper_runtime.config_hash(settings) != fingerprint:
                    raise SystemExit("PDF运行资源已变化，请重启worker重新验证")
                paper_runtime.heartbeat(engine, fingerprint, beijing_now())
                advertised = True
            from app.v2.worker import run_once as v2_once
            worked = v2_once(engine, settings) if fingerprint else False
            if not worked:
                worked = run_once(engine)
            if not worked and fingerprint:
                worked = paper_execution.run_once(engine, settings, fingerprint=fingerprint)
            if args.once:
                break
            if not worked:
                time.sleep(1)
    except KeyboardInterrupt:
        pass  # 中断留下租约；到期后有限重试。
    finally:
        try:
            if advertised:
                paper_runtime.withdraw(engine, fingerprint, beijing_now())
        finally:
            signal.signal(signal.SIGTERM, previous_term)
            engine.dispose()


if __name__ == '__main__':
    main()
