"""Проверка связи с реальным аккаунтом Dikidi — только чтение, ничего не создаёт.

Логинится по DIKIDI_PHONE/DIKIDI_PASSWORD/DIKIDI_COMPANY_ID из .env и печатает
ваши услуги, мастеров и записи на сегодня. Пароль не выводится.

Запуск:
    .venv\\Scripts\\python.exe scripts\\check_dikidi.py
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from app.config import settings  # noqa: E402
from app.dikidi.client import DikidiUnavailable  # noqa: E402
from app.dikidi.sdk_client import SdkDikidiClient  # noqa: E402


def main() -> int:
    missing = [
        name
        for name, value in (
            ("DIKIDI_PHONE", settings.dikidi_phone),
            ("DIKIDI_PASSWORD", settings.dikidi_password),
            ("DIKIDI_COMPANY_ID", settings.dikidi_company_id),
        )
        if not value
    ]
    if missing:
        print(f"Не заданы переменные: {', '.join(missing)}")
        print("Скопируйте .env.example в .env и заполните их.")
        return 1

    print(f"Вход в Dikidi: телефон {settings.dikidi_phone}, компания {settings.dikidi_company_id}")
    client = SdkDikidiClient(
        phone=settings.dikidi_phone,
        password=settings.dikidi_password,
        company_id=settings.dikidi_company_id,
        default_staff_id=settings.dikidi_default_staff_id,
    )

    try:
        services = client.list_services()
        print(f"\nУслуги ({len(services)}):")
        for service in services[:40]:
            print(f"  [{service.id}] {service.title} — {service.price:.0f} руб, {service.duration_minutes} мин")
        if len(services) > 40:
            print(f"  ... и ещё {len(services) - 40}")

        masters = client._get_api().catalog.get_masters()
        print(f"\nМастера ({len(masters)}):")
        for master in masters:
            print(f"  [{master.id}] {master.name}")
        print("\nЛюбой из этих id можно прописать в DIKIDI_DEFAULT_STAFF_ID.")

        today = date.today()
        bookings = client.get_bookings_for_date(today)
        print(f"\nЗаписи на {today.strftime('%d.%m.%Y')} ({len(bookings)}):")
        for booking in bookings:
            services_text = ", ".join(booking.service_titles) or "без услуг"
            print(f"  {booking.time.strftime('%H:%M')} — {booking.client_name} ({services_text})")
        if not bookings:
            print("  записей нет")

    except DikidiUnavailable as exc:
        print(f"\nНе удалось получить данные: {exc}")
        print("Проверьте телефон/пароль/company_id. Подробности — выше в трейсбеке.")
        return 1

    print("\nГотово: связь с Dikidi работает.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
