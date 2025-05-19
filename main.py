import os
import re
import sqlite3
import logging
import threading
import time
from flask import Flask, request
import telebot
from telebot import types
import requests

# --- Настройка логирования ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Константы ---
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OWNER_ID = os.getenv("OWNER_TELEGRAM_ID")
RENDER_URL = os.getenv("RENDER_URL", "https://barskiehoromi.onrender.com")

# --- Инициализация БД ---
def init_db():
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cart (
            user_id INTEGER,
            dish TEXT,
            meal_type TEXT,
            price INTEGER
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bike_rentals (
            user_id INTEGER,
            bike_type TEXT,
            rent_time DATETIME
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# --- Меню ---
FOOD_MENU = {
    "breakfast": {
        "Яичница (150г)": 500,
        "Кофе": 200,
        "Блины (180г)": 450,
        "Творожная запеканка (200г)": 450,
        "Сырники (180г)": 400
    },
    "dinner": {
        "Суп (300г)": 350,
        "Рыба (250г)": 600,
        "Чай": 150,
        "Гречка с грибами (250г)": 350,
        "Курица-гриль (300г)": 600
    }
}

BIKE_MENU = {
    "Велосипед 1": {"price_hour": 500, "price_day": 1000, "photo": "bike1.jpg"},
    "Велосипед 2": {"price_hour": 600, "price_day": 1200, "photo": "bike2.jpg"}
}

# --- Инициализация бота и Flask ---
app = Flask(__name__)
bot = telebot.TeleBot(TOKEN)
WEBHOOK_URL = f"{RENDER_URL}/{TOKEN}"
bot.remove_webhook()
bot.set_webhook(url=WEBHOOK_URL)

# ================= ОБРАБОТЧИКИ КНОПОК =================
@bot.message_handler(commands=["start"])
def start(message):
    main_keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    main_keyboard.add(
        types.KeyboardButton("🏠 О доме"),
        types.KeyboardButton("🌆 Город"),
        types.KeyboardButton("🛍️ Сувениры"),
        types.KeyboardButton("Обратная связь")
    )
    bot.send_message(
        message.chat.id,
        "👋 Добро пожаловать в наш дом! 🏡\nВыберите раздел:",
        reply_markup=main_keyboard
    )

@bot.message_handler(func=lambda m: m.text == "🏠 О доме")
def handle_home(message):
    with open("photos/main_photo.jpg", "rb") as photo:
        bot.send_photo(
            message.chat.id,
            photo,
            caption="🏡 Уютный дом с видом на лес. Все удобства включены."
        )
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(
        types.KeyboardButton("🍽 Еда"),
        types.KeyboardButton("🚲 Прокат велосипедов"),
        types.KeyboardButton("🔙 Назад")
    )
    bot.send_message(message.chat.id, "Выберите действие:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "🌆 Город")
def handle_city(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(
        types.KeyboardButton("🏛️ Музей Карельского фронта"),
        types.KeyboardButton("🚖 Такси"),
        types.KeyboardButton("🏥 Больница"),
        types.KeyboardButton("🔙 Назад")
    )
    bot.send_message(
        message.chat.id,
        "🌆 Г. Беломорск, Республика Карелия:\nНаселение: ~12 000 чел.",
        reply_markup=markup
    )

@bot.message_handler(func=lambda m: m.text == "🛍️ Сувениры")
def handle_souvenirs(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(
        types.KeyboardButton("🧲 Магнит на холодильник"),
        types.KeyboardButton("🔙 Назад")
    )
    bot.send_message(message.chat.id, "🛍️ Сувениры:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "Обратная связь")
def handle_feedback(message):
    msg = bot.send_message(message.chat.id, "💬 Напишите ваш отзыв:")
    bot.register_next_step_handler(msg, send_feedback)

def send_feedback(message):
    bot.send_message(OWNER_ID, f"📬 Отзыв от @{message.from_user.username}:\n{message.text}")
    bot.send_message(message.chat.id, "✅ Сообщение отправлено!", reply_markup=types.ReplyKeyboardRemove())

# --- Прокат велосипедов ---
@bot.message_handler(func=lambda m: m.text == "🚲 Прокат велосипедов")
def bike_rental(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(
        types.KeyboardButton("Велосипед 1"),
        types.KeyboardButton("Велосипед 2"),
        types.KeyboardButton("🔙 Назад")
    )
    bot.send_message(message.chat.id, "Выберите велосипед:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text in ["Велосипед 1", "Велосипед 2"])
def show_bike_details(message):
    try:
        bike = BIKE_MENU[message.text]
        with open(f"photos/{bike['photo']}", "rb") as photo:
            bot.send_photo(
                message.chat.id,
                photo,
                caption=f"🚲 {message.text}\nЦены:\n- 1 час: {bike['price_hour']}₽\n- Целый день: {bike['price_day']}₽"
            )
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(
            types.KeyboardButton("✅ Хочу кататься!"),
            types.KeyboardButton("🔙 Назад")
        )
        bot.send_message(message.chat.id, "Забронировать?", reply_markup=markup)
    except Exception as e:
        logger.error(f"Ошибка при загрузке велосипеда: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка загрузки данных.")

@bot.message_handler(func=lambda m: m.text == "✅ Хочу кататься!")
def confirm_bike_rental(message):
    bot.send_message(OWNER_ID, f"🚴 Новый прокат от @{message.from_user.username}!")
    bot.send_message(message.chat.id, "✅ Велосипед забронирован. Хозяин свяжется с вами.", reply_markup=types.ReplyKeyboardRemove())
    start(message)

# --- Еда и корзина ---
@bot.message_handler(func=lambda m: m.text == "🍽 Еда")
def handle_food(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(
        types.KeyboardButton("🍳 Завтрак"),
        types.KeyboardButton("🍽 Ужин"),
        types.KeyboardButton("🛒 Корзина"),
        types.KeyboardButton("🔙 Назад")
    )
    bot.send_message(message.chat.id, "Выберите категорию:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text in ["🍳 Завтрак", "🍽 Ужин"])
def show_food_menu(message):
    meal_type = "breakfast" if message.text == "🍳 Завтрак" else "dinner"
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for dish in FOOD_MENU[meal_type]:
        markup.add(types.KeyboardButton(dish))
    markup.add(types.KeyboardButton("🔙 Назад"))
    bot.send_message(message.chat.id, "Выберите блюдо:", reply_markup=markup)

@bot.message_handler(func=lambda m: any(m.text in FOOD_MENU["breakfast"] or m.text in FOOD_MENU["dinner"]))
def add_to_cart(message):
    meal_type = "breakfast" if message.text in FOOD_MENU["breakfast"] else "dinner"
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO cart (user_id, dish, meal_type, price) VALUES (?, ?, ?, ?)",
        (message.chat.id, message.text, meal_type, FOOD_MENU[meal_type][message.text])
    )
    conn.commit()
    conn.close()
    bot.send_message(message.chat.id, f"✅ {message.text} ({meal_type.capitalize()}) добавлено в корзину!")

@bot.message_handler(func=lambda m: m.text == "🛒 Корзина")
def show_cart(message):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute("SELECT dish, meal_type, price FROM cart WHERE user_id=?", (message.chat.id,))
    items = cursor.fetchall()
    conn.close()

    if not items:
        bot.send_message(message.chat.id, "Корзина пуста.")
        return

    total = sum(item[2] for item in items)
    cart_text = "🛒 Ваш заказ:\n" + "\n".join([f"- {dish} ({meal_type}): {price}₽" for dish, meal_type, price in items]) + f"\nИтого: {total}₽"
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(
        types.KeyboardButton("✅ Подтвердить заказ"),
        types.KeyboardButton("🔙 Назад")
    )
    bot.send_message(message.chat.id, cart_text, reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "✅ Подтвердить заказ")
def confirm_cart(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(
        types.KeyboardButton("🍳 Завтрак"),
        types.KeyboardButton("🍽 Ужин"),
        types.KeyboardButton("⏰ Другое время")
    )
    bot.send_message(message.chat.id, "Выберите время доставки:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text in ["🍳 Завтрак", "🍽 Ужин", "⏰ Другое время"])
def handle_delivery_time(message):
    if message.text == "⏰ Другое время":
        bot.send_message(message.chat.id, "Укажите время в формате ЧЧ:ММ:")
        bot.register_next_step_handler(message, save_custom_time)
    else:
        save_order(message)

def save_custom_time(message):
    if not re.match(r"^\d{2}:\d{2}$", message.text):
        bot.send_message(message.chat.id, "❌ Некорректный формат времени!")
        return
    save_order(message, custom_time=message.text)

def save_order(message, custom_time=None):
    user_id = message.chat.id
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute("SELECT dish, meal_type FROM cart WHERE user_id=?", (user_id,))
    items = cursor.fetchall()
    
    order_text = f"Новый заказ от @{message.from_user.username}:\n"
    for dish, meal_type in items:
        order_text += f"- {dish} ({meal_type.capitalize()})\n"
    
    if custom_time:
        order_text += f"⏰ Время: {custom_time}"
    else:
        order_text += f"⏰ Время: {message.text}"

    bot.send_message(OWNER_ID, order_text)
    cursor.execute("DELETE FROM cart WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()
    bot.send_message(user_id, "✅ Заказ отправлен!", reply_markup=types.ReplyKeyboardRemove())

@bot.message_handler(func=lambda m: m.text == "🔙 Назад")
def go_back(message):
    start(message)

# --- Автопинг ---
def self_ping():
    while True:
        try:
            requests.get(f"{RENDER_URL}/ping")
            logger.info("Автопинг выполнен")
        except Exception as e:
            logger.error(f"Ошибка автопинга: {e}")
        time.sleep(300)

threading.Thread(target=self_ping, daemon=True).start()

# --- Flask-роуты ---
@app.route("/")
def index():
    return "Bot is running!", 200

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    if request.method == "POST":
        update = types.Update.de_json(request.get_json(force=True))
        bot.process_new_updates([update])
    return "", 200

@app.route("/ping")
def ping():
    return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
