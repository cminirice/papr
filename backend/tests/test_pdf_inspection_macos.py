import importlib.util
from pathlib import Path
import sys
import pytest

spec = importlib.util.spec_from_file_location('inspect_pdf_macos', Path(__file__).resolve().parents[2] / 'scripts/inspect_pdf_macos.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
pytestmark = pytest.mark.skipif(sys.platform != 'darwin', reason='Development CoreGraphics parser is macOS only')


def fixture_pdf(width=595.276, height=841.89):
    # Minimal known one-page document; this is parser input, not a rendered papr sample.
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] /Resources << >> /Contents 4 0 R >>'.encode(),
               b'<< /Length 0 >>\nstream\n\nendstream']
    output = b'%PDF-1.4\n'
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(output)); output += f'{index} 0 obj\n'.encode() + obj + b'\nendobj\n'
    xref = len(output)
    output += b'xref\n0 5\n0000000000 65535 f \n'
    output += b''.join(f'{offset:010d} 00000 n \n'.encode() for offset in offsets[1:])
    return output + f'trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode()


def test_native_parser_reads_a4_page_and_fingerprint(tmp_path):
    path = tmp_path / 'valid.pdf'; path.write_bytes(fixture_pdf())
    report = module.inspect_pdf(path)
    assert report['pages'] == 1 and report['pdf_parser_checked']
    assert report['page_sizes_pt'] == [[595.28, 841.89]]
    assert len(report['sha256']) == 64 and not report['production_ready']
    assert report['visual_review'] == 'pending'


def test_native_parser_rejects_non_a4(tmp_path):
    path = tmp_path / 'wrong.pdf'; path.write_bytes(fixture_pdf(612, 792))
    with pytest.raises(ValueError, match='A4'):
        module.inspect_pdf(path)


def test_native_parser_rejects_broken_document(tmp_path):
    path = tmp_path / 'broken.pdf'
    for data in (b'', fixture_pdf()[:-20], b'%PDF-1.4\n' + b'garbage' * 40 + b'\n%%EOF'):
        path.write_bytes(data)
        with pytest.raises(ValueError):
            module.inspect_pdf(path)
