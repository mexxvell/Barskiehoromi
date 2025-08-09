import os
import logging
import threading
import time
import requests
import json
from io import BytesIO
from flask import Flask, request
import telebot
from telebot import types
from datetime import datetime, date
import sqlalchemy
from sqlalchemy import create_engine
# --- ИСПРАВЛЕНО: переименовали импорт text в sql_text для избежания конфликта имен ---
from sqlalchemy import text as sql_text
from sqlalchemy.exc import OperationalError
# --- Настройка логирования ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)
# --- Константы (из Environment Variables) ---
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    logger.error("Переменная TELEGRAM_BOT_TOKEN не установлена")
    raise RuntimeError("TOKEN is required")
OWNER_ID = int(os.getenv("OWNER_TELEGRAM_ID", "0")) or None
if not OWNER_ID:
    logger.error("Переменная OWNER_TELEGRAM_ID не установлена или некорректна")
    raise RuntimeError("OWNER_TELEGRAM_ID is required")
RENDER_URL = os.getenv("RENDER_URL", "https://your-app.onrender.com  ")
WEBHOOK_URL = f"{RENDER_URL}/{TOKEN}"
# --- Настройка PostgreSQL ---
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL:
    # Заменяем префикс для SQLAlchemy
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    try:
        engine = create_engine(DATABASE_URL)
        # Проверяем подключение
        with engine.connect() as conn:
            conn.execute(sql_text("SELECT 1"))
        logger.info("Успешное подключение к PostgreSQL")
    except Exception as e:
        logger.error(f"Ошибка подключения к PostgreSQL: {e}")
        raise
else:
    logger.warning("Переменная DATABASE_URL не установлена. Бот может не работать корректно.")
# --- Импорт для Google Sheets ---
try:
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
    GOOGLE_SHEETS_ENABLED = True
    logger.info("gspread установлен. Интеграция с Google Sheets доступна.")
except ImportError:
    GOOGLE_SHEETS_ENABLED = False
    logger.warning("gspread не установлен. Интеграция с Google Sheets отключена.")
# --- Инициализация БД ---
def init_db():
    try:
        with engine.connect() as conn:
            # корзина (с ценой)
            conn.execute(sql_text('''
                CREATE TABLE IF NOT EXISTS merch_cart (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER,
                    item TEXT,
                    quantity INTEGER,
                    price INTEGER
                )
            '''))
            # лог уникальных пользователей
            conn.execute(sql_text('''
                CREATE TABLE IF NOT EXISTS user_log (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER,
                    date TEXT
                )
            '''))
            # таблица заказов с статусами
            conn.execute(sql_text('''
                CREATE TABLE IF NOT EXISTS merch_orders (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER,
                    username TEXT,
                    item TEXT,
                    quantity INTEGER,
                    price INTEGER,
                    total INTEGER,
                    date TEXT,
                    status TEXT
                )
            '''))
            # таблица отложенных (pending) заказов, ожидающих подтверждения владельца
            conn.execute(sql_text('''
                CREATE TABLE IF NOT EXISTS merch_pending (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER,
                    username TEXT,
                    items_json TEXT,
                    total INTEGER,
                    date TEXT
                )
            '''))
            # подписчики на события
            conn.execute(sql_text('''
                CREATE TABLE IF NOT EXISTS subscriptions (
                    user_id INTEGER PRIMARY KEY,
                    date_subscribed TEXT,
                    username TEXT
                )
            '''))
            # таблица отписчиков
            conn.execute(sql_text('''
                CREATE TABLE IF NOT EXISTS unsubscriptions (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER,
                    date_unsubscribed TEXT,
                    username TEXT
                )
            '''))
            # таблица рефералов
            conn.execute(sql_text('''
                CREATE TABLE IF NOT EXISTS referrals (
                    user_id INTEGER PRIMARY KEY,
                    referral_code TEXT UNIQUE,
                    referred_by INTEGER,
                    referrals_count INTEGER DEFAULT 0,
                    bonus_points INTEGER DEFAULT 0,
                    date_registered TEXT
                )
            '''))
            conn.commit()
    except Exception as e:
        logger.error(f"Ошибка инициализации базы данных: {e}")
        raise
init_db()
# --- Интеграция с Google Sheets ---
if GOOGLE_SHEETS_ENABLED:
    def init_gspread():
        try:
            credentials_path = os.getenv("GOOGLE_SHEETS_CREDENTIALS_PATH")
            if not credentials_path:
                logger.error("GOOGLE_SHEETS_CREDENTIALS_PATH не установлен")
                return None
            scope = [
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]
            creds = ServiceAccountCredentials.from_json_keyfile_name(
                credentials_path, 
                scope
            )
            client = gspread.authorize(creds)
            return client
        except Exception as e:
            logger.error(f"Ошибка инициализации Google Sheets: {e}")
            return None
    gs_client = init_gspread()
    SPREADSHEET_ID = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
    if not SPREADSHEET_ID:
        logger.warning("GOOGLE_SHEETS_SPREADSHEET_ID не установлен")
def log_order_to_google_sheets(order_id, user_id, username, item, quantity, price, total, date, status):
    """Записывает информацию о заказе в Google Таблицу"""
    if not GOOGLE_SHEETS_ENABLED or not gs_client or not SPREADSHEET_ID:
        return False
    try:
        sheet = gs_client.open_by_key(SPREADSHEET_ID).worksheet("Заказы")
        # Добавляем новую строку
        sheet.append_row([
            order_id,
            user_id,
            username or f"ID:{user_id}",
            item,
            quantity,
            price,
            total,
            date,
            status,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # Время записи
        ])
        return True
    except Exception as e:
        logger.error(f"Ошибка записи заказа в Google Sheets: {e}")
        return False
def log_subscription_to_google_sheets(user_id, date_subscribed, username):
    """Записывает информацию о подписке в Google Таблицу"""
    if not GOOGLE_SHEETS_ENABLED or not gs_client or not SPREADSHEET_ID:
        return False
    try:
        sheet = gs_client.open_by_key(SPREADSHEET_ID).worksheet("Подписчики")
        sheet.append_row([
            user_id,
            username or f"ID:{user_id}",
            date_subscribed,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # Время записи
        ])
        return True
    except Exception as e:
        logger.error(f"Ошибка записи подписки в Google Sheets: {e}")
        return False
def log_unsubscription_to_google_sheets(user_id, date_unsubscribed, username):
    """Записывает информацию об отписке в Google Таблицу"""
    if not GOOGLE_SHEETS_ENABLED or not gs_client or not SPREADSHEET_ID:
        return False
    try:
        sheet = gs_client.open_by_key(SPREADSHEET_ID).worksheet("Отписчики")
        sheet.append_row([
            user_id,
            username or f"ID:{user_id}",
            date_unsubscribed,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # Время записи
        ])
        return True
    except Exception as e:
        logger.error(f"Ошибка записи отписки в Google Sheets: {e}")
        return False
def log_user_to_google_sheets(user_id, date_registered, username):
    """Записывает информацию о новом пользователе в Google Таблицу"""
    if not GOOGLE_SHEETS_ENABLED or not gs_client or not SPREADSHEET_ID:
        return False
    try:
        sheet = gs_client.open_by_key(SPREADSHEET_ID).worksheet("Пользователи")
        sheet.append_row([
            user_id,
            username or f"ID:{user_id}",
            date_registered,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # Время записи
        ])
        return True
    except Exception as e:
        logger.error(f"Ошибка записи пользователя в Google Sheets: {e}")
        return False
def log_referral_to_google_sheets(user_id, referrer_id, referral_code, date_registered, username):
    """Записывает информацию о реферале в Google Таблицу"""
    if not GOOGLE_SHEETS_ENABLED or not gs_client or not SPREADSHEET_ID:
        return False
    try:
        sheet = gs_client.open_by_key(SPREADSHEET_ID).worksheet("Рефералы")
        sheet.append_row([
            user_id,
            username or f"ID:{user_id}",
            referrer_id or "Нет",
            referral_code,
            date_registered,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # Время записи
        ])
        return True
    except Exception as e:
        logger.error(f"Ошибка записи реферала в Google Sheets: {e}")
        return False
# --- Инициализация бота и Flask ---
app = Flask(__name__)
bot = telebot.TeleBot(TOKEN)
bot.remove_webhook()
bot.set_webhook(url=WEBHOOK_URL)
# --- Словарь товаров мерча (название: (цена, файл фото или список фото)) ---
MERCH_ITEMS = {
    "👜 Сумка Шоппер":   (500, ["shopper.jpg", "shopper1.jpg"]),
    "☕ Кружки":    (300, "mug.jpg"),
    "👕 Футболки":  (800, "tshirt.jpg")
}
# --- Rate limiting (защита от спама) ---
# структура: last_action_time["{user_id}:{action}"] = timestamp
last_action_time = {}
DEFAULT_LIMIT_SECONDS = 2  # минимальное время между действиями
def allowed_action(user_id: int, action: str, limit_seconds: int = DEFAULT_LIMIT_SECONDS):
    key = f"{user_id}:{action}"
    now = time.time()
    last = last_action_time.get(key, 0)
    if now - last < limit_seconds:
        return False
    last_action_time[key] = now
    return True
def send_rate_limited_message(chat_id):
    try:
        bot.send_message(chat_id, "⏳ Подожди немного перед следующим действием (защита от спама).")
    except Exception as e:
        logger.debug(f"Не удалось отправить сообщение о лимите: {e}")
# --- Уникальные пользователи лог ---
def log_user(user_id):
    today = str(date.today())
    try:
        with engine.connect() as conn:
            result = conn.execute(sql_text(
                "SELECT 1 FROM user_log WHERE user_id = :user_id AND date = :today"
            ), {"user_id": user_id, "today": today})
            if not result.fetchone():
                conn.execute(sql_text(
                    "INSERT INTO user_log (user_id, date) VALUES (:user_id, :today)"
                ), {"user_id": user_id, "today": today})
                conn.commit()
    except Exception as e:
        logger.error(f"Ошибка записи в БД: {e}")
# --- Рассылка статистики владельцу (ежедневно в 23:59) ---
def send_daily_stats():
    while True:
        now = datetime.now()
        if now.hour == 23 and now.minute == 59:
            today = str(date.today())
            try:
                with engine.connect() as conn:
                    result = conn.execute(sql_text(
                        "SELECT COUNT(DISTINCT user_id) FROM user_log WHERE date = :today"
                    ), {"today": today})
                    count = result.fetchone()[0]
                try:
                    bot.send_message(OWNER_ID, f"📊 Уникальных пользователей за {today}: {count}")
                except Exception as e:
                    logger.error(f"Ошибка при отправке статистики владельцу: {e}")
            except Exception as e:
                logger.error(f"Ошибка получения статистики: {e}")
            time.sleep(60)  # ждать минуту, чтобы не продублировать
        time.sleep(10)
threading.Thread(target=send_daily_stats, daemon=True).start()
# --- Автопинг ---
def self_ping():
    while True:
        try:
            requests.get(f"{RENDER_URL}/ping", timeout=5)
            logger.info("Пинг выполнен")
        except Exception as e:
            logger.error(f"Ошибка пинга: {e}")
        time.sleep(300)
threading.Thread(target=self_ping, daemon=True).start()
# --- Вспомогательные DB-функции ---
def add_to_cart_db(user_id, item, quantity, price):
    try:
        with engine.connect() as conn:
            conn.execute(sql_text(
                "INSERT INTO merch_cart (user_id, item, quantity, price) VALUES (:user_id, :item, :quantity, :price)"
            ), {
                "user_id": user_id,
                "item": item,
                "quantity": quantity,
                "price": price
            })
            conn.commit()
    except Exception as e:
        logger.error(f"Ошибка добавления в корзину: {e}")
def get_cart_items(user_id):
    try:
        with engine.connect() as conn:
            result = conn.execute(sql_text(
                "SELECT item, quantity, price FROM merch_cart WHERE user_id = :user_id"
            ), {"user_id": user_id})
            rows = result.fetchall()
            return rows
    except Exception as e:
        logger.error(f"Ошибка получения корзины: {e}")
        return []
def clear_cart(user_id):
    try:
        with engine.connect() as conn:
            conn.execute(sql_text(
                "DELETE FROM merch_cart WHERE user_id = :user_id"
            ), {"user_id": user_id})
            conn.commit()
    except Exception as e:
        logger.error(f"Ошибка очистки корзины: {e}")
def create_pending_from_cart(user_id, username):
    """
    Создаёт запись в merch_pending на основе корзины (не очищает корзину).
    Возвращает (pending_id, items_list, total_sum) или None если корзина пуста.
    """
    items = get_cart_items(user_id)
    if not items:
        return None
    today = str(date.today())
    items_list = []
    total_sum = 0
    for item, qty, price in items:
        total = qty * price
        total_sum += total
        items_list.append({"item": item, "quantity": qty, "price": price, "total": total})
    items_json = json.dumps(items_list, ensure_ascii=False)
    try:
        with engine.connect() as conn:
            result = conn.execute(sql_text(
                "INSERT INTO merch_pending (user_id, username, items_json, total, date) VALUES (:user_id, :username, :items_json, :total, :date) RETURNING id"
            ), {
                "user_id": user_id,
                "username": username,
                "items_json": items_json,
                "total": total_sum,
                "date": today
            })
            pid = result.fetchone()[0]
            conn.commit()
            return pid, items_list, total_sum
    except Exception as e:
        logger.error(f"Ошибка создания pending заказа: {e}")
        return None
def get_pending(pending_id):
    try:
        with engine.connect() as conn:
            result = conn.execute(sql_text(
                "SELECT id, user_id, username, items_json, total, date FROM merch_pending WHERE id = :pending_id"
            ), {"pending_id": pending_id})
            row = result.fetchone()
            return row
    except Exception as e:
        logger.error(f"Ошибка получения pending: {e}")
        return None
def delete_pending(pending_id):
    try:
        with engine.connect() as conn:
            conn.execute(sql_text(
                "DELETE FROM merch_pending WHERE id = :pending_id"
            ), {"pending_id": pending_id})
            conn.commit()
    except Exception as e:
        logger.error(f"Ошибка удаления pending: {e}")
def move_pending_to_orders(pending_id):
    """
    Переносит pending в merch_orders (по каждому item создаёт запись), очищает корзину пользователя.
    """
    row = get_pending(pending_id)
    if not row:
        return False
    _, user_id, username, items_json, total, date_str = row
    try:
        items = json.loads(items_json)
    except:
        items = []
    try:
        with engine.connect() as conn:
            for it in items:
                item = it.get("item")
                qty = int(it.get("quantity", 0))
                price = int(it.get("price", 0))
                total_item = int(it.get("total", qty * price))
                conn.execute(sql_text(
                    "INSERT INTO merch_orders (user_id, username, item, quantity, price, total, date, status) VALUES (:user_id, :username, :item, :quantity, :price, :total, :date, :status)"
                ), {
                    "user_id": user_id,
                    "username": username,
                    "item": item,
                    "quantity": qty,
                    "price": price,
                    "total": total_item,
                    "date": date_str,
                    "status": "В обработке"
                })
                # Логируем заказ в Google Sheets
                if GOOGLE_SHEETS_ENABLED:
                    order_id = conn.execute(sql_text("SELECT LASTVAL()")).fetchone()[0]
                    log_order_to_google_sheets(
                        order_id, user_id, username, item, qty, price, total_item, date_str, "В обработке"
                    )
            # очистить корзину пользователя
            clear_cart(user_id)
            # удалить pending
            delete_pending(pending_id)
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Ошибка переноса pending в заказы: {e}")
        return False
# --- Главное меню ---
@bot.message_handler(commands=["start"])
def start(message):
    # rate limit for main /start
    if not allowed_action(message.chat.id, "start", limit_seconds=1):
        send_rate_limited_message(message.chat.id)
        return
    log_user(message.chat.id)
    # Получаем username пользователя
    username = f"@{message.from_user.username}" if message.from_user.username else None
    # Проверяем, новый ли пользователь
    try:
        with engine.connect() as conn:
            result = conn.execute(sql_text(
                "SELECT 1 FROM referrals WHERE user_id = :user_id"
            ), {"user_id": message.chat.id})
            is_new_user = not bool(result.fetchone())
    except Exception as e:
        logger.error(f"Ошибка проверки пользователя: {e}")
        is_new_user = True
    # Если это реферальный запуск (есть параметр в /start)
    referrer_id = None
    if len(message.text.split()) > 1:
        ref_code = message.text.split()[1]
        try:
            with engine.connect() as conn:
                result = conn.execute(sql_text(
                    "SELECT user_id FROM referrals WHERE referral_code = :ref_code"
                ), {"ref_code": ref_code})
                referrer = result.fetchone()
                if referrer:
                    referrer_id = referrer[0]
        except Exception as e:
            logger.error(f"Ошибка проверки реферального кода: {e}")
    # Если пользователь новый, добавляем его в БД
    if is_new_user:
        # Генерируем уникальный реферальный код
        import random
        import string
        referral_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        # Дата регистрации
        date_registered = str(date.today())
        # Добавляем пользователя в таблицу referrals
        try:
            with engine.connect() as conn:
                conn.execute(sql_text(
                    "INSERT INTO referrals (user_id, referral_code, referred_by, date_registered) VALUES (:user_id, :referral_code, :referred_by, :date_registered)"
                ), {
                    "user_id": message.chat.id,
                    "referral_code": referral_code,
                    "referred_by": referrer_id,
                    "date_registered": date_registered
                })
                conn.commit()
                # Если есть реферер, увеличиваем его счетчик
                if referrer_id:
                    conn.execute(sql_text(
                        "UPDATE referrals SET referrals_count = referrals_count + 1, bonus_points = bonus_points + 10 WHERE user_id = :referrer_id"
                    ), {"referrer_id": referrer_id})
                    conn.commit()
                    # Уведомляем реферера
                    try:
                        with engine.connect() as conn2:
                            result = conn2.execute(sql_text(
                                "SELECT referrals_count FROM referrals WHERE user_id = :referrer_id"
                            ), {"referrer_id": referrer_id})
                            referrals_count = result.fetchone()[0]
                        bot.send_message(referrer_id, f"🎉 Пользователь перешел по вашей реферальной ссылке! "
                                                   f"Вы получили 10 бонусных баллов. Всего приглашено: {referrals_count}")
                    except Exception as e:
                        logger.error(f"Не удалось уведомить реферера {referrer_id}: {e}")
        except Exception as e:
            logger.error(f"Ошибка добавления пользователя в referrals: {e}")
        # Логируем пользователя в Google Sheets
        if GOOGLE_SHEETS_ENABLED:
            log_user_to_google_sheets(message.chat.id, date_registered, username)
        # Если есть реферер, логируем реферальную связь
        if referrer_id:
            log_referral_to_google_sheets(
                message.chat.id, 
                referrer_id, 
                referral_code, 
                date_registered,
                username
            )
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(
        types.KeyboardButton("👥 Команда"),
        types.KeyboardButton("🌍 Путешествия"),
        types.KeyboardButton("🧘 Кундалини-йога"),
        types.KeyboardButton("📸 Медиа"),
        types.KeyboardButton("🛍 Мерч"),
        types.KeyboardButton("🎁 Доп. услуги")
    )
    # --- ИЗМЕНЕНО: обновлено описание разделов ---
    bot.send_message(message.chat.id, "👋 Добро пожаловать!\n"
                "👥 Команда — узнайте о наших преподавателях и их опыте\n"
                "🌍 Путешествия — эксклюзивные туры и духовные ретриты\n"
                "🧘 Кундалини-йога — онлайн и офлайн занятия для трансформации\n"
                "📸 Медиа — фото и видео с наших мероприятий и путешествий\n"
                "🛍 Мерч — одежда и аксессуары для поддержки ScanDream\n"
                "🎁 Доп. услуги — можете подписаться на события, что бы узнать первыми о наших будущих поездках!", reply_markup=kb)
# --- Личный кабинет ---
@bot.message_handler(func=lambda m: m.text == "👤 Личный кабинет")
def personal_cabinet(message):
    if not allowed_action(message.chat.id, "personal_cabinet"):
        send_rate_limited_message(message.chat.id)
        return
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("📦 Мои заказы", "📜 История покупок", "🔗 Реферальная ссылка")
    kb.add("📢 Подписаться на события", "🚫 Отписаться от событий")
    kb.add("🔙 Назад в меню")
    bot.send_message(message.chat.id, "👤 Ваш личный кабинет", reply_markup=kb)
# Обновляем обработчик "Мои заказы"
@bot.message_handler(func=lambda m: m.text == "📦 Мои заказы")
def my_orders(message):
    if not allowed_action(message.chat.id, "my_orders"):
        send_rate_limited_message(message.chat.id)
        return
    try:
        with engine.connect() as conn:
            result = conn.execute(sql_text(
                "SELECT id, item, quantity, price, total, date, status FROM merch_orders WHERE user_id = :user_id ORDER BY id DESC"
            ), {"user_id": message.chat.id})
            rows = result.fetchall()
        if not rows:
            bot.send_message(message.chat.id, "У вас нет заказов.")
            personal_cabinet(message)
            return
        text_lines = []
        for row in rows:
            oid, item, qty, price, total, date_str, status = row
            text_lines.append(f"#{oid} — {item} ×{qty} ({price}₽/шт) = {total}₽ | {status} | {date_str}")
        bot.send_message(message.chat.id, "Ваши заказы:\n" + "\n".join(text_lines))
        # Кнопка для возврата в личный кабинет
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add("👤 Личный кабинет")
        bot.send_message(message.chat.id, "Нажмите 'Личный кабинет' для возврата", reply_markup=kb)
    except Exception as e:
        logger.error(f"Ошибка получения заказов: {e}")
        bot.send_message(message.chat.id, "Произошла ошибка при получении ваших заказов. Попробуйте позже.")
# Добавляем обработчик для истории покупок
@bot.message_handler(func=lambda m: m.text == "📜 История покупок")
def purchase_history(message):
    if not allowed_action(message.chat.id, "purchase_history"):
        send_rate_limited_message(message.chat.id)
        return
    try:
        with engine.connect() as conn:
            result = conn.execute(sql_text(
                "SELECT id, item, quantity, price, total, date, status FROM merch_orders WHERE user_id = :user_id ORDER BY id DESC"
            ), {"user_id": message.chat.id})
            rows = result.fetchall()
        if not rows:
            bot.send_message(message.chat.id, "История покупок пуста.")
            personal_cabinet(message)
            return
        # Формируем сообщение
        text = "История ваших покупок:\n"
        total_spent = 0
        for row in rows:
            oid, item, qty, price, total, date_str, status = row
            text += f"#{oid} — {item} ×{qty} ({price}₽/шт) = {total}₽ | {status} | {date_str}\n"
            total_spent += total
        if total_spent > 0:
            text += f"\nОбщая сумма покупок: {total_spent}₽"
        bot.send_message(message.chat.id, text)
        # Кнопка для возврата в личный кабинет
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add("👤 Личный кабинет")
        bot.send_message(message.chat.id, "Нажмите 'Личный кабинет' для возврата", reply_markup=kb)
    except Exception as e:
        logger.error(f"Ошибка получения истории покупок: {e}")
        bot.send_message(message.chat.id, "Произошла ошибка при получении истории покупок. Попробуйте позже.")
# Добавляем обработчик для реферальной ссылки
@bot.message_handler(func=lambda m: m.text == "🔗 Реферальная ссылка")
def referral_link(message):
    if not allowed_action(message.chat.id, "referral_link"):
        send_rate_limited_message(message.chat.id)
        return
    try:
        with engine.connect() as conn:
            result = conn.execute(sql_text(
                "SELECT referral_code, referrals_count, bonus_points FROM referrals WHERE user_id = :user_id"
            ), {"user_id": message.chat.id})
            referral_info = result.fetchone()
        if not referral_info:
            bot.send_message(message.chat.id, "Ошибка: ваша реферальная информация не найдена.")
            return
        referral_code, referrals_count, bonus_points = referral_info
        referral_link = f"https://t.me/{bot.get_me().username}?start={referral_code}"
        response = f"Ваша реферальная ссылка:\n`{referral_link}`\n"
        response += f"Вы пригласили: {referrals_count} человек\n"
        response += f"Ваши бонусные баллы: {bonus_points}\n"
        response += "Приглашайте друзей и получайте бонусы за каждое приглашение!\n"
        response += "Как это работает:\n"
        response += "1. Поделитесь ссылкой с друзьями\n"
        response += "2. За каждого приглашенного получайте 10 баллов\n"
        response += "3. 50 баллов = скидка 500₽ на мерч или путешествия"
        bot.send_message(message.chat.id, response, parse_mode="Markdown")
        # Кнопка для возврата в личный кабинет
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add("👤 Личный кабинет")
        bot.send_message(message.chat.id, "Нажмите 'Личный кабинет' для возврата", reply_markup=kb)
    except Exception as e:
        logger.error(f"Ошибка получения реферальной информации: {e}")
        bot.send_message(message.chat.id, "Произошла ошибка при получении реферальной информации. Попробуйте позже.")
# --- Разделы (сохранена логика) ---
@bot.message_handler(func=lambda m: m.text == "🌍 Путешествия")
def travels_menu(message):
    if not allowed_action(message.chat.id, "travels_menu"):
        send_rate_limited_message(message.chat.id)
        return
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("📂 Архив путешествий", "🌍 Где мы сейчас", "🔙 Назад к меню")
    bot.send_message(message.chat.id, "✈️ Путешествия: архив и текущее местоположение.", reply_markup=kb)
@bot.message_handler(func=lambda m: m.text == "🧘 Кундалини-йога")
def yoga_menu(message):
    if not allowed_action(message.chat.id, "yoga_menu"):
        send_rate_limited_message(message.chat.id)
        return
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🏢 Офлайн-мероприятия", "💻 Онлайн-йога", "📅 Ближайшие мероприятия", "🔙 Назад к меню")
    bot.send_message(message.chat.id, "🧘 Кундалини-йога: офлайн, онлайн и ближайшие события.", reply_markup=kb)
# --- Онлайн-йога (оставлено как есть, с rate limit где логично) ---
@bot.message_handler(func=lambda m: m.text == "💻 Онлайн-йога")
def online_yoga(message):
    if not allowed_action(message.chat.id, "online_yoga"):
        send_rate_limited_message(message.chat.id)
        return
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("Да, хочу", "Приобрести подписку", "🔙 Назад к онлайн-йоге")
    bot.send_message(message.chat.id, """Это уникальная возможность быть в поле мастера онлайн. Практики диктуемые эпохой Водолея. Медитации. Работа в малых группах.
Занятия проходят каждый вт и чт в 05:00 по мск. Все записи хранятся в канале группы.
Ценность: 2500 рублей месяц, продление - 2300 руб.
Хотите посмотреть пробный класс?""", reply_markup=kb)
@bot.message_handler(func=lambda m: m.text == "Да, хочу")
def try_online_yoga(message):
    if not allowed_action(message.chat.id, "try_online_yoga"):
        send_rate_limited_message(message.chat.id)
        return
    bot.send_message(message.chat.id, "https://disk.yandex.ru/i/nCQFa8edIspzNA  ")
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("Приобрести подписку", "🔙 Назад к онлайн-йоге")
    bot.send_message(message.chat.id, "Если вам понравилось и вы хотели бы дополнительно узнать больше о онлайн занятии, нажмите кнопку приобрести подписку и мы обязательно свяжемся с вами!", reply_markup=kb)
@bot.message_handler(func=lambda m: m.text == "Приобрести подписку")
def buy_subscription(message):
    if not allowed_action(message.chat.id, "buy_subscription"):
        send_rate_limited_message(message.chat.id)
        return
    # Отправляем информацию владельцу
    user_info = f"Пользователь @{message.from_user.username or message.chat.id} хочет приобрести подписку на онлайн-йогу."
    bot.send_message(OWNER_ID, user_info)
    # Сообщаем пользователю
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🔙 Назад к онлайн-йоге")
    bot.send_message(message.chat.id, "Спасибо, что выбрали нас, мы скоро свяжемся с вами! 😊", reply_markup=kb)
@bot.message_handler(func=lambda m: m.text == "🔙 Назад к онлайн-йоге")
def back_to_online_yoga_menu(message):
    if not allowed_action(message.chat.id, "back_to_online_yoga"):
        send_rate_limited_message(message.chat.id)
        return
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🏢 Офлайн-мероприятия", "💻 Онлайн-йога", "📅 Ближайшие мероприятия", "🔙 Назад к меню")
    bot.send_message(message.chat.id, "🧘 Кундалини-йога: офлайн, онлайн и ближайшие события.", reply_markup=kb)
# --- Новые обработчики (как были) ---
@bot.message_handler(func=lambda m: m.text == "📅 Ближайшие мероприятия")
def upcoming_events(message):
    if not allowed_action(message.chat.id, "upcoming_events"):
        send_rate_limited_message(message.chat.id)
        return
    bot.send_message(message.chat.id, """- 10 августа мы отправляемся в «Большой Волжский Путь», путешествие на автодоме из Карелии на фестиваль кундалини-йоги в Волгоград:
7 августа - Тольятти - <a href="https://t.me/+PosQ9pcHMIk4NjQ6  ">Большой класс и саундхидинг</a>
9 августа - Волгоград - <a href="https://t.me/+ii8MpmrGhMo2YTVi  ">Большой класс и саундхилинг</a>
10 августа - площадка 17 фестиваля кундалини-йоги - Большой класс.
11 - 19 августа фестиваль кундалини-йоги (Волгоград)""", parse_mode="HTML")
@bot.message_handler(func=lambda m: m.text == "▶️ YouTube")
def youtube_channel(message):
    if not allowed_action(message.chat.id, "youtube_channel"):
        send_rate_limited_message(message.chat.id)
        return
    bot.send_message(message.chat.id, "https://www.youtube.com/@ScanDreamChannel  ")
@bot.message_handler(func=lambda m: m.text == "📸 Медиа")
def media_menu(message):
    if not allowed_action(message.chat.id, "media_menu"):
        send_rate_limited_message(message.chat.id)
        return
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("▶️ YouTube", "🔙 Назад к меню")
    bot.send_message(message.chat.id, "🎥 Медиа: наши видео на YouTube.", reply_markup=kb)
# --- Доп. услуги: теперь здесь личный кабинет ---
@bot.message_handler(func=lambda m: m.text == "🎁 Доп. услуги")
def services_menu(message):
    if not allowed_action(message.chat.id, "services_menu"):
        send_rate_limited_message(message.chat.id)
        return
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("👤 Личный кабинет", "🔙 Назад к меню")
    bot.send_message(message.chat.id, "🔧 Дополнительные услуги: детали по запросу.", reply_markup=kb)
@bot.message_handler(func=lambda m: m.text == "📢 Подписаться на события")
def subscribe_events(message):
    if not allowed_action(message.chat.id, "subscribe_events"):
        send_rate_limited_message(message.chat.id)
        return
    try:
        # Получаем username пользователя
        username = f"@{message.from_user.username}" if message.from_user.username else None
        date_subscribed = str(date.today())
        with engine.connect() as conn:
            # Проверяем, не отписывался ли пользователь ранее
            result = conn.execute(sql_text(
                "SELECT 1 FROM unsubscriptions WHERE user_id = :user_id"
            ), {"user_id": message.chat.id})
            was_unsubscribed = bool(result.fetchone())
            # Если ранее отписывался, удаляем из таблицы отписчиков
            if was_unsubscribed:
                conn.execute(sql_text(
                    "DELETE FROM unsubscriptions WHERE user_id = :user_id"
                ), {"user_id": message.chat.id})
            # Добавляем в подписчики
            conn.execute(sql_text(
                "INSERT INTO subscriptions (user_id, date_subscribed, username) VALUES (:user_id, :date_subscribed, :username) " +
                "ON CONFLICT (user_id) DO UPDATE SET date_subscribed = EXCLUDED.date_subscribed, username = EXCLUDED.username"
            ), {
                "user_id": message.chat.id,
                "date_subscribed": date_subscribed,
                "username": username
            })
            conn.commit()
        bot.send_message(message.chat.id, "Вы успешно подписались на события. Будем отправлять уведомления о новых ретритах и мероприятиях.")
        # Логируем подписку в Google Sheets
        if GOOGLE_SHEETS_ENABLED:
            log_subscription_to_google_sheets(message.chat.id, date_subscribed, username)
    except Exception as e:
        logger.error(f"Ошибка подписки: {e}")
        bot.send_message(message.chat.id, "Ошибка при подписке. Попробуйте позже.")
@bot.message_handler(func=lambda m: m.text == "🚫 Отписаться от событий")
def unsubscribe_events(message):
    if not allowed_action(message.chat.id, "unsubscribe_events"):
        send_rate_limited_message(message.chat.id)
        return
    try:
        # Получаем username пользователя
        username = f"@{message.from_user.username}" if message.from_user.username else None
        date_unsubscribed = str(date.today())
        with engine.connect() as conn:
            # Удаляем из подписчиков
            conn.execute(sql_text(
                "DELETE FROM subscriptions WHERE user_id = :user_id"
            ), {"user_id": message.chat.id})
            # Добавляем в отписчики
            conn.execute(sql_text(
                "INSERT INTO unsubscriptions (user_id, date_unsubscribed, username) VALUES (:user_id, :date_unsubscribed, :username)"
            ), {
                "user_id": message.chat.id,
                "date_unsubscribed": date_unsubscribed,
                "username": username
            })
            conn.commit()
        bot.send_message(message.chat.id, "Вы отписаны от рассылки событий.")
        # Логируем отписку в Google Sheets
        if GOOGLE_SHEETS_ENABLED:
            log_unsubscription_to_google_sheets(message.chat.id, date_unsubscribed, username)
    except Exception as e:
        logger.error(f"Ошибка отписки: {e}")
        bot.send_message(message.chat.id, "Ошибка при отписке. Попробуйте позже.")
@bot.message_handler(func=lambda m: m.text == "👥 Команда")
def team_menu(message):
    if not allowed_action(message.chat.id, "team_menu"):
        send_rate_limited_message(message.chat.id)
        return
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🏷 О бренде", "🌐 Официальные источники", "🔙 Назад к меню")
    bot.send_message(message.chat.id, """Нас зовут Алексей Бабенко — учитель кундалини-йоги, визионер, путешественник, кинематографист, медиа-продюсер.
Более 20 лет личной практики, 18 лет преподавания. Преподаватель тренинга школы Амрит Нам Саровар (Франция) в России.
Создатель йога-кемпа и ретритов по Карелии, Северной Осетии, Грузии, Армении и Турции.
И Анастасия Голик — сертифицированный инструктор хатха-йоги, аромапрактик, вдохновитель и заботливая спутница ретритов.""", reply_markup=kb)
@bot.message_handler(func=lambda m: m.text == "🏷 О бренде")
def about_brand(message):
    if not allowed_action(message.chat.id, "about_brand"):
        send_rate_limited_message(message.chat.id)
        return
    bot.send_message(message.chat.id, """ScanDream - https://t.me/scandream   - зарегистрированный товарный знак, основная идея которого осознанные творческие коммуникации. ScanDream - это место, где мы пересобираем конструкт Мира, рассматривая и восхищаясь его строением. Быть #scandream - это сканировать свое жизненное предназначение действием и мечтой. В реальности оставаться активным, осознанным и логичным, а мечтать широко, мощно, свободно и не ощущая предела. 
Проект йога-кемп - это творческая интеграция опыта и пользы. Пользы через новые знания и умения. Умения через новые формы.""")
@bot.message_handler(func=lambda m: m.text == "🌐 Официальные источники")
def official_sources(message):
    if not allowed_action(message.chat.id, "official_sources"):
        send_rate_limited_message(message.chat.id)
        return
    bot.send_message(message.chat.id, """ОФИЦИАЛЬНЫЕ ИСТОЧНИКИ взаимодействия с командой ScanDream:
1. Личная страница в ВК Алексея - https://vk.ru/scandream  
2. Моя личная страница в ВК - https://vk.ru/yoga.golik  
3. Официальный ТГ канал ScanDream•Live - https://t.me/scandream  
4. Личный ТГ канал Алексея - https://t.me/scandreamlife  
5. Личный мой ТГ канал - https://t.me/yogagolik_dnevnik  
6. Йога с Алексеем Бабенко в ВК (Петрозаводск) - https://vk.ru/kyogababenko  """)
# Назад
@bot.message_handler(func=lambda m: m.text == "🔙 Назад в меню")
def back_to_menu_from_cabinet(message):
    if not allowed_action(message.chat.id, "back_to_menu"):
        send_rate_limited_message(message.chat.id)
        return
    start(message)
@bot.message_handler(func=lambda m: m.text == "🔙 Назад к меню")
def back_to_menu(message):
    if not allowed_action(message.chat.id, "back_to_menu"):
        send_rate_limited_message(message.chat.id)
        return
    start(message)
# --- Мерч: меню (добавлены кнопки "Мои заказы") ---
@bot.message_handler(func=lambda m: m.text == "🛍 Мерч")
def merch_menu(message):
    if not allowed_action(message.chat.id, "merch_menu"):
        send_rate_limited_message(message.chat.id)
        return
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for name in MERCH_ITEMS:
        kb.add(types.KeyboardButton(name))
    kb.add("🛍️ Корзина", "🔙 Назад к меню", "📦 Мои заказы")
    bot.send_message(message.chat.id, "🛍️ Выберите товар:", reply_markup=kb)
@bot.message_handler(func=lambda m: m.text in MERCH_ITEMS)
def show_merch_item(message):
    if not allowed_action(message.chat.id, "show_merch_item"):
        send_rate_limited_message(message.chat.id)
        return
    name = message.text
    price, photo_file = MERCH_ITEMS[name]
    # Проверяем существование папки photos
    if not os.path.exists("photos"):
        logger.error("Папка photos не найдена")
        bot.send_message(message.chat.id, "Ошибка: папка с изображениями не найдена")
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add("✅ Заказать", "🔙 Назад к Мерч")
        msg = bot.send_message(message.chat.id, "Выберите действие:", reply_markup=kb)
        bot.register_next_step_handler(msg, lambda m: merch_order_choice(m, name))
        return
    # Если это список фото (для Сумка Шоппер)
    if isinstance(photo_file, list):
        media = []
        found_valid_photo = False
        for i, file in enumerate(photo_file):
            file_path = f"photos/{file}"
            if os.path.exists(file_path):
                try:
                    with open(file_path, "rb") as f:
                        photo_data = f.read()
                    photo = BytesIO(photo_data)
                    photo.name = file
                    if i == 0:  # Для первого фото добавляем описание и цену
                        media.append(types.InputMediaPhoto(photo, caption=f"{name[2:]} — {price}₽"))
                    else:
                        media.append(types.InputMediaPhoto(photo))
                    found_valid_photo = True
                    logger.info(f"Фото найдено: {file_path}")
                except Exception as e:
                    logger.error(f"Ошибка при загрузке фото {file}: {e}")
            else:
                logger.warning(f"Файл не найден: {file_path}")
        if media and found_valid_photo:
            try:
                bot.send_media_group(message.chat.id, media)
            except Exception as e:
                logger.error(f"Ошибка при отправке медиа-группы: {e}")
                bot.send_message(message.chat.id, "Ошибка при отправке фото. Проверьте наличие файлов на сервере.")
        else:
            bot.send_message(message.chat.id, f"{name[2:]} — {price}₽")
    # Если это одиночное фото (для других товаров)
    else:
        file_path = f"photos/{photo_file}"
        if os.path.exists(file_path):
            try:
                with open(file_path, "rb") as photo:
                    bot.send_photo(message.chat.id, photo, caption=f"{name[2:]} — {price}₽")
            except Exception as e:
                logger.error(f"Ошибка при загрузке фото: {e}")
                bot.send_message(message.chat.id, f"{name[2:]} — {price}₽")
        else:
            logger.error(f"Файл не найден: {file_path}")
            bot.send_message(message.chat.id, f"{name[2:]} — {price}₽")
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("✅ Заказать", "🔙 Назад к Мерч")
    msg = bot.send_message(message.chat.id, "Выберите действие:", reply_markup=kb)
    bot.register_next_step_handler(msg, lambda m: merch_order_choice(m, name))
def merch_order_choice(message, item_name):
    if not allowed_action(message.chat.id, "merch_order_choice"):
        send_rate_limited_message(message.chat.id)
        return
    if message.text == "✅ Заказать":
        msg = bot.send_message(message.chat.id, "Сколько штук добавить?")
        bot.register_next_step_handler(msg, lambda m: add_merch_quantity(m, item_name))
    else:
        merch_menu(message)
def add_merch_quantity(message, item_name):
    if not allowed_action(message.chat.id, "add_merch_quantity", limit_seconds=2):
        send_rate_limited_message(message.chat.id)
        return
    try:
        qty = int(message.text)
        if qty < 1:
            raise ValueError
    except:
        msg = bot.send_message(message.chat.id, "Введите корректное число (>0):")
        bot.register_next_step_handler(msg, lambda m: add_merch_quantity(m, item_name))
        return
    # цена из словаря
    price = MERCH_ITEMS[item_name][0]
    # сохраняем в корзину с ценой
    add_to_cart_db(message.chat.id, item_name[2:], qty, price)
    bot.send_message(message.chat.id, f"✔️ Добавлено: {item_name[2:]} ×{qty} ({price}₽/шт)")
    merch_menu(message)
@bot.message_handler(func=lambda m: m.text == "🛍️ Корзина")
def show_merch_cart(message):
    if not allowed_action(message.chat.id, "show_merch_cart", limit_seconds=2):
        send_rate_limited_message(message.chat.id)
        return
    rows = get_cart_items(message.chat.id)
    if not rows:
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add("🔙 Назад к Мерч")
        bot.send_message(message.chat.id, "Корзина пуста.", reply_markup=kb)
        return
    lines = []
    total = 0
    for item, qty, price in rows:
        line_sum = qty * price
        lines.append(f"- {item}: {qty} × {price}₽ = {line_sum}₽")
        total += line_sum
    text = "\n".join(lines) + f"\nИтого: {total}₽"
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("✅ Оформить заказ", "🗑 Очистить корзину", "🔙 Назад к Мерч")
    bot.send_message(message.chat.id, f"🛒 Корзина:\n{text}", reply_markup=kb)
@bot.message_handler(func=lambda m: m.text == "🗑 Очистить корзину")
def clear_cart_handler(message):
    if not allowed_action(message.chat.id, "clear_cart", limit_seconds=1):
        send_rate_limited_message(message.chat.id)
        return
    clear_cart(message.chat.id)
    bot.send_message(message.chat.id, "Корзина очищена.")
    merch_menu(message)
@bot.message_handler(func=lambda m: m.text == "✅ Оформить заказ")
def send_merch_order(message):
    # rate limit for sending order
    if not allowed_action(message.chat.id, "send_merch_order", limit_seconds=3):
        send_rate_limited_message(message.chat.id)
        return
    # Создаём pending заказ и отправляем владельцу для подтверждения
    username = f"@{message.from_user.username}" if message.from_user.username else str(message.chat.id)
    res = create_pending_from_cart(message.chat.id, username)
    if not res:
        bot.send_message(message.chat.id, "Корзина пуста.")
        return
    pending_id, items_list, total_sum = res
    # формируем текст для владельца
    order_lines = [f"- {it['item']} ×{it['quantity']} = {it['total']}₽" for it in items_list]
    order_text = f"Новый заказ (ожидает подтверждения) #{pending_id} от {username}:\n" + "\n".join(order_lines) + f"\nИтого: {total_sum}₽"
    # inline кнопки для подтверждения/отклонения
    ikb = types.InlineKeyboardMarkup()
    ikb.add(
        types.InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm_pending:{pending_id}"),
        types.InlineKeyboardButton("❌ Отклонить", callback_data=f"decline_pending:{pending_id}")
    )
    try:
        bot.send_message(OWNER_ID, order_text, reply_markup=ikb)
        bot.send_message(message.chat.id, "Заказ отправлен владельцу на подтверждение. Вы получите уведомление после решения.")
    except Exception as e:
        logger.error(f"Ошибка при отправке заказа владельцу: {e}")
        bot.send_message(message.chat.id, "Не удалось отправить заказ владельцу. Попробуйте позже.")
@bot.message_handler(func=lambda m: m.text == "🔙 Назад к Мерч")
def back_to_merch(message):
    if not allowed_action(message.chat.id, "back_to_merch"):
        send_rate_limited_message(message.chat.id)
        return
    merch_menu(message)
# --- Мои заказы (пользователь) ---
@bot.message_handler(func=lambda m: m.text == "📦 Мои заказы")
def my_orders(message):
    if not allowed_action(message.chat.id, "my_orders"):
        send_rate_limited_message(message.chat.id)
        return
    try:
        with engine.connect() as conn:
            result = conn.execute(sql_text(
                "SELECT id, item, quantity, price, total, date, status FROM merch_orders WHERE user_id = :user_id ORDER BY id DESC"
            ), {"user_id": message.chat.id})
            rows = result.fetchall()
        if not rows:
            bot.send_message(message.chat.id, "У вас нет заказов.")
            merch_menu(message)
            return
        text_lines = []
        for row in rows:
            oid, item, qty, price, total, date_str, status = row
            text_lines.append(f"#{oid} — {item} ×{qty} ({price}₽/шт) = {total}₽ | {status} | {date_str}")
        bot.send_message(message.chat.id, "Ваши заказы:\n" + "\n".join(text_lines))
        merch_menu(message)
    except Exception as e:
        logger.error(f"Ошибка получения заказов: {e}")
        bot.send_message(message.chat.id, "Произошла ошибка при получении ваших заказов. Попробуйте позже.")
# --- Админ-панель (inline) и команды владельца ---
@bot.message_handler(commands=['admin'])
def admin_command(message):
    if message.chat.id != OWNER_ID:
        return
    ikb = types.InlineKeyboardMarkup(row_width=1)
    ikb.add(
        types.InlineKeyboardButton("📊 Статистика", callback_data="admin_stats"),
        types.InlineKeyboardButton("🛍 Заказы", callback_data="admin_orders"),
        types.InlineKeyboardButton("📬 Рассылка", callback_data="admin_broadcast"),
        types.InlineKeyboardButton("📢 Подписчики", callback_data="admin_subscribers"),
        types.InlineKeyboardButton("🔙 В главное меню", callback_data="admin_back")
    )
    bot.send_message(OWNER_ID, "Админ-панель (inline):", reply_markup=ikb)
# --- ОСНОВНЫЕ ИЗМЕНЕНИЯ: Исправлены ошибки в админ-панели ---
# --- Обработчик callback'ов (inline кнопки) ---
@bot.callback_query_handler(func=lambda call: True)
def callback_query_handler(call: types.CallbackQuery):
    data = call.data
    user_id = call.from_user.id
    # Только владелец может использовать админ inline (кроме подтверждения pending/decline, тоже владельцу)
    if data == "admin_back" and user_id == OWNER_ID:
        bot.answer_callback_query(call.id)
        start(call.message)
        return
    # ИСПРАВЛЕНО: добавлена обработка None значений для статистики
    if data == "admin_stats" and user_id == OWNER_ID:
        bot.answer_callback_query(call.id)
        try:
            with engine.connect() as conn:
                today = str(date.today())
                result = conn.execute(sql_text(
                    "SELECT COUNT(DISTINCT user_id) FROM user_log WHERE date = :today"
                ), {"today": today})
                today_count = result.fetchone()[0] or 0
                result = conn.execute(sql_text(
                    "SELECT COUNT(DISTINCT user_id) FROM user_log"
                ))
                total_count = result.fetchone()[0] or 0
            bot.send_message(OWNER_ID, f"📊 Статистика\nСегодня: {today_count}\nЗа всё время: {total_count}")
        except Exception as e:
            logger.error(f"Ошибка получения статистики: {e}")
            bot.send_message(OWNER_ID, "Ошибка при получении статистики.")
        return
    # ИСПРАВЛЕНО: улучшена обработка подписчиков
    if data == "admin_subscribers" and user_id == OWNER_ID:
        bot.answer_callback_query(call.id)
        try:
            with engine.connect() as conn:
                result = conn.execute(sql_text(
                    "SELECT user_id, username FROM subscriptions"
                ))
                rows = result.fetchall()
            if not rows:
                bot.send_message(OWNER_ID, "Нет подписчиков.")
            else:
                lst = []
                for user_id, username in rows:
                    if username:
                        lst.append(username)
                    else:
                        lst.append(f"ID:{user_id}")
                subscribers_list = ", ".join(lst)
                # Добавляем информацию о количестве
                bot.send_message(OWNER_ID, f"Подписчиков всего: {len(rows)}\n{subscribers_list}")
        except Exception as e:
            logger.error(f"Ошибка получения подписчиков: {e}")
            bot.send_message(OWNER_ID, "Ошибка при получении списка подписчиков.")
        return
    # ИСПРАВЛЕНО: Добавлено подтверждение рассылки
    if data == "admin_broadcast" and user_id == OWNER_ID:
        bot.answer_callback_query(call.id)
        # Просим владельца отправить текст
        msg = bot.send_message(OWNER_ID, "Отправьте текст рассылки (будет отправлено всем подписчикам).")
        bot.register_next_step_handler(msg, prepare_broadcast)
        return
    # ИСПРАВЛЕНО: Обновлен запрос к заказам, учитывающий структуру таблицы
    if data == "admin_orders" and user_id == OWNER_ID:
        bot.answer_callback_query(call.id)
        try:
            with engine.connect() as conn:
                # ИСПРАВЛЕНО: Добавлено условие WHERE status != 'Доставлен', чтобы скрыть доставленные заказы
                result = conn.execute(sql_text(
                    "SELECT id, user_id, username, item, quantity, price, total, date, status FROM merch_orders WHERE status != 'Доставлен' ORDER BY id DESC LIMIT 50"
                ))
                rows = result.fetchall()
            if not rows:
                bot.send_message(OWNER_ID, "Заказов нет.")
                return
            # Для компактности покажем кнопки-переключатели на отдельные заказы
            ikb = types.InlineKeyboardMarkup(row_width=1)
            for row in rows:
                oid, uid, username, item, qty, price, total, date_str, status = row
                # Добавлено поле price в отображение
                label = f"#{oid} | {username or f'ID:{uid}'} | {item}×{qty} | {price}₽ | {total}₽ | {status}"
                ikb.add(types.InlineKeyboardButton(label, callback_data=f"open_order:{oid}"))
            ikb.add(types.InlineKeyboardButton("🔙 Назад", callback_data="admin_back"))
            bot.send_message(OWNER_ID, "Последние заказы (нажмите для управления):", reply_markup=ikb)
        except Exception as e:
            logger.error(f"Ошибка получения заказов: {e}")
            bot.send_message(OWNER_ID, "Ошибка при получении списка заказов.")
        return
    # Открыть конкретный заказ (показать детали + кнопки изменения статуса)
    if data and data.startswith("open_order:") and user_id == OWNER_ID:
        bot.answer_callback_query(call.id)
        try:
            oid = int(data.split(":", 1)[1])
        except:
            bot.send_message(OWNER_ID, "Неправильный id заказа.")
            return
        try:
            with engine.connect() as conn:
                # Исправленный запрос с учетом всех полей
                result = conn.execute(sql_text(
                    "SELECT id, user_id, username, item, quantity, price, total, date, status FROM merch_orders WHERE id = :oid"
                ), {"oid": oid})
                row = result.fetchone()
            if not row:
                bot.send_message(OWNER_ID, f"Заказ #{oid} не найден.")
                return
            _, uid, username, item, qty, price, total, date_str, status = row
            text = f"Заказ #{oid}\nПользователь: {username or f'ID:{uid}'} ({uid})\nТовар: {item}\nКол-во: {qty}\nЦена: {price}₽/шт\nСумма: {total}₽\nДата: {date_str}\nСтатус: {status}"
            # Кнопки для изменения статуса (исключая текущий)
            statuses = ["В обработке", "Отправлен", "Доставлен", "Отклонён"]
            ikb = types.InlineKeyboardMarkup(row_width=2)
            for st in statuses:
                if st != status:
                    ikb.add(types.InlineKeyboardButton(st, callback_data=f"change_status:{oid}:{st}"))
            ikb.add(types.InlineKeyboardButton("Удалить заказ", callback_data=f"delete_order:{oid}"))
            ikb.add(types.InlineKeyboardButton("🔙 Назад к списку", callback_data="admin_orders"))
            bot.send_message(OWNER_ID, text, reply_markup=ikb)
        except Exception as e:
            logger.error(f"Ошибка получения заказа: {e}")
            bot.send_message(OWNER_ID, f"Ошибка при получении заказа #{oid}.")
        return
    # Изменить статус заказа (админ)
    if data and data.startswith("change_status:") and user_id == OWNER_ID:
        bot.answer_callback_query(call.id)
        parts = data.split(":", 2)
        if len(parts) < 3:
            bot.send_message(OWNER_ID, "Неправильный формат.")
            return
        try:
            oid = int(parts[1])
            new_status = parts[2]
        except:
            bot.send_message(OWNER_ID, "Неправильный формат данных.")
            return
        try:
            with engine.connect() as conn:
                result = conn.execute(sql_text(
                    "SELECT user_id FROM merch_orders WHERE id = :oid"
                ), {"oid": oid})
                row = result.fetchone()
                if not row:
                    bot.send_message(OWNER_ID, f"Заказ #{oid} не найден.")
                    return
                user_for_notify = row[0]
                conn.execute(sql_text(
                    "UPDATE merch_orders SET status = :new_status WHERE id = :oid"
                ), {"new_status": new_status, "oid": oid})
                conn.commit()
            bot.send_message(OWNER_ID, f"Статус заказа #{oid} изменён на: {new_status}")
            try:
                bot.send_message(user_for_notify, f"Обновление статуса вашего заказа #{oid}: {new_status}")
            except Exception as e:
                logger.error(f"Не удалось уведомить пользователя {user_for_notify}: {e}")
        except Exception as e:
            logger.error(f"Ошибка изменения статуса заказа: {e}")
            bot.send_message(OWNER_ID, f"Ошибка при изменении статуса заказа #{oid}.")
        return
    # Удалить заказ (админ)
    if data and data.startswith("delete_order:") and user_id == OWNER_ID:
        bot.answer_callback_query(call.id)
        try:
            oid = int(data.split(":", 1)[1])
        except:
            bot.send_message(OWNER_ID, "Неправильный id.")
            return
        try:
            with engine.connect() as conn:
                result = conn.execute(sql_text(
                    "SELECT user_id FROM merch_orders WHERE id = :oid"
                ), {"oid": oid})
                row = result.fetchone()
                conn.execute(sql_text(
                    "DELETE FROM merch_orders WHERE id = :oid"
                ), {"oid": oid})
                conn.commit()
            bot.send_message(OWNER_ID, f"Заказ #{oid} удалён.")
            if row:
                try:
                    bot.send_message(row[0], f"Ваш заказ #{oid} удалён администратором.")
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"Ошибка удаления заказа: {e}")
            bot.send_message(OWNER_ID, f"Ошибка при удалении заказа #{oid}.")
        return
    # Обработка подтверждения/отклонения pending заказов (владелец)
    if data and data.startswith("confirm_pending:") and user_id == OWNER_ID:
        bot.answer_callback_query(call.id, "Подтверждаю заказ")
        try:
            pid = int(data.split(":", 1)[1])
        except:
            bot.send_message(OWNER_ID, "Неправильный id pending.")
            return
        try:
            # ИСПРАВЛЕНО: сначала получаем информацию о заказе, сохраняем ID пользователя, потом обрабатываем заказ
            pending = get_pending(pid)
            if not pending:
                bot.send_message(OWNER_ID, f"Ожидающий заказ #{pid} не найден.")
                return
            _, uid, username, items_json, total, date_str = pending
            
            # Переносим pending -> orders, очищаем корзину пользователя
            ok = move_pending_to_orders(pid)
            if ok:
                bot.send_message(OWNER_ID, f"Заказ #{pid} подтверждён и перенесён в заказы.")
                # Отправляем уведомление клиенту
                try:
                    bot.send_message(uid, f"Ваш заказ #{pid} подтвержден. Мы скоро свяжемся с вами! Все детали в личном кабинете.")
                except Exception as e:
                    logger.error(f"Не удалось уведомить пользователя {uid}: {e}")
            else:
                bot.send_message(OWNER_ID, "Ошибка при подтверждении заказа.")
        except Exception as e:
            logger.error(f"Ошибка подтверждения pending: {e}")
            bot.send_message(OWNER_ID, "Ошибка при подтверждении заказа.")
        return
    if data and data.startswith("decline_pending:") and user_id == OWNER_ID:
        bot.answer_callback_query(call.id, "Отклоняю заказ")
        try:
            pid = int(data.split(":", 1)[1])
        except:
            bot.send_message(OWNER_ID, "Неправильный id pending.")
            return
        try:
            # ИСПРАВЛЕНО: сначала получаем информацию о заказе, сохраняем ID пользователя, потом обрабатываем заказ
            pending = get_pending(pid)
            if not pending:
                bot.send_message(OWNER_ID, f"Ожидающий заказ #{pid} не найден.")
                return
            _, uid, username, items_json, total, date_str = pending
            
            # Удаляем pending и очищаем корзину пользователя
            delete_pending(pid)
            clear_cart(uid)
            bot.send_message(OWNER_ID, f"Заказ #{pid} отклонён и удалён.")
            # Отправляем уведомление клиенту
            try:
                bot.send_message(uid, f"Ваш заказ #{pid} отменен. Мы скоро свяжемся с вами! Все детали в личном кабинете.")
            except Exception as e:
                logger.error(f"Не удалось уведомить пользователя {uid}: {e}")
        except Exception as e:
            logger.error(f"Ошибка отклонения pending: {e}")
            bot.send_message(OWNER_ID, "Ошибка при отклонении заказа.")
        return
    # fallback: неопознанный callback — просто ack
    try:
        bot.answer_callback_query(call.id)
    except:
        pass
# --- ИСПРАВЛЕНО: Добавлено подтверждение для рассылки ---
def prepare_broadcast(message):
    """Подготовка рассылки - запрос подтверждения"""
    if message.text is None:
        bot.send_message(OWNER_ID, "Ошибка: сообщение не содержит текста.")
        return
    broadcast_text = message.text
    # Создаем клавиатуру подтверждения
    ikb = types.InlineKeyboardMarkup()
    ikb.add(
        types.InlineKeyboardButton("✅ Отправить", callback_data=f"confirm_broadcast:{broadcast_text}"),
        types.InlineKeyboardButton("❌ Отмена", callback_data="cancel_broadcast")
    )
    # Отправляем сообщение с подтверждением
    bot.send_message(
        OWNER_ID,
        f"Вы собираетесь отправить следующее сообщение всем подписчикам:\n{broadcast_text}\nОтправить рассылку?",
        reply_markup=ikb
    )
def confirm_broadcast(broadcast_text):
    """Фактическая отправка рассылки"""
    try:
        with engine.connect() as conn:
            result = conn.execute(sql_text(
                "SELECT user_id FROM subscriptions"
            ))
            rows = result.fetchall()
        if not rows:
            bot.send_message(OWNER_ID, "Нет подписчиков для рассылки.")
            return
        sent = 0
        failed = 0
        for (user_id,) in rows:
            try:
                bot.send_message(user_id, broadcast_text)
                sent += 1
            except Exception as e:
                logger.error(f"Ошибка при отправке рассылки {user_id}: {e}")
                failed += 1
        bot.send_message(OWNER_ID, f"Рассылка завершена.\nУспешно: {sent}\nОшибок: {failed}")
    except Exception as e:
        logger.error(f"Ошибка рассылки: {e}")
        bot.send_message(OWNER_ID, "Ошибка при выполнении рассылки.")
# Обработчик для подтверждения рассылки
@bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_broadcast:"))
def handle_confirm_broadcast(call):
    if call.from_user.id != OWNER_ID:
        bot.answer_callback_query(call.id, "Вы не являетесь владельцем бота!")
        return
    # Извлекаем текст рассылки из callback_data
    broadcast_text = call.data.split(":", 1)[1]
    # Отправляем сообщение о начале рассылки
    bot.answer_callback_query(call.id, "Начинаем рассылку...")
    # Удаляем сообщение с подтверждением
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except:
        pass
    # Отправляем сообщение о процессе
    bot.send_message(OWNER_ID, "📤 Рассылка началась...")
    # Запускаем рассылку
    confirm_broadcast(broadcast_text)
# Обработчик для отмены рассылки
@bot.callback_query_handler(func=lambda call: call.data == "cancel_broadcast")
def handle_cancel_broadcast(call):
    if call.from_user.id != OWNER_ID:
        bot.answer_callback_query(call.id, "Вы не являетесь владельцем бота!")
        return
    bot.answer_callback_query(call.id, "Рассылка отменена")
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except:
        pass
    bot.send_message(OWNER_ID, "Рассылка отменена.")
# --- Остальной webhook и запуск Flask ---
@app.route("/")
def index():
    return "Bot is running!"
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = types.Update.de_json(request.get_json(force=True))
    bot.process_new_updates([update])
    return "", 200
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
