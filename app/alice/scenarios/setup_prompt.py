"""Offer a browser login bound to the requesting Alice account."""
from app.alice.models import AliceButton
from app.pairing import codes
from app.config import settings
from app.credentials import store


def handle(body):
    user_id = body.session.user.get('user_id') or body.session.user_id
    if not user_id:
        return 'Войдите в аккаунт Яндекса и откройте навык заново.', {}, None
    owner = store.get().owner_id or settings.alice_owner_id
    if owner and owner != user_id:
        return 'Этот навык доступен только владельцу салона.', {}, None
    if not settings.public_base_url.startswith('https://'):
        return 'Подключение пока не настроено администратором.', {}, None
    if not settings.database_url or len(settings.credentials_encryption_key) < 32:
        return 'Подключение пока недоступно: администратору нужно настроить защищённое хранилище.', {}, None
    token = codes.issue(user_id)
    url = settings.public_base_url.rstrip('/') + '/setup#' + token
    return ('Нажмите «Подключить DIKIDI» и введите телефон и пароль на открывшейся странице. '
            'После подключения вернитесь сюда и скажите «добавь запись».', {},
            [AliceButton(title='Подключить DIKIDI', url=url)])
