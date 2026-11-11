"""A4 PDF integrity inspection: native macOS parser or portable pypdf on Linux."""
import ctypes as c
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile

MAX_PDF_BYTES = 32 * 1024 * 1024


class Point(c.Structure):
    _fields_ = [('x', c.c_double), ('y', c.c_double)]


class Size(c.Structure):
    _fields_ = [('width', c.c_double), ('height', c.c_double)]


class Rect(c.Structure):
    _fields_ = [('origin', Point), ('size', Size)]


def inspect_pdf(path):
    if sys.platform != 'darwin':
        return inspect_pdf_portable(path)
    path = Path(path).resolve(strict=True)
    with path.open('rb') as stream:
        content = stream.read(MAX_PDF_BYTES + 1)
    if len(content) > MAX_PDF_BYTES:
        raise ValueError('PDF超过32MiB上限')
    if len(content) < 100 or not content.startswith(b'%PDF-') or b'%%EOF' not in content[-1024:]:
        raise ValueError('PDF头尾或文件大小无效')
    cf = c.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
    cg = c.CDLL('/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics')
    cf.CFURLCreateFromFileSystemRepresentation.argtypes = [c.c_void_p, c.c_char_p, c.c_long, c.c_ubyte]
    cf.CFURLCreateFromFileSystemRepresentation.restype = c.c_void_p
    cf.CFRelease.argtypes = [c.c_void_p]
    cf.CFRelease.restype = None
    cg.CGPDFDocumentCreateWithURL.argtypes = [c.c_void_p]
    cg.CGPDFDocumentCreateWithURL.restype = c.c_void_p
    cg.CGPDFDocumentGetNumberOfPages.argtypes = [c.c_void_p]
    cg.CGPDFDocumentGetNumberOfPages.restype = c.c_size_t
    cg.CGPDFDocumentIsEncrypted.argtypes = [c.c_void_p]
    cg.CGPDFDocumentIsEncrypted.restype = c.c_bool
    cg.CGPDFDocumentGetPage.argtypes = [c.c_void_p, c.c_size_t]
    cg.CGPDFDocumentGetPage.restype = c.c_void_p
    cg.CGPDFPageGetBoxRect.argtypes = [c.c_void_p, c.c_int]
    cg.CGPDFPageGetBoxRect.restype = Rect
    cg.CGPDFDocumentRelease.argtypes = [c.c_void_p]
    cg.CGPDFDocumentRelease.restype = None
    raw_path = str(path).encode('utf-8')
    url = cf.CFURLCreateFromFileSystemRepresentation(None, raw_path, len(raw_path), False)
    if not url:
        raise ValueError('无法创建文件URL')
    document = None
    try:
        document = cg.CGPDFDocumentCreateWithURL(url)
        if not document or cg.CGPDFDocumentIsEncrypted(document):
            raise ValueError('PDF无法解析或已加密')
        count = cg.CGPDFDocumentGetNumberOfPages(document)
        if not 1 <= count <= 100:
            raise ValueError('PDF页数无效')
        dimensions = []
        for index in range(1, count + 1):
            page = cg.CGPDFDocumentGetPage(document, index)
            if not page:
                raise ValueError('PDF页面无法读取')
            box = cg.CGPDFPageGetBoxRect(page, 0)  # kCGPDFMediaBox from the installed Apple SDK.
            if not (abs(box.size.width - 595.276) <= 2 and abs(box.size.height - 841.89) <= 2):
                raise ValueError('PDF不是纵向A4页面')
            dimensions.append([round(box.size.width, 2), round(box.size.height, 2)])
        return {'parser': 'macOS CoreGraphics', 'pdf_parser_checked': True, 'pages': count,
                'page_sizes_pt': dimensions, 'byte_size': len(content), 'sha256': sha256(content).hexdigest(),
                'visual_review': 'pending', 'font_coverage_review': 'pending', 'production_ready': False}
    finally:
        if document:
            cg.CGPDFDocumentRelease(document)
        cf.CFRelease(url)


def inspect_pdf_portable(path):
    """Bounded file, strict parser, no encrypted/empty/non-A4/rotated documents."""
    from io import BytesIO
    import math
    from pypdf import PdfReader
    from pypdf.errors import PyPdfError
    path = Path(path).resolve(strict=True)
    with path.open('rb') as stream:
        content = stream.read(MAX_PDF_BYTES + 1)
    if len(content) > MAX_PDF_BYTES:
        raise ValueError('PDF超过32MiB上限')
    if len(content) < 100 or not content.startswith(b'%PDF-') or b'%%EOF' not in content[-1024:]:
        raise ValueError('PDF头尾或文件大小无效')
    try:
        reader = PdfReader(BytesIO(content), strict=True)
        if reader.is_encrypted:
            raise ValueError('PDF不可加密')
        count = len(reader.pages)
        if not 1 <= count <= 100:
            raise ValueError('PDF页数无效')
        dimensions = []
        for page in reader.pages:
            width, height = float(page.mediabox.width), float(page.mediabox.height)
            if (not math.isfinite(width) or not math.isfinite(height)
                or abs(width - 595.276) > 2 or abs(height - 841.89) > 2
                or page.rotation % 360 != 0 or float(page.get('/UserUnit', 1)) != 1):
                raise ValueError('PDF不是纵向A4页面')
            dimensions.append([round(width, 2), round(height, 2)])
        return {'parser': 'pypdf', 'pdf_parser_checked': True, 'pages': count,
                'page_sizes_pt': dimensions, 'byte_size': len(content), 'sha256': sha256(content).hexdigest(),
                'visual_review': 'pending', 'font_coverage_review': 'pending', 'production_ready': False}
    except (PyPdfError, KeyError, TypeError, OverflowError) as error:
        raise ValueError('PDF无法完整解析') from error


def main():
    """Private subprocess protocol: bounded PDF bytes on stdin, JSON on stdout."""
    content = sys.stdin.buffer.read(MAX_PDF_BYTES + 1)
    if len(content) > MAX_PDF_BYTES:
        raise SystemExit(1)
    try:
        with tempfile.TemporaryDirectory(prefix='papr-pdf-inspect-') as directory:
            path = Path(directory) / 'input.pdf'
            path.write_bytes(content)
            print(json.dumps(inspect_pdf(path)))
    except (ValueError, OSError):
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
