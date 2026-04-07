import requests
import json
import os
from datetime import datetime, timedelta

# ============================================================
#  НАСТРОЙКИ
#  Если запускаете локально — замените значения прямо здесь.
#  Если запускаете через GitHub Actions — оставьте как есть,
#  значения подставятся автоматически из секретов GitHub.
# ============================================================
SUBDOMAIN       = os.environ.get("SUBDOMAIN", "yourcompany")
LONG_TERM_TOKEN = os.environ.get("LONG_TERM_TOKEN", "ВАШ_ДОЛГОСРОЧНЫЙ_ТОКЕН")

TASK_TEXT           = "Новая заявка! Свяжитесь с клиентом в течение 1 часа."
TASK_DEADLINE_HOURS = 2  # через сколько часов дедлайн задачи
# ============================================================

BASE_URL = f"https://{SUBDOMAIN}.amocrm.ru/api/v4"

HEADERS = {
    "Authorization": f"Bearer {LONG_TERM_TOKEN}",
    "Content-Type": "application/json",
}

STATE_FILE = "last_checked.json"


def load_last_checked():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f).get("last_checked", None)
    return None


def save_last_checked(timestamp: int):
    with open(STATE_FILE, "w") as f:
        json.dump({"last_checked": timestamp}, f)


def get_new_leads(since_timestamp: int):
    url = f"{BASE_URL}/leads"
    params = {
        "filter[created_at][from]": since_timestamp,
        "limit": 50,
        "order[created_at]": "asc",
    }
    response = requests.get(url, headers=HEADERS, params=params)
    if response.status_code == 204:
        return []
    response.raise_for_status()
    return response.json().get("_embedded", {}).get("leads", [])


def create_task(lead_id: int, responsible_user_id: int):
    deadline_ts = int((datetime.now() + timedelta(hours=TASK_DEADLINE_HOURS)).timestamp())
    url = f"{BASE_URL}/tasks"
    payload = [
        {
            "responsible_user_id": responsible_user_id,
            "entity_id": lead_id,
            "entity_type": "leads",
            "task_type_id": 1,       # 1 = Связаться
            "text": TASK_TEXT,
            "complete_till": deadline_ts,
        }
    ]
    response = requests.post(url, headers=HEADERS, json=payload)
    response.raise_for_status()
    return response.json()


def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Запуск проверки AmoCRM...")

    last_checked = load_last_checked()
    if last_checked is None:
        last_checked = int((datetime.now() - timedelta(hours=1)).timestamp())
        print("⚠️  Первый запуск — проверяем заявки за последний час")

    now_ts = int(datetime.now().timestamp())

    try:
        leads = get_new_leads(since_timestamp=last_checked)
        print(f"📋 Найдено новых заявок: {len(leads)}")
    except requests.HTTPError as e:
        print(f"❌ Ошибка получения лидов: {e.response.status_code} — {e.response.text}")
        return
    except Exception as e:
        print(f"❌ Неожиданная ошибка: {e}")
        return

    for lead in leads:
        lead_id             = lead["id"]
        lead_name           = lead.get("name", "Без названия")
        responsible_user_id = lead.get("responsible_user_id")
        try:
            create_task(lead_id, responsible_user_id)
            print(f"✅ Задача создана для лида #{lead_id} «{lead_name}»")
        except requests.HTTPError as e:
            print(f"❌ Ошибка для лида #{lead_id}: {e.response.text}")
        except Exception as e:
            print(f"❌ Неожиданная ошибка для лида #{lead_id}: {e}")

    save_last_checked(now_ts)
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Проверка завершена.")


if __name__ == "__main__":
    main()
