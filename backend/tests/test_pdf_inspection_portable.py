from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest
from pypdf import PdfWriter
from app.services import pdf_inspection, paper_runtime


def document(path, *, width=595.276, rotate=0, encrypted=False, pages=1):
    writer = PdfWriter()
    for _ in range(pages):
        page = writer.add_blank_page(width=width, height=841.89)
        if rotate:
            page.rotate(rotate)
    if encrypted:
        writer.encrypt('test-only')
    writer.write(path)


def test_linux_dispatch_and_integrity(tmp_path, monkeypatch):
    path = tmp_path / 'paper.pdf'
    document(path, pages=2)
    monkeypatch.setattr(pdf_inspection, 'sys', SimpleNamespace(platform='linux'))
    result = pdf_inspection.inspect_pdf(path)
    assert result['parser'] == 'pypdf'
    assert result['pages'] == 2
    assert result['page_sizes_pt'] == [[595.28, 841.89]] * 2
    assert result['sha256'] == sha256(path.read_bytes()).hexdigest()
    assert result['pdf_parser_checked'] and not result['production_ready']


@pytest.mark.parametrize('options', [dict(width=612), dict(rotate=90), dict(encrypted=True), dict(pages=0), dict(pages=101)])
def test_rejects_invalid_documents(tmp_path, options):
    path = tmp_path / 'invalid.pdf'
    document(path, **options)
    with pytest.raises(ValueError):
        pdf_inspection.inspect_pdf_portable(path)


def test_rejects_truncation_and_bad_xref(tmp_path):
    path = tmp_path / 'broken.pdf'
    document(path)
    valid = path.read_bytes()
    for data in (valid[:-30], b'%PDF-1.4\n' + b'garbage' * 40 + b'\n%%EOF'):
        path.write_bytes(data)
        with pytest.raises(ValueError):
            pdf_inspection.inspect_pdf_portable(path)


def test_linux_runtime_accepts_complete_assets(tmp_path, monkeypatch):
    for relative in ['print/dist/document.mjs', 'print/dist/style.css', 'scripts/pdf_renderer.mjs',
                     'scripts/pdf_worker.mjs', 'scripts/chrome_worker_launcher.sh', 'package-lock.json',
                     'node', 'chrome', 'font.otf']:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('fixture')
    monkeypatch.setattr(paper_runtime, 'ROOT', tmp_path)
    monkeypatch.setattr(paper_runtime, 'sys', SimpleNamespace(platform='linux'))
    settings = SimpleNamespace(pdf_node=tmp_path/'node', pdf_browser=tmp_path/'chrome',
                               pdf_font=tmp_path/'font.otf', generated_root=tmp_path/'generated')
    assert paper_runtime.config_hash(settings)
    settings.pdf_browser.unlink()
    assert paper_runtime.config_hash(settings) is None
