from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
import os
import stat
import subprocess
import sys
from uuid import uuid4

import pytest

from app.services import pdf_storage as storage
from app.services.pdf_storage import PdfStorageError, PdfTarget, read_verified, save_pair
from test_pdf_inspection_macos import fixture_pdf


@pytest.fixture
def inputs(tmp_path):
    # Registration is before Beijing midnight; no save-time clock is consulted.
    now = datetime(2030, 1, 1, 15, 59, 59, tzinfo=timezone.utc)
    targets = {kind: PdfTarget(uuid4(), now) for kind in storage.KINDS}
    contents = {'student_pdf': fixture_pdf(), 'solution_pdf': fixture_pdf() + b'\n% solution\n'}
    return tmp_path / 'generated', targets, contents


def fake_inspector(content):
    # Isolate storage tests from the OS parser. These are NOT renderer tests.
    return {'pdf_parser_checked': True, 'pages': 2 if b'% solution' in content else 1,
            'parser': 'test-double', 'byte_size': len(content), 'sha256': sha256(content).hexdigest()}


def save(inputs, inspector=fake_inspector):
    return save_pair(*inputs, inspector=inspector)


def test_pair_saved_and_read_with_registration_date_and_private_permissions(inputs):
    root, targets, contents = inputs
    saved = save(inputs)
    assert {t.date for t in targets.values()} == {'20300101'}
    for kind, asset in saved.items():
        path = root / asset.target.storage_key
        assert path.read_bytes() == read_verified(root, asset) == contents[kind]
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert len(list(root.rglob('*.pdf'))) == 2
    assert not list(root.rglob('*.tmp'))


def test_beijing_midnight_and_no_arbitrary_paths():
    target = PdfTarget(uuid4(), datetime(2030, 1, 1, 16, tzinfo=timezone.utc))
    assert target.date == '20300102'
    with pytest.raises(ValueError):
        PdfTarget('../../outside', target.registered_at)
    with pytest.raises(ValueError):
        PdfTarget(uuid4(), datetime(2030, 1, 1))


@pytest.mark.parametrize('failure', ['missing', 'same_id', 'broken', 'oversize', 'parser', 'hash', 'pages'])
def test_invalid_pair_never_written(inputs, monkeypatch, failure):
    root, targets, contents = inputs
    inspector = fake_inspector
    if failure == 'missing':
        contents.pop('solution_pdf')
    elif failure == 'same_id':
        targets['solution_pdf'] = targets['student_pdf']
    elif failure == 'broken':
        contents['solution_pdf'] = b'not a PDF'
    elif failure == 'oversize':
        monkeypatch.setattr(storage, 'MAX_PDF_BYTES', 100)
    elif failure == 'parser':
        inspector = lambda data: {**fake_inspector(data), 'pdf_parser_checked': False}
    elif failure == 'hash':
        inspector = lambda data: {**fake_inspector(data), 'sha256': '0' * 64}
    elif failure == 'pages':
        inspector = lambda data: {**fake_inspector(data), 'pages': 1}
    with pytest.raises((PdfStorageError, ValueError)):
        save(inputs, inspector)
    assert not root.exists()


def test_existing_file_never_overwritten(inputs):
    root, targets, contents = inputs
    original = save(inputs)
    contents['student_pdf'] += b'\n% changed\n'
    with pytest.raises(PdfStorageError):
        save(inputs)
    assert read_verified(root, original['student_pdf']) == fixture_pdf()
    assert not list(root.rglob('*.tmp'))


def test_concurrent_same_reservation_has_one_winner(inputs):
    def attempt(_):
        try:
            return save(inputs)
        except PdfStorageError:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, range(2)))
    assert sum(result is not None for result in results) == 1
    assert len(list(inputs[0].rglob('*.pdf'))) == 2
    assert not list(inputs[0].rglob('*.tmp'))


def test_failure_after_first_publication_preserves_orphan_and_retry_uses_new_ids(inputs, monkeypatch):
    root, targets, contents = inputs
    link = os.link
    def fail_second(src, dst, **kwargs):
        if dst == targets['solution_pdf'].filename:
            raise OSError('simulated disk failure')
        return link(src, dst, **kwargs)
    monkeypatch.setattr(storage.os, 'link', fail_second)
    with pytest.raises(PdfStorageError):
        save(inputs)
    orphan = root / targets['student_pdf'].storage_key
    assert orphan.read_bytes() == contents['student_pdf']
    assert len(list(root.rglob('*.pdf'))) == 1
    assert not list(root.rglob('*.tmp'))
    monkeypatch.setattr(storage.os, 'link', link)
    new_targets = {kind: PdfTarget(uuid4(), target.registered_at) for kind, target in targets.items()}
    assert len(save_pair(root, new_targets, contents, inspector=fake_inspector)) == 2
    assert orphan.read_bytes() == contents['student_pdf']


def test_file_sync_failure_never_publishes(inputs, monkeypatch):
    fsync = os.fsync
    def fail_file(fd):
        if stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError('simulated ENOSPC')
        return fsync(fd)
    monkeypatch.setattr(storage.os, 'fsync', fail_file)
    with pytest.raises(PdfStorageError):
        save(inputs)
    assert not list(inputs[0].rglob('*.pdf'))
    assert not list(inputs[0].rglob('*.tmp'))


@pytest.mark.parametrize('mode', ['missing', 'truncated', 'same_size_tamper', 'symlink', 'fifo'])
def test_read_rejects_missing_corrupted_or_special_files(inputs, mode):
    root, _, contents = inputs
    asset = save(inputs)['student_pdf']
    path = root / asset.target.storage_key
    path.unlink()
    if mode == 'truncated':
        path.write_bytes(b'%PDF-')
    elif mode == 'same_size_tamper':
        path.write_bytes(contents['student_pdf'].replace(b'Catalog', b'CATALOG'))
    elif mode == 'symlink':
        other = root / 'other.pdf'
        other.write_bytes(contents['student_pdf'])
        path.symlink_to(other)
    elif mode == 'fifo':
        os.mkfifo(path)
    with pytest.raises(PdfStorageError):
        read_verified(root, asset)


def test_symlink_date_directory_is_rejected(inputs):
    root, targets, _ = inputs
    outside = root.parent / 'outside'
    outside.mkdir()
    root.mkdir()
    (root / targets['student_pdf'].date).symlink_to(outside, target_is_directory=True)
    with pytest.raises(PdfStorageError):
        save(inputs)
    assert not list(outside.iterdir())


def test_parser_timeout_is_sanitized(inputs, monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired('private/path/parser', 10, stderr=b'private')
    monkeypatch.setattr(storage.subprocess, 'run', timeout)
    with pytest.raises(PdfStorageError, match='解析失败或超时') as error:
        storage.inspect_bytes(inputs[2]['student_pdf'])
    assert 'private' not in str(error.value)


@pytest.mark.skipif(sys.platform != 'darwin', reason='CoreGraphics requires macOS')
def test_native_parser_runs_in_real_subprocess(inputs):
    report = storage.inspect_bytes(inputs[2]['student_pdf'])
    assert report['pdf_parser_checked'] and report['pages'] == 1
    assert report['parser'] == 'macOS CoreGraphics'
    with pytest.raises(PdfStorageError):
        storage.inspect_bytes(fixture_pdf(612, 792))
