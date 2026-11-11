"""Bounded subprocesses and actual PDF readiness, independent of admission."""
from datetime import timedelta
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from app.core.database import write_transaction
from app.models.papers import PdfWorkerState
from app.services.content_seed import canonical, digest
from app.services.pdf_storage import MAX_PDF_BYTES, PdfTarget, save_pair, read_verified

ROOT = Path(__file__).resolve().parents[3]


def config_hash(settings):
    paths = [settings.pdf_node, settings.pdf_browser, settings.pdf_font,
             ROOT / 'print/dist/document.mjs', ROOT / 'print/dist/style.css', ROOT / 'scripts/pdf_renderer.mjs',
             ROOT / 'scripts/pdf_worker.mjs', ROOT / 'scripts/chrome_worker_launcher.sh', ROOT / 'package-lock.json']
    if any(path is None or not path.is_file() for path in paths):
        return None
    try:
        return digest({'generated_root': str(settings.generated_root),
            'files': [(str(p), p.stat().st_size, p.stat().st_mtime_ns) for p in paths]})
    except OSError:
        return None


def heartbeat(engine, fingerprint, now):
    with write_transaction(engine) as session:
        state = session.get(PdfWorkerState, 1)
        if state is None:
            state = PdfWorkerState(id=1)
            session.add(state)
        state.config_hash = fingerprint
        state.ready_until = now + timedelta(seconds=30)


def ready(session, settings, now):
    fingerprint = config_hash(settings)
    state = session.get(PdfWorkerState, 1)
    return bool(fingerprint and state and state.config_hash == fingerprint and state.ready_until > now)


def process(args, *, data, timeout, pulse=None, browser_pid_file=None):
    """Poll child with lease renewal; kill its entire process group on any exit."""
    with tempfile.TemporaryFile() as stdin, tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        stdin.write(data.encode())
        stdin.seek(0)
        child = subprocess.Popen(args, cwd=ROOT / 'backend', stdin=stdin, stdout=stdout, stderr=stderr,
                                 start_new_session=True)
        deadline = time.monotonic() + timeout
        try:
            while True:
                try:
                    code = child.wait(timeout=min(2, max(0.01, deadline - time.monotonic())))
                    if code:
                        raise RuntimeError('CHILD_FAILED')
                    stdout.seek(0)
                    result = stdout.read(1024 * 1024 + 1)
                    if len(result) > 1024 * 1024:
                        raise ValueError('CHILD_OUTPUT_TOO_LARGE')
                    return result
                except subprocess.TimeoutExpired:
                    if time.monotonic() >= deadline:
                        raise TimeoutError('CHILD_TIMEOUT') from None
                    if pulse is not None:
                        pulse()
        finally:
            terminate_tree(child, browser_pid_file)


def terminate_tree(child, browser_pid_file):
    # Playwright starts Chromium in a separate group. Its exec wrapper records
    # that group's PID in our private directory, so no system process scan is needed.
    browser_pid = None
    if browser_pid_file is not None:
        try:
            value = browser_pid_file.read_text()[:20].strip()
            if value.isdecimal() and 1 < int(value) != os.getpgrp():
                browser_pid = int(value)
        except OSError:
            pass
    def signal_group(pid, sig):
        if pid is not None:
            try:
                os.killpg(pid, sig)
            except ProcessLookupError:
                pass
    signal_group(browser_pid, signal.SIGTERM)
    signal_group(child.pid, signal.SIGTERM)
    try:
        child.wait(timeout=3)
    except subprocess.TimeoutExpired:
        pass
    signal_group(browser_pid, signal.SIGKILL)
    signal_group(child.pid, signal.SIGKILL)
    child.wait()


def withdraw(engine, fingerprint, now):
    with write_transaction(engine) as session:
        state = session.get(PdfWorkerState, 1)
        if state is not None and state.config_hash == fingerprint:
            state.ready_until = now


def generate(plan, pulse=None):
    return json.loads(process([sys.executable, '-m', 'app.paper_child'],
                             data=plan.model_dump_json(), timeout=20, pulse=pulse))


def render(document, settings, pulse=None):
    with tempfile.TemporaryDirectory(prefix='papr-render-') as directory:
        process([str(settings.pdf_node), str(ROOT / 'scripts/pdf_worker.mjs'), str(settings.pdf_browser),
                 str(settings.pdf_font), directory], data=canonical(document), timeout=65, pulse=pulse,
                 browser_pid_file=Path(directory) / 'browser.pid')
        contents = {}
        for kind, filename in [('student_pdf', 'student.pdf'), ('solution_pdf', 'solution.pdf')]:
            with (Path(directory) / filename).open('rb') as stream:
                contents[kind] = stream.read(MAX_PDF_BYTES + 1)
        metadata_path = Path(directory) / 'metadata.json'
        if metadata_path.stat().st_size > 65536:
            raise ValueError('PDF_METADATA_INVALID')
        metadata = json.loads(metadata_path.read_text())
        return contents, metadata


def probe(settings):
    from app.schemas.content import MultiplicationProfile
    from app.generators.multiplication import generate_paper
    from app.core.time import beijing_now, serialize_time
    seed = json.loads((ROOT / 'content/seeds/mul-vertical-v1.json').read_text())
    # Same first supported profile as the standalone development sample.
    profile = MultiplicationProfile.model_validate(seed['profiles'][0])
    questions = generate_paper(profile, seed='pdf-worker-probe', count=3)
    document = {'schema_version': 1, 'title': '纸上练运行检查', 'generated_at': serialize_time(beijing_now()),
                'questions': [q.model_dump(mode='json') for q in questions]}
    contents, metadata = render(document, settings)
    from app.services.paper_execution import check_metadata
    from uuid import uuid4
    check_metadata(document, contents, metadata)
    if settings.generated_root.is_symlink():
        raise ValueError('PDF_ROOT_SYMLINK')
    settings.generated_root.mkdir(mode=0o700, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.probe-', dir=settings.generated_root) as directory:
        targets = {kind: PdfTarget(uuid4(), beijing_now()) for kind in contents}
        saved = save_pair(Path(directory) / 'files', targets, contents)
        for asset in saved.values():
            read_verified(Path(directory) / 'files', asset)
