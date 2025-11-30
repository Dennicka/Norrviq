import hashlib
import hmac
import time
from typing import Optional

from .exc import BadSignature


class TimestampSigner:
    def __init__(self, secret_key: str):
        self.secret_key = secret_key.encode()

    def get_signature(self, value: bytes, timestamp: bytes) -> bytes:
        digest = hmac.new(self.secret_key, value + b"." + timestamp, hashlib.sha256)
        return digest.hexdigest().encode()

    def sign(self, value: bytes) -> bytes:
        timestamp = str(int(time.time())).encode()
        signature = self.get_signature(value, timestamp)
        return value + b"." + timestamp + b"." + signature

    def unsign(self, signed_value: bytes, max_age: Optional[int] = None) -> bytes:
        try:
            value, timestamp, signature = signed_value.rsplit(b".", 2)
        except ValueError as exc:
            raise BadSignature("Bad signature format") from exc

        expected = self.get_signature(value, timestamp)
        if not hmac.compare_digest(signature, expected):
            raise BadSignature("Signature mismatch")

        if max_age is not None:
            try:
                ts_int = int(timestamp.decode())
            except ValueError as exc:
                raise BadSignature("Bad timestamp") from exc
            if time.time() - ts_int > max_age:
                raise BadSignature("Signature expired")

        return value


__all__ = ["TimestampSigner", "BadSignature"]
