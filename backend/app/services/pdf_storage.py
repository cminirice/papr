"""Private PDF storage primitives, independent of database publication.

The caller must persist pending asset IDs before saving, fence its lease and
publish both assets in the success transaction afterwards. A returned file is
NOT a ready asset. No authorization or public download route lives here.
"""
from contextlib import contextmanager, ExitStack
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from uuid import UUID, uuid4

from app.core.time import to_beijing
from app.services.pdf_inspection import MAX_PDF_BYTES

KINDS = ('student_pdf', 'solution_pdf')
PARSER_TIMEOUT_SECONDS = 10


class PdfStorageError(Exception):
    """Sanitized storage failure; never expose filesystem paths to API clients."""


@dataclass(frozen=True)
class PdfTarget:
    asset_id: UUID
    registered_at: datetime

    def __post_init__(self):
        if not isinstance(self.asset_id, UUID):
            raise ValueError('资产标识必须为UUID')
        object.__setattr__(self, 'registered_at', to_beijing(self.registered_at))

    @property
    def date(self):
        return self.registered_at.strftime('%Y%m%d')

    @property
    def filename(self):
        return f'{self.asset_id}.pdf'

    @property
    def storage_key(self):
        return f'{self.date}/{self.filename}'


@dataclass(frozen=True)
class SavedPdf:
    target: PdfTarget
    byte_size: int
    sha256: str
    pages: int
    parser: str

    def __post_init__(self):
        if (type(self.byte_size) is not int or not 100 <= self.byte_size <= MAX_PDF_BYTES
                or type(self.pages) is not int or not 1 <= self.pages <= 100
                or not re.fullmatch('[0-9a-f]{64}', self.sha256)
                or not self.parser):
            raise ValueError('PDF校验元数据无效')


def inspect_bytes(content):
    """Isolate native parser crashes/timeouts; no browser or shell is started."""
    _check_bytes(content)
    try:
        result = subprocess.run(
            [sys.executable, '-m', 'app.services.pdf_inspection'],
            cwd=Path(__file__).resolve().parents[2], input=content,
            capture_output=True, check=True, timeout=PARSER_TIMEOUT_SECONDS)
        return json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        raise PdfStorageError('PDF解析失败或超时') from None


def _check_bytes(content):
    if (not isinstance(content, bytes) or not 100 <= len(content) <= MAX_PDF_BYTES
            or not content.startswith(b'%PDF-') or b'%%EOF' not in content[-1024:]):
        raise PdfStorageError('PDF字节格式或大小无效')


def _metadata(target, content, report):
    fingerprint = sha256(content).hexdigest()
    if (not isinstance(report, dict) or report.get('pdf_parser_checked') is not True
            or report.get('byte_size') != len(content) or report.get('sha256') != fingerprint):
        raise PdfStorageError('PDF解析结果与文件不一致')
    try:
        return SavedPdf(target, len(content), fingerprint, report['pages'], report['parser'])
    except (ValueError, KeyError, TypeError):
        raise PdfStorageError('PDF解析元数据无效') from None


@contextmanager
def _directory(root, date, *, create):
    """Anchor operations to open directories; reject symlink date directories."""
    root = Path(root)
    if not root.is_absolute():
        raise ValueError('生成文件根目录必须为绝对路径')
    if create:
        # Deployment provisions the parent; sync creation of the root itself too.
        root.mkdir(mode=0o700, exist_ok=True)
        parent_fd = os.open(root.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    root_fd = os.open(root, flags)
    try:
        if create:
            try:
                os.mkdir(date, mode=0o700, dir_fd=root_fd)
            except FileExistsError:
                pass
            os.fsync(root_fd)
        date_fd = os.open(date, flags, dir_fd=root_fd)
        try:
            yield date_fd
        finally:
            os.close(date_fd)
    finally:
        os.close(root_fd)


def save_pair(root, targets, contents, *, inspector=inspect_bytes):
    """Validate both PDFs, then durably save under reserved immutable paths.

    Atomic hard-link publication provides no-replace semantics on the same
    filesystem. Failure can leave an invisible orphan; never roll back by
    deleting a final path, which might already belong to a successful commit.
    The caller receives metadata only after BOTH files and directories sync.
    """
    if set(targets) != set(KINDS) or set(contents) != set(KINDS):
        raise ValueError('必须同时提供学生版和解析版')
    if any(not isinstance(t, PdfTarget) for t in targets.values()):
        raise ValueError('资产目标无效')
    if len({t.asset_id for t in targets.values()}) != 2:
        raise ValueError('两版PDF必须使用不同资产标识')
    saved = {}
    for kind in KINDS:
        content = contents[kind]
        _check_bytes(content)
        saved[kind] = _metadata(targets[kind], content, inspector(content))
    if saved['solution_pdf'].pages <= saved['student_pdf'].pages:
        raise PdfStorageError('解析版缺少独立答案页')

    temporary = []
    try:
        with ExitStack() as stack:
            directories = {date: stack.enter_context(_directory(root, date, create=True))
                           for date in sorted({t.date for t in targets.values()})}
            try:
                for kind in KINDS:
                    target = targets[kind]
                    directory = directories[target.date]
                    name = f'.{target.asset_id}.{uuid4()}.tmp'
                    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                 0o600, dir_fd=directory)
                    temporary.append((directory, name))
                    with os.fdopen(fd, 'wb') as stream:
                        stream.write(contents[kind])
                        stream.flush()
                        os.fsync(stream.fileno())
                for kind, (directory, name) in zip(KINDS, temporary, strict=True):
                    # Unlike replace/rename, link fails if a final path already exists.
                    os.link(name, targets[kind].filename, src_dir_fd=directory,
                            dst_dir_fd=directory, follow_symlinks=False)
                    os.fsync(directory)
            finally:
                for directory, name in temporary:
                    os.unlink(name, dir_fd=directory)
                for directory in directories.values():
                    os.fsync(directory)
    except OSError:
        raise PdfStorageError('PDF保存失败，未完成双份文件确认') from None
    return saved


def read_verified(root, asset):
    """Read the exact bytes checked against saved metadata (after caller auth).

    Returning bounded bytes avoids checking one file and subsequently serving
    a replacement through FileResponse. This function cannot confer ready state.
    """
    try:
        with _directory(root, asset.target.date, create=False) as directory:
            fd = os.open(asset.target.filename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=directory)
            with os.fdopen(fd, 'rb') as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size != asset.byte_size:
                    raise PdfStorageError('PDF文件大小或类型不一致')
                content = stream.read(MAX_PDF_BYTES + 1)
        if len(content) != asset.byte_size or sha256(content).hexdigest() != asset.sha256:
            raise PdfStorageError('PDF文件完整性校验失败')
        return content
    except OSError:
        raise PdfStorageError('PDF文件不可用') from None
