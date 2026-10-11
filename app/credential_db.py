"""Encrypted single-salon connection; key stays outside the database."""
import base64
import hashlib
import json
from threading import Lock

from cryptography.fernet import Fernet
from sqlalchemy import create_engine, MetaData, Table, Column, Integer, Text, select
from sqlalchemy.exc import IntegrityError


class ConnectionDB:
    def __init__(self, url, key):
        if not url or len(key) < 32:
            raise RuntimeError("Configure DATABASE_URL and CREDENTIALS_ENCRYPTION_KEY (32+ characters)")
        if url.startswith(("postgres://", "postgresql://")):
            url = "postgresql+psycopg://" + url.split("://", 1)[1]
        self.cipher = Fernet(base64.urlsafe_b64encode(hashlib.sha256(key.encode()).digest()))
        self.engine = create_engine(url, pool_pre_ping=True, hide_parameters=True)
        metadata = MetaData()
        self.table = Table("dikidi_connection", metadata,
                           Column("id", Integer, primary_key=True), Column("payload", Text, nullable=False))
        metadata.create_all(self.engine)
        self.lock = Lock()

    def load(self):
        with self.engine.connect() as conn:
            value = conn.execute(select(self.table.c.payload).where(self.table.c.id == 1)).scalar_one_or_none()
        return self.decode(value) if value else None

    def decode(self, value):
        return json.loads(self.cipher.decrypt(value.encode()).decode())

    def save(self, payload):
        encrypted = self.cipher.encrypt(json.dumps(payload).encode()).decode()
        with self.lock, self.engine.begin() as conn:
            old = conn.execute(select(self.table.c.payload).where(self.table.c.id == 1).with_for_update()).scalar_one_or_none()
            if old:
                if self.decode(old)["owner_id"] != payload["owner_id"]:
                    raise PermissionError("Connection belongs to another Alice user")
                conn.execute(self.table.update().where(self.table.c.id == 1).values(payload=encrypted))
            else:
                try:
                    conn.execute(self.table.insert().values(id=1, payload=encrypted))
                except IntegrityError as exc:
                    raise PermissionError("Connection was claimed concurrently") from exc
