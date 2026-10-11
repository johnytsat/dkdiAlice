"""Credentials cached in memory and encrypted in a persistent database."""
from dataclasses import dataclass, field, asdict, replace
from threading import RLock
from app.config import settings

@dataclass(frozen=True)
class DikidiCredentials:
    phone: str = ''
    password: str = field(default='', repr=False)
    company_id: str = ''
    default_staff_id: str = ''
    owner_id: str = ''

    @property
    def is_complete(self):
        return bool(self.phone and self.password and self.company_id)

    def masked(self):
        return {'phone': '***' + self.phone[-4:], 'company_id': self.company_id,
                'default_staff_id': self.default_staff_id}

class CredentialStore:
    def __init__(self):
        self._lock = RLock()
        self._credentials = None
        self._listeners = []
        self._db = None

    def on_change(self, callback):
        self._listeners.append(callback)

    def database(self):
        with self._lock:
            if self._db is None:
                from app.credential_db import ConnectionDB
                self._db = ConnectionDB(settings.database_url, settings.credentials_encryption_key)
            return self._db

    def get(self):
        with self._lock:
            if self._credentials is None:
                saved = self.database().load() if settings.database_url else None
                self._credentials = DikidiCredentials(**saved) if saved else DikidiCredentials(
                    phone=settings.dikidi_phone, password=settings.dikidi_password,
                    company_id=settings.dikidi_company_id,
                    default_staff_id=settings.dikidi_default_staff_id,
                    owner_id=settings.alice_owner_id)
            return self._credentials

    def set(self, credentials):
        if not credentials.owner_id:
            raise ValueError('An Alice account is required')
        with self._lock:
            self.database().save(asdict(credentials))
            self._credentials = credentials
        for callback in self._listeners:
            callback()

    def update_staff_id(self, staff_id):
        self.set(replace(self.get(), default_staff_id=staff_id))

    def clear(self):
        """Clear only cache, never the persistent connection."""
        with self._lock:
            self._credentials = None
        for callback in self._listeners:
            callback()

store = CredentialStore()
