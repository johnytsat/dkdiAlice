"""Долгие вызовы SDK не удерживают ответ Алисе; повторная реплика проверяет результат."""
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from time import monotonic

_pool = ThreadPoolExecutor(max_workers=4)
_lock = Lock()
_jobs = {}


def submit(session_id, message_id, work):
    with _lock:
        now = monotonic()
        for key, (_, future, created) in list(_jobs.items()):
            if future.done() and now - created > 600:
                del _jobs[key]
        previous = _jobs.get(session_id)
        if previous:
            old_message, future, created = previous
            # Пока не доставлен результат, новые реплики не запускают запись повторно.
            if message_id in future.seen_ids or not future.done() or not getattr(future, "delivered", False):
                future.seen_ids.add(message_id)
                return future
        if len(_jobs) >= 1000:
            raise RuntimeError("Очередь заполнена")
        future = _pool.submit(work)
        future.seen_ids = {message_id}
        _jobs[session_id] = (message_id, future, now)
        return future
