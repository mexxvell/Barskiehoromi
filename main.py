import os
import logging
import sqlite3
import threading
import time
import requests
from flask import Flask, request
import telebot
from telebot import types
from datetime import datetime, date

# --- Настройка логирования ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Константы ---
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    logger.error("Переменная TELEGRAM_BOT_TOKEN не установлена")
    raise RuntimeError("TOKEN is required")
OWNER_ID = int(os.getenv("OWNER_TELEGRAM_ID", "0")) or None
if not OWNER_ID:
    logger.error("Переменная OWNER_TELEGRAM_ID не установлена или некорректна")
    raise RuntimeError("OWNER_TELEGRAM_ID is required")
RENDER_URL = os.getenv("RENDER_URL", "https://your-app.onrender.com")
WEBHOOK_URL = f"{RENDER_URL}/{TOKEN}"

# --- Инициализация БД ---
def init_db():
    conn = sqlite3.connect('bot_data.db')
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS merch_cart (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            item TEXT,
            quantity INTEGER
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS user_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            date TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# --- Инициализация бота и Flask ---
app = Flask(__name__)
bot = telebot.TeleBot(TOKEN)
bot.remove_webhook()
bot.set_webhook(url=WEBHOOK_URL)

# --- Словарь товаров мерча (название: (цена, файл фото)) ---
MERCH_ITEMS = {
    "🛒 Шоперы":   (500, "shopper.jpg"),
    "☕ Кружки":    (300, "mug.jpg"),
    "👕 Футболки":  (800, "tshirt.jpg")
}

# --- Уникальные пользователи лог ---
def log_user(user_id):
    today = str(date.today())
    conn = sqlite3.connect("bot_data.db")
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM user_log WHERE user_id=? AND date=?", (user_id, today))
    if not cur.fetchone():
        cur.execute("INSERT INTO user_log (user_id, date) VALUES (?, ?)", (user_id, today))
        conn.commit()
    conn.close()

# --- Рассылка статистики владельцу ---
def send_daily_stats():
    while True:
        now = datetime.now()
        if now.hour == 23 and now.minute == 59:
            today = str(date.today())
            conn = sqlite3.connect("bot_data.db")
            cur = conn.cursor()
            cur.execute("SELECT COUNT(DISTINCT user_id) FROM user_log WHERE date=?", (today,))
            count = cur.fetchone()[0]
            conn.close()
            bot.send_message(OWNER_ID, f"📊 Уникальных пользователей за {today}: {count}")
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

# --- Главное меню ---
@bot.message_handler(commands=["start"])
def start(message):
    log_user(message.chat.id)
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(
        types.KeyboardButton("👥 Команда"),
        types.KeyboardButton("🌍 Путешествия"),
        types.KeyboardButton("🧘 Кундалини-йога"),
        types.KeyboardButton("📸 Медиа"),
        types.KeyboardButton("🛍 Мерч"),
        types.KeyboardButton("🎁 Доп. услуги")
    )
    bot.send_message(message.chat.id, "👋 Добро пожаловать!\n"
                "👥 Команда — познакомьтесь с нами\n"
                "🌍 Путешествия — авторские туры и ретриты\n"
                "🧘 Кундалини‑йога — практика и трансформация\n"
                "📸 Медиа — вдохновляющие фото и видео\n"
                "🛍 Мерч — одежда и аксессуары ScanDream\n"
                "🎁 Доп. услуги — всё для вашего комфорта", reply_markup=kb)

# --- Разделы ---
@bot.message_handler(func=lambda m: m.text == "1️⃣ Путешествия")
def travels_menu(message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("📂 Архив путешествий", "🌍 Где мы сейчас", "🔙 Назад к меню")
    bot.send_message(message.chat.id, "✈️ Путешествия: архив и текущее местоположение.", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "2️⃣ Кундалини-йога")
def yoga_menu(message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🏢 Офлайн-мероприятия", "💻 Онлайн-йога", "📅 Ближайшие мероприятия", "🔙 Назад к меню")
    bot.send_message(message.chat.id, "🧘 Кундалини-йога: офлайн, онлайн и ближайшие события.", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "3️⃣ Медиа")
def media_menu(message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("▶️ YouTube", "🔙 Назад к меню")
    bot.send_message(message.chat.id, "🎥 Медиа: наши видео на YouTube.", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "5️⃣ Доп. услуги")
def services_menu(message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🔙 Назад к меню")
    bot.send_message(message.chat.id, "🔧 Дополнительные услуги: детали по запросу.", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "👥 Команда")
def team_menu(message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🏷 О бренде", "🌐 Официальные источники", "🔙 Назад к меню")
    bot.send_message(message.chat.id, " Нас зовут Алексей Бабенко - учитель кундалини-йоги, визионер, путешественник, кинематографист, медиа продюсер. Более 20 лет личной практики кундалини-йоги, 18 лет ведения занятий. Преподаватель учительского тренинга школы Амрит Нам Саровар (Франция) в России. Создатель проекта авторских путешествий Йога-кемп, организатор йога-туров, ретритов и путешествий по Карелии, Северной Осетии, Грузии, Армении и Турции.
И Анастасия Голик - сертифицированный инструктор хатха-йоги, аромапрактик, идейный вдохновитель, а также кормилеца групп на выездах и ретритах кемпа.", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "🏷 О бренде")
def about_brand(message):
    bot.send_message(message.chat.id, "ScanDream - https://t.me/scandream - зарегистрированный товарный знак, основная идея которого осознанные творческие коммуникации. ScanDream - это место, где мы пересобираем конструкт Мира, рассматривая и восхищаясь его строением. Быть #scandream - это сканировать свое жизненное предназначение действием и мечтой. В реальности оставаться активным, осознанным и логичным, а мечтать широко, мощно, свободно и не ощущая предела. 

Проект йога-кемп - это творческая интеграция опыта и пользы. Пользы через новые знания и умения. Умения через новые формы.")

@bot.message_handler(func=lambda m: m.text == "🌐 Официальные источники")
def official_sources(message):
    bot.send_message(message.chat.id, "ОФИЦИАЛЬНЫЕ ИСТОЧНИКИ взаимодействия с командой ScanDream:

1. Личная страница в ВК Алексея - https://vk.ru/scandream
2. Моя личная страница в ВК - https://vk.ru/yoga.golik
2. Официальный ТГ канал ScanDream•Live - https://t.me/scandream
3. Личный  ТГ канал Алексея - https://t.me/scandreamlife
4. Личный мой ТГ канал -  https://t.me/yogagolik_dnevnik
5. Йога с Алексеем Бабенко  в ВК (Петрозаводск) - https://vk.ru/kyogababenko")

# Назад
@bot.message_handler(func=lambda m: m.text == "🔙 Назад к меню")
def back_to_menu(message):
    start(message)

# --- Мерч ---
@bot.message_handler(func=lambda m: m.text == "4️⃣ Мерч")
def merch_menu(message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for name in MERCH_ITEMS:
        kb.add(types.KeyboardButton(name))
    kb.add("🛍️ Корзина", "🔙 Назад к меню")
    bot.send_message(message.chat.id, "🛍️ Выберите товар:", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text in MERCH_ITEMS)
def show_merch_item(message):
    name = message.text
    price, photo_file = MERCH_ITEMS[name]
    try:
        with open(f"photos/{photo_file}", "rb") as photo:
            bot.send_photo(message.chat.id, photo, caption=f"{name[2:]} — {price}₽")
    except:
        bot.send_message(message.chat.id, f"{name[2:]} — {price}₽")
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("✅ Заказать", "🔙 Назад к Мерч")
    msg = bot.send_message(message.chat.id, "Выберите действие:", reply_markup=kb)
    bot.register_next_step_handler(msg, lambda m: merch_order_choice(m, name))

def merch_order_choice(message, item_name):
    if message.text == "✅ Заказать":
        msg = bot.send_message(message.chat.id, "Сколько штук добавить?")
        bot.register_next_step_handler(msg, lambda m: add_merch_quantity(m, item_name))
    else:
        merch_menu(message)

def add_merch_quantity(message, item_name):
    try:
        qty = int(message.text)
        if qty < 1:
            raise ValueError
    except:
        msg = bot.send_message(message.chat.id, "Введите корректное число (>0):")
        bot.register_next_step_handler(msg, lambda m: add_merch_quantity(m, item_name))
        return
    conn = sqlite3.connect('bot_data.db')
    cur = conn.cursor()
    cur.execute("INSERT INTO merch_cart (user_id, item, quantity) VALUES (?, ?, ?)", (message.chat.id, item_name[2:], qty))
    conn.commit()
    conn.close()
    bot.send_message(message.chat.id, f"✔️ Добавлено: {item_name[2:]} ×{qty}")
    merch_menu(message)

@bot.message_handler(func=lambda m: m.text == "🛍️ Корзина")
def show_merch_cart(message):
    conn = sqlite3.connect('bot_data.db')
    cur = conn.cursor()
    cur.execute("SELECT item, quantity FROM merch_cart WHERE user_id=?", (message.chat.id,))
    rows = cur.fetchall()
    conn.close()
    if not rows:
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add("🔙 Назад к Мерч")
        bot.send_message(message.chat.id, "Корзина пуста.", reply_markup=kb)
        return
    text = "\n".join([f"- {item}: {qty}" for item, qty in rows])
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("✅ Оформить заказ", "🔙 Назад к Мерч")
    bot.send_message(message.chat.id, f"🛒 Корзина:\n{text}", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "✅ Оформить заказ")
def send_merch_order(message):
    conn = sqlite3.connect('bot_data.db')
    cur = conn.cursor()
    cur.execute("SELECT item, quantity FROM merch_cart WHERE user_id=?", (message.chat.id,))
    rows = cur.fetchall()
    cur.execute("DELETE FROM merch_cart WHERE user_id=?", (message.chat.id,))
    conn.commit()
    conn.close()
    order = f"Новый заказ от @{message.from_user.username or message.chat.id}:\n"
    order += "\n".join([f"- {item} ×{qty}" for item, qty in rows])
    bot.send_message(OWNER_ID, order)
    bot.send_message(message.chat.id, "Спасибо, заказ отправлен! 🎉")

@bot.message_handler(func=lambda m: m.text == "🔙 Назад к Мерч")
def back_to_merch(message):
    merch_menu(message)

# --- Flask ---
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


