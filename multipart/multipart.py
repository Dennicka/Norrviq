import cgi
from typing import Dict, Tuple


def parse_options_header(value: str | None) -> Tuple[str, Dict[str, str]]:
    """Lightweight replacement for python-multipart's helper.

    This is sufficient for test environments that rely on basic form submissions
    with ``application/x-www-form-urlencoded`` payloads.
    """

    if not value:
        return "", {}

    main_value, params = cgi.parse_header(value)
    return main_value, params
