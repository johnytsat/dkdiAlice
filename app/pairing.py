"""Single-use, high-entropy links binding the browser to an Alice account."""
import secrets
import time
from threading import Lock

class PairingError(RuntimeError):
    pass

class PairingCodes:
    def __init__(self):
        self._lock = Lock()
        self._codes = {}

    def issue(self, user_id):
        if not user_id:
            raise PairingError('Sign in to Alice')
        with self._lock:
            now = time.monotonic()
            self._codes = {k: v for k, v in self._codes.items() if v[1] > now and v[0] != user_id}
            if len(self._codes) >= 1000:
                raise PairingError('Too many pending links')
            token = secrets.token_urlsafe(32)
            self._codes[token] = (user_id, now + 600)
            return token

    def verify(self, token):
        with self._lock:
            entry = self._codes.pop(token, None)
            if not entry or entry[1] <= time.monotonic():
                raise PairingError('Expired or used link')
            return entry[0]

    def reset(self):
        with self._lock:
            self._codes.clear()

codes = PairingCodes()
