import requests
import json
import os
from datetime import datetime, timedelta

# ============================================================
#  НАСТРОЙКИ
# ============================================================
SUBDOMAIN       = os.environ.get("SUBDOMAIN", "yourcompany")
LONG_TERM_TOKEN = os.environ.get("LONG_TERM_TOKEN", "ВАШ_ДОЛГОСРОЧНЫЙ_ТОКЕН")

FIXED_USER_ID       = 11206022   # ID ответственного сотрудника
TASK_TEXT           = "Новая заявка! Свяжитесь с клиентом в течение 1 часа."
TASK_DEADLINE_HOURS = 2          # через сколько часов дедлайн задачи
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


def has_existing_tasks(lead_id: int) -> bool:
    """Проверяет, есть ли уже задачи у заявки."""
    url = f"{BASE_URL}/tasks"
    params = {
        "filter[entity_type]": "leads",
        "filter[entity_id]": lead_id,
        "limit": 1,
    }
    response = requests.get(url, headers=HEADERS, params=params)
    if response.status_code == 204:
        return False  # задач нет
    response.raise_for_status()
    tasks = response.json().get("_embedded", {}).get("tasks", [])
    return len(tasks) > 0


def set_responsible_user(lead_id: int):
    """Назначает ответственного сотрудника в заявке."""
    url = f"{BASE_URL}/leads"
    payload = [
        {
            "id": lead_id,
            "responsible_user_id": FIXED_USER_ID,
        }
    ]
    response = requests.patch(url, headers=HEADERS, json=payload)
    response.raise_for_status()


def create_task(lead_id: int):
    """Создаёт задачу на фиксированного сотрудника."""
    deadline_ts = int((datetime.now() + timedelta(hours=TASK_DEADLINE_HOURS)).timestamp())
    url = f"{BASE_URL}/tasks"
    payload = [
        {
            "responsible_user_id": FIXED_USER_ID,
            "entity_id": lead_id,
            "entity_type": "leads",
            "task_type_id": 1,       # 1 = Связаться
            "text": TASK_TEXT,
            "complete_till": deadline_ts,
        }
    ]
    response = requests.post(url, headers=HEADERS, json=payload)
    response.raise_for_status()


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
        lead_id   = lead["id"]
        lead_name = lead.get("name", "Без названия")

        # Проверяем — есть ли уже задача у заявки
        try:
            if has_existing_tasks(lead_id):
                print(f"⏭️  Лид #{lead_id} «{lead_name}» — задача уже есть, пропускаем")
                continue
        except Exception as e:
            print(f"❌ Ошибка проверки задач для лида #{lead_id}: {e}")
            continue

        # 1. Назначаем ответственного в заявке
        try:
            set_responsible_user(lead_id)
            print(f"👤 Ответственный назначен для лида #{lead_id} «{lead_name}»")
        except requests.HTTPError as e:
            print(f"❌ Ошибка назначения ответственного для лида #{lead_id}: {e.response.text}")

        # 2. Создаём задачу на него же
        try:
            create_task(lead_id)
            print(f"✅ Задача создана для лида #{lead_id} «{lead_name}»")
        except requests.HTTPError as e:
            print(f"❌ Ошибка создания задачи для лида #{lead_id}: {e.response.text}")

    save_last_checked(now_ts)
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Проверка завершена.")


if __name__ == "__main__":
    main()
