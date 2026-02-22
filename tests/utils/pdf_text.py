from __future__ import annotations

import re


def norm_pdf_text(text: str) -> str:
    return re.sub(r"\s+", "", text or "")
