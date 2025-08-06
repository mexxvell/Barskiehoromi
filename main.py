import os
import logging
import sqlite3
import threading
import time
import requests
from datetime import datetime
from flask import Flask, request
import telebot
from telebot import types
from apscheduler.schedulers.background import BackgroundScheduler

# --- Логирование ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Константы ---
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_TELEGRAM_ID", "0"))
if not TOKEN or not OWNER_ID:
    raise RuntimeError("Установите TELEGRAM_BOT_TOKEN и OWNER_TELEGRAM_ID")

RENDER_URL = os.getenv("RENDER_URL", "https://your-app.onrender.com")
WEBHOOK_URL = f"{RENDER_URL}/{TOKEN}"

# --- Инициализация ---
app = Flask(__name__)
bot = telebot.TeleBot(TOKEN)

bot.remove_webhook()
bot.set_webhook(url=WEBHOOK_URL)

# --- БД ---
def init_db():
    conn = sqlite3.connect('bot.db')
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS merch_cart (
        id INTEGER PRIMARY KEY,
        user_id INTEGER,
        item TEXT,
        quantity INTEGER
    )''')
    cur.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        first_seen TEXT
    )''')
    conn.commit()
    conn.close()

init_db()

# --- Товары ---
MERCH_ITEMS = {
    "👛 Шопер": (500, "shopper.jpg"),
    "☕ Кружка": (300, "mug.jpg"),
    "👕 Футболка": (800, "tshirt.jpg"),
}

# --- Пользовательские состояния ---
user_states = {}

# --- Стартовое меню ---
def main_menu(chat_id, send_text=True):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    keyboard.add(
        types.KeyboardButton("👥 Команда"),
        types.KeyboardButton("🌍 Путешествия"),
        types.KeyboardButton("🧘 Кундалини‑йога"),
        types.KeyboardButton("📸 Медиа"),
        types.KeyboardButton("🛍 Мерч"),
        types.KeyboardButton("🎁 Доп. услуги")
    )
    if send_text:
        text = ("👋 Добро пожаловать!\n"
                "👥 Команда — познакомьтесь с нами\n"
                "🌍 Путешествия — авторские туры и ретриты\n"
                "🧘 Кундалини‑йога — практика и трансформация\n"
                "📸 Медиа — вдохновляющие фото и видео\n"
                "🛍 Мерч — одежда и аксессуары ScanDream\n"
                "🎁 Доп. услуги — всё для вашего комфорта")
        bot.send_message(chat_id, text, reply_markup=keyboard)
    return keyboard

@bot.message_handler(commands=["start"])
def handler_start(m):
    track_user(m.chat.id)
    main_menu(m.chat.id)

# --- Подсчет уникальных пользователей ---
def track_user(user_id):
    conn = sqlite3.connect('bot.db')
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO users (user_id, first_seen) VALUES (?, ?)",
                (user_id, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

# --- Меню «Команда» ---
@bot.message_handler(func=lambda m: m.text == "👥 Команда")
def handler_team(m):
    track_user(m.chat.id)
    text = ("Нас зовут Алексей Бабенко — учитель кундалини‑йоги, визионер, путешественник, кинематографист, медиа‑продюсер.\n"
            "Более 20 лет личной практики, 18 лет преподавания. Преподаватель тренинга школы Амрит Нам Саровар (Франция) в России.\n"
            "Создатель йога‑кемпа и ретритов по Карелии, Северной Осетии, Грузии, Армении и Турции.\n\n"
            "И Анастасия Голик — сертифицированный инструктор хатха‑йоги, аромапрактик, вдохновитель и заботливая спутница ретритов.")
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton("ℹ️ О бренде"), types.KeyboardButton("🔗 Источники"))
    kb.add(types.KeyboardButton("🔙 Назад"))
    bot.send_message(m.chat.id, text, reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "ℹ️ О бренде")
def handler_brand(m):
    track_user(m.chat.id)
    text = ("ScanDream — @scandream — зарегистрированный товарный знак. "
            "Место осознанных творческих коммуникаций, где мы пересобираем конструкт Мира.\n"
            "Быть #scandream — значит сканировать своё жизненное предназначение мечтой и действием.\n"
            "Проект «Йога‑кемп» — это интеграция пользы (новые знания) и умений (новые формы).")
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton("🔙 Назад"))
    bot.send_message(m.chat.id, text, reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "🔗 Источники")
def handler_sources(m):
    track_user(m.chat.id)
    text = ("Официальные источники:\n"
            "1. Алексей ВК — https://vk.ru/scandream\n"
            "2. Анастасия ВК — https://vk.ru/yoga.golik\n"
            "3. Канал ScanDream•Live — https://t.me/scandream\n"
            "4. ТГ Алексея — https://t.me/scandreamlife\n"
            "5. ТГ Анастасии — https://t.me/yogagolik_dnevnik\n"
            "6. Йога с Алексеем (ВК) — https://vk.ru/kyogababenko")
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton("🔙 Назад"))
    bot.send_message(m.chat.id, text, reply_markup=kb)

# --- Другие разделы (каркас) ---
@bot.message_handler(func=lambda m: m.text in ["🌍 Путешествия", "🧘 Кундалини‑йога",
                                              "📸 Медиа", "🎁 Доп. услуги"])
def handler_other(m):
    track_user(m.chat.id)
    main_menu(m.chat.id)

# --- Мерч ---
@bot.message_handler(func=lambda m: m.text == "🛍 Мерч")
def handler_merch(m):
    track_user(m.chat.id)
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for key in MERCH_ITEMS:
        keyboard.add(types.KeyboardButton(key))
    keyboard.add(types.KeyboardButton("🛍️ Корзина"), types.KeyboardButton("🔙 Назад"))
    bot.send_message(m.chat.id, "🛍 Мерч: выберите товар для просмотра", reply_markup=keyboard)

@bot.message_handler(func=lambda m: m.text in MERCH_ITEMS)
def show_item(m):
    track_user(m.chat.id)
    name = m.text
    price, fname = MERCH_ITEMS[name]
    caption = f"{name[2:]} — {price}₽"
    try:
        with open(f"photos/{fname}", "rb") as ph:
            bot.send_photo(m.chat.id, ph, caption=caption)
    except:
        bot.send_message(m.chat.id, caption)
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton("✅ Заказать"), types.KeyboardButton("🔙 Назад"))
    msg = bot.send_message(m.chat.id, "Выберите:", reply_markup=kb)
    user_states[m.chat.id] = {"item": name}

@bot.message_handler(func=lambda m: m.chat.id in user_states and m.text == "✅ Заказать")
def ask_qty(m):
    bot.send_message(m.chat.id, "Сколько штук добавить?")
    user_states[m.chat.id]["stage"] = "ask_qty"

@bot.message_handler(func=lambda m: m.chat.id in user_states and user_states[m.chat.id].get("stage") == "ask_qty")
def save_qty(m):
    try:
        qty = int(m.text)
        if qty < 1: raise ValueError
    except:
        bot.send_message(m.chat.id, "Введите корректное число (>0)")
        return
    info = user_states.pop(m.chat.id)
    item = info["item"][2:]  # без эмодзи
    conn = sqlite3.connect('bot.db')
    cur = conn.cursor()
    cur.execute("INSERT INTO merch_cart (user_id, item, quantity) VALUES (?, ?, ?)",
                (m.chat.id, item, qty))
    conn.commit()
    conn.close()
    bot.send_message(m.chat.id, f"Добавлено: {item} ×{qty} ✅")
    handler_merch(m)

@bot.message_handler(func=lambda m: m.text == "🛍️ Корзина")
def show_cart(m):
    track_user(m.chat.id)
    conn = sqlite3.connect('bot.db')
    cur = conn.cursor()
    cur.execute("SELECT item, quantity FROM merch_cart WHERE user_id=?", (m.chat.id,))
    data = cur.fetchall()
    conn.close()
    if not data:
        bot.send_message(m.chat.id, "Корзина пуста.", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add(types.KeyboardButton("🔙 Назад")))
        return
    text = "🛍 Ваша корзина:\n" + "\n".join([f"- {i}: {q}" for i, q in data])
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton("📨 Оформить заказ"), types.KeyboardButton("🔙 Назад"))
    bot.send_message(m.chat.id, text, reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "📨 Оформить заказ")
def finalize_order(m):
    conn = sqlite3.connect('bot.db')
    cur = conn.cursor()
    cur.execute("SELECT item, quantity FROM merch_cart WHERE user_id=?", (m.chat.id,))
    data = cur.fetchall()
    cur.execute("DELETE FROM merch_cart WHERE user_id=?", (m.chat.id,))
    conn.commit()
    conn.close()
    order = (f"📦 Новый заказ от @{m.from_user.username or m.chat.id}:\n" +
             "\n".join([f"- {i} ×{q}" for i, q in data]))
    bot.send_message(OWNER_ID, order)
    bot.send_message(m.chat.id, "Спасибо, ваш заказ отправлен! 🎉", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add(types.KeyboardButton("🔙 Назад")))

# --- Автопинг и ежедневная статистика ---
def send_stats():
    conn = sqlite3.connect('bot.db')
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    count = cur.fetchone()[0]
    conn.close()
    today = datetime.utcnow().date().isoformat()
    bot.send_message(OWNER_ID, f"📊 Статистика на {today}: уникальных пользователей — {count}")

def self_ping():
    while True:
        try:
            requests.get(f"{RENDER_URL}/ping", timeout=5)
        except Exception as e:
            logger.error("Ping error: %s", e)
        time.sleep(300)

scheduler = BackgroundScheduler()
scheduler.add_job(send_stats, 'cron', hour=9, minute=0)  # каждый день в 09:00 UTC
scheduler.start()

threading.Thread(target=self_ping, daemon=True).start()

# --- Flask webhook ---
@app.route("/", methods=["GET"])
def index():
    return "OK", 200

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = types.Update.de_json(request.get_json(force=True))
    bot.process_new_updates([update])
    return "", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
