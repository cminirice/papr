"""Opt-in built Vue + real HTTP + Chrome + PDF integration on temporary data."""
from contextlib import contextmanager
from dataclasses import replace
import os
from pathlib import Path
import socket
import subprocess
import threading
import time

import pytest
import uvicorn
from fastapi.staticfiles import StaticFiles

from test_paper_execution import prepared, opened, ready, editor, storage, NOW
from app.main import create_app
from app.services import paper_runtime, paper_execution
from app.worker import run_once as validate_once

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(os.environ.get('PAPR_TEST_BROWSER') != '1', reason='Opt-in: real Chrome process cleanup')
def test_real_chrome_timeout_cleanup(tmp_path):
    node = os.environ.get('PAPR_PDF_NODE', '/Users/eric/.local/node-v22.23.2/bin/node')
    browser = os.environ.get('PAPR_PDF_BROWSER', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
    pid_file = tmp_path / 'browser.pid'
    script = tmp_path / 'timeout.mjs'
    import json
    script.write_text(
        f"import {{ chromium }} from {json.dumps((ROOT / 'node_modules/playwright-core/index.mjs').as_uri())};\n"
        f"process.env.PAPR_BROWSER_EXECUTABLE = {json.dumps(browser)};\n"
        f"process.env.PAPR_BROWSER_PID_FILE = {json.dumps(str(pid_file))};\n"
        f"await chromium.launch({{executablePath: {json.dumps(str(ROOT / 'scripts/chrome_worker_launcher.sh'))}, headless: true}});\n"
        "setInterval(() => {}, 1000);\n")
    with pytest.raises(TimeoutError):
        paper_runtime.process([node, str(script)], data='', timeout=8, browser_pid_file=pid_file)
    pid = int(pid_file.read_text())
    deadline = time.monotonic() + 5
    while True:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        assert time.monotonic() < deadline, 'Chrome survived renderer timeout'
        time.sleep(.05)


@contextmanager
def browser_services(engine, base_settings, *, pdf=True, workflow_v2=False):
    settings = replace(base_settings,
        pdf_node=Path(os.environ.get('PAPR_PDF_NODE', '/Users/eric/.local/node-v22.23.2/bin/node')),
        pdf_browser=Path(os.environ.get('PAPR_PDF_BROWSER', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')),
        pdf_font=Path(os.environ.get('PAPR_PDF_FONT', '/System/Library/Fonts/Supplemental/Arial Unicode.ttf')))
    sockets, servers, threads = [], [], []
    stop = threading.Event()
    errors = []
    fingerprint = None
    try:
        for _ in range(2):
            listener = socket.socket()
            listener.bind(('127.0.0.1', 0))
            sockets.append(listener)
        origins = [f'http://127.0.0.1:{s.getsockname()[1]}' for s in sockets]
        settings = replace(settings, user_origins=(origins[0],), admin_origins=(origins[1],))
        for name, listener in zip(('web', 'admin'), sockets):
            app = create_app(settings)
            app.state.clock = lambda: NOW
            app.mount('/', StaticFiles(directory=ROOT / name / 'dist', html=True))
            server = uvicorn.Server(uvicorn.Config(app, log_level='error', proxy_headers=False))
            thread = threading.Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
            servers.append(server)
            threads.append(thread)
            thread.start()
        deadline = time.monotonic() + 10
        while not all(s.started for s in servers):
            assert time.monotonic() < deadline, 'HTTP startup timed out'
            time.sleep(.05)
        if pdf:
            paper_runtime.probe(settings)
            fingerprint = paper_runtime.config_hash(settings)
            paper_runtime.heartbeat(engine, fingerprint, NOW)

        def worker():
            try:
                while not stop.is_set():
                    if fingerprint:
                        paper_runtime.heartbeat(engine, fingerprint, NOW)
                    if workflow_v2:
                        from app.v2.worker import run_once as workflow_once
                        workflow_once(engine, settings, clock=lambda: NOW)
                        stop.wait(.1)
                        continue
                    worked = validate_once(engine, clock=lambda: NOW)
                    if not worked and fingerprint:
                        paper_execution.run_once(engine, settings, clock=lambda: NOW, fingerprint=fingerprint)
                    stop.wait(.1)
            except BaseException as error:
                errors.append(error)

        worker_thread = threading.Thread(target=worker, daemon=True)
        threads.append(worker_thread)
        worker_thread.start()
        yield settings, origins
        assert not errors, errors
    finally:
        stop.set()
        for server in servers:
            server.should_exit = True
        for thread in threads:
            thread.join(timeout=70)
        for listener in sockets:
            listener.close()
        if fingerprint:
            paper_runtime.withdraw(engine, fingerprint, NOW)
        assert not any(t.is_alive() for t in threads), 'Test processes did not stop'


def browser_script(settings, origins, script, tmp_path):
    result = subprocess.run([str(settings.pdf_node), str(ROOT / 'scripts' / script),
        str(settings.pdf_browser), *origins, str(tmp_path)], capture_output=True, text=True, timeout=240)
    assert result.returncode == 0, result.stdout + result.stderr
    print(result.stdout)


@pytest.mark.skipif(os.environ.get('PAPR_TEST_BROWSER') != '1', reason='Opt-in: real Chrome and local listeners')
def test_browser_generation_history_and_admin(prepared, tmp_path):
    engine, client, *_ = prepared
    with browser_services(engine, client.app.state.settings) as (settings, origins):
        browser_script(settings, origins, 'browser_smoke.mjs', tmp_path)


@pytest.mark.skipif(os.environ.get('PAPR_TEST_BROWSER') != '1', reason='Opt-in: real admin publication workflow')
def test_browser_full_publication(editor, tmp_path):
    engine, client, *_ = editor  # Seeded draft only; no validation/review/release fixture.
    with browser_services(engine, client.app.state.settings, pdf=False) as (settings, origins):
        browser_script(settings, origins, 'browser_publication.mjs', tmp_path)


@pytest.mark.skipif(os.environ.get('PAPR_TEST_BROWSER') != '1', reason='Opt-in: real Chrome information pages')
def test_browser_information_pages(editor, tmp_path):
    engine, client, *_ = editor
    with browser_services(engine, client.app.state.settings, pdf=False) as (settings, origins):
        browser_script(settings, origins, 'browser_information.mjs', tmp_path)


@pytest.mark.skipif(os.environ.get('PAPR_TEST_BROWSER') != '1', reason='Opt-in: real Chrome catalog maintenance')
def test_browser_catalog_maintenance(editor, tmp_path):
    engine, client, *_ = editor
    with browser_services(engine, client.app.state.settings, pdf=False) as (settings, origins):
        browser_script(settings, origins, 'browser_catalog.mjs', tmp_path)


@pytest.mark.skipif(os.environ.get('PAPR_TEST_BROWSER') != '1', reason='Opt-in: real Chrome knowledge maintenance')
def test_browser_knowledge_maintenance(editor, tmp_path):
    engine, client, *_ = editor
    with browser_services(engine, client.app.state.settings, pdf=False) as (settings, origins):
        browser_script(settings, origins, 'browser_knowledge.mjs', tmp_path)


@pytest.mark.skipif(os.environ.get('PAPR_TEST_BROWSER') != '1', reason='Opt-in: real Chrome template tools')
def test_browser_template_tools(editor, tmp_path):
    engine, client, *_ = editor
    with browser_services(engine, client.app.state.settings, pdf=False) as (settings, origins):
        browser_script(settings, origins, 'browser_template_tools.mjs', tmp_path)
