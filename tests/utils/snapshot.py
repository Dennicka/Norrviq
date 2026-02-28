from __future__ import annotations

import difflib
import re
from pathlib import Path

SNAPSHOT_DIR = Path(__file__).resolve().parents[1] / "snapshots"

_DYNAMIC_PATTERNS: list[tuple[str, str]] = [
    (r'(name=["\']csrf_token["\']\s+value=["\'])[^"\']+(["\'])', r"\1<CSRF>\2"),
    (r'(<meta\s+name=["\']csrf-token["\']\s+content=["\'])[^"\']+(["\'])', r"\1<CSRF>\2"),
    (r"\brequest_id=[A-Za-z0-9\-_.:]+", "request_id=<REQUEST_ID>"),
    (r"\b(created_at|updated_at)\b\s*[:=]\s*[^\s<]+", r"\1=<TIMESTAMP>"),
    (r"\b\d{4}-\d{2}-\d{2}[T ][0-9:.+-]{5,}\b", "<TIMESTAMP>"),
    (r"/(projects|offers|invoices)/\d+", r"/\1/<ID>"),
    (r"\bproject_no\s+\d+\b", "project_no <ID>"),
    (r"\b(OF|TR)-\d{4}-\d{4}\b", "<DOCNO>"),
    (r"(Projekt nr|Project no)\s+\d+", r"\1 <ID>"),
]

_BLACKLIST_LINES = {
    "Download PDF",
    "Finalize",
    "Issue",
    "Issuing...",
    "Finalizing...",
    "PDF-motorns reservläge är aktivt",
    "PDF engine fallback mode active",
    "Активирован резервный режим PDF-движка",
}



def _extract_offer_wrapper(html: str) -> str:
    match = re.search(r'<div class="offer-wrapper">.*?</script>', html, flags=re.DOTALL)
    if match:
        return match.group(0)
    return html



def normalize_document_html(html: str) -> str:
    doc = _extract_offer_wrapper(html)
    doc = re.sub(r"<script.*?</script>", "", doc, flags=re.DOTALL | re.IGNORECASE)
    doc = re.sub(r"<style.*?</style>", "", doc, flags=re.DOTALL | re.IGNORECASE)
    doc = re.sub(r"<!--.*?-->", "", doc, flags=re.DOTALL)

    for pattern, replacement in _DYNAMIC_PATTERNS:
        doc = re.sub(pattern, replacement, doc, flags=re.IGNORECASE)

    doc = re.sub(r"\b(id|invoice_id|offer_id|project_id)\s*[:=]\s*\d+", r"\1=<ID>", doc, flags=re.IGNORECASE)
    doc = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", "<DATE>", doc)

    doc = re.sub(r"</tr>", "\n", doc, flags=re.IGNORECASE)
    doc = re.sub(r"</t[dh]>", " | ", doc, flags=re.IGNORECASE)
    doc = re.sub(r"<(tr|table|thead|tbody|div|p|h1|h2|h3|li|pre|br|a|form|input|button)[^>]*>", "\n", doc, flags=re.IGNORECASE)
    doc = re.sub(r"<t[dh][^>]*>", "", doc, flags=re.IGNORECASE)

    text = re.sub(r"<[^>]+>", "", doc)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"\r", "", text)

    lines: list[str] = []
    for raw_line in text.split("\n"):
        line = re.sub(r"\s+", " ", raw_line).strip(" |")
        if not line or line in _BLACKLIST_LINES:
            continue
        if "Download PDF" in line or "onsubmit=" in line or line == '">':
            continue
        if re.search(r"/offer\?lang=(ru|sv|en)&view=", line):
            continue
        if re.search(r"/invoices/.*\?lang=(ru|sv|en)", line):
            continue
        if line in {"Dokumentspråk:", "Document language:", "Язык документа:"}:
            continue
        lines.append(line)

    return "\n".join(lines) + "\n"



def assert_matches_snapshot(name: str, normalized: str, *, max_diff_lines: int = 80) -> None:
    snapshot_path = SNAPSHOT_DIR / name
    if not snapshot_path.exists():
        raise AssertionError(f"Snapshot missing: {snapshot_path}")

    expected = snapshot_path.read_text(encoding="utf-8")
    if expected == normalized:
        return

    diff = list(
        difflib.unified_diff(
            expected.splitlines(),
            normalized.splitlines(),
            fromfile=str(snapshot_path),
            tofile="current",
            lineterm="",
        )
    )
    snippet = "\n".join(diff[:max_diff_lines])
    raise AssertionError(f"Snapshot mismatch for {name}. Diff (first {max_diff_lines} lines):\n{snippet}")
