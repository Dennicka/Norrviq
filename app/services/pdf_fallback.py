from __future__ import annotations

import html as html_lib
import re

_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"[ \t\x0b\x0c\r]+")


def html_to_plain_text(html: str) -> str:
    text = html or ""
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"(?i)</?(p|div|li|ul|ol|h[1-6]|tr|table|section|article|br)[^>]*>", "\n", text)
    text = _TAG_RE.sub(" ", text)
    text = html_lib.unescape(text)
    lines = []
    for raw in text.splitlines():
        line = _WHITESPACE_RE.sub(" ", raw).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def _pdf_escape(text: str) -> str:
    encoded = text.encode("latin-1", errors="replace").decode("latin-1")
    encoded = encoded.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return encoded


def render_simple_pdf_from_text(text: str, *, title: str | None = None) -> bytes:
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    if not lines:
        lines = [" "]

    max_lines_per_page = 48
    pages: list[list[str]] = [lines[i : i + max_lines_per_page] for i in range(0, len(lines), max_lines_per_page)]

    objects: list[bytes] = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")

    page_ids = []
    content_ids = []
    next_id = 3
    for _ in pages:
        page_ids.append(next_id)
        next_id += 1
        content_ids.append(next_id)
        next_id += 1

    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode())

    font_obj_id = next_id
    next_id += 1
    info_obj_id = next_id

    for idx, page_lines in enumerate(pages):
        page_obj = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 {font_obj_id} 0 R >> >> /Contents {content_ids[idx]} 0 R >>"
        )
        objects.append(page_obj.encode())

        y = 800
        stream_lines = ["BT", "/F1 11 Tf", "36 0 0 36 36 0 Tm", "1 0 0 1 0 0 cm"]
        for line in page_lines:
            stream_lines.append(f"1 0 0 1 0 {y - 800} Tm")
            stream_lines.append(f"({_pdf_escape(line)}) Tj")
            y -= 16
        stream_lines.append("ET")
        stream = "\n".join(stream_lines).encode("latin-1", errors="replace")
        content_obj = b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
        objects.append(content_obj)

    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")

    clean_title = _pdf_escape(title or "Document")
    objects.append(f"<< /Title ({clean_title}) /Producer (Portable PDF fallback) >>".encode("latin-1", errors="replace"))

    out = bytearray()
    out.extend(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")

    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out.extend(f"{i} 0 obj\n".encode())
        out.extend(obj)
        out.extend(b"\nendobj\n")

    xref_start = len(out)
    out.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    out.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode())

    out.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R /Info {info_obj_id} 0 R >>\n"
            f"startxref\n{xref_start}\n%%EOF"
        ).encode()
    )
    return bytes(out)


def render_pdf_fallback_from_html(html: str, *, title: str | None = None) -> bytes:
    return render_simple_pdf_from_text(html_to_plain_text(html), title=title)
