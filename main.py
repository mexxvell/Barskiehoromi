import os
import logging
import threading
import requests
from flask import Flask, request
import telebot
from telebot import types

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Константы
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OWNER_ID = os.getenv("OWNER_TELEGRAM_ID")
RENDER_URL = os.getenv("RENDER_URL", "https://barskiehoromi.onrender.com")

# Меню и временные слоты
FOOD_MENU = {
    "breakfast": ["Овсяная каша", "Яичница", "Блины"],
    "dinner": ["Суп", "Рыба", "Плов"]
}

TIME_SLOTS = {
    "breakfast": ["08:00", "09:00", "10:00"],
    "dinner": ["18:00", "19:00", "20:00"]
}

# Проверка переменных окружения
if not all([TOKEN, OWNER_ID, RENDER_URL]):
    raise EnvironmentError("Не заданы обязательные переменные окружения!")

app = Flask(__name__)
bot = telebot.TeleBot(TOKEN)

# Установка вебхука
WEBHOOK_URL = f"{RENDER_URL}/{TOKEN}"
bot.remove_webhook()
bot.set_webhook(url=WEBHOOK_URL)

# ================= ОБРАБОТЧИКИ КОМАНД =================
@bot.message_handler(commands=["start"])
def start(message):
    main_keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    main_keyboard.add(
        types.KeyboardButton("🏠 О доме"),
        types.KeyboardButton("🌆 Город"),
        types.KeyboardButton("🛍️ Сувениры"),
        types.KeyboardButton("Обратная связь"),
        types.KeyboardButton("🛎 Помощь")
    )
    bot.send_message(
        message.chat.id,
        "👋 Добро пожаловать!\nПравила использования:\n1) Выберите раздел из меню\n2) Следуйте инструкциям",
        reply_markup=main_keyboard
    )

@bot.message_handler(func=lambda m: m.text == "🏠 О доме")
def handle_home(message):
    home_submenu = types.ReplyKeyboardMarkup(resize_keyboard=True)
    home_submenu.add(types.KeyboardButton("🍽 Еда"), types.KeyboardButton("🔙 Назад"))
    bot.send_message(message.chat.id, "🏡 Наш дом расположен...", reply_markup=home_submenu)

@bot.message_handler(func=lambda m: m.text == "🍽 Еда")
def handle_food(message):
    meal_keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    meal_keyboard.add(types.KeyboardButton("🍳 Завтрак"), types.KeyboardButton("🍽 Ужин"), types.KeyboardButton("🔙 Назад"))
    bot.send_message(message.chat.id, "Выберите тип еды:", reply_markup=meal_keyboard)

@bot.message_handler(func=lambda m: m.text in ["🍳 Завтрак", "🍽 Ужин"])
def choose_meal_type(message):
    meal_type = "breakfast" if message.text == "🍳 Завтрак" else "dinner"
    buttons = [types.KeyboardButton(food) for food in FOOD_MENU[meal_type]]
    buttons.append(types.KeyboardButton("🔙 Назад"))
    bot.send_message(message.chat.id, "Выберите блюдо:", 
                    reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add(*buttons))

@bot.message_handler(func=lambda m: m.text in FOOD_MENU["breakfast"] + FOOD_MENU["dinner"])
def choose_food(message):
    meal_type = "breakfast" if message.text in FOOD_MENU["breakfast"] else "dinner"
    buttons = [types.KeyboardButton(slot) for slot in TIME_SLOTS[meal_type]]
    buttons.append(types.KeyboardButton("🔙 Назад"))
    bot.send_message(message.chat.id, "Выберите время:",
                    reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add(*buttons))

@bot.message_handler(func=lambda m: any(m.text in slots for slots in TIME_SLOTS.values()))
def confirm_order(message):
    user_id = message.chat.id
    meal_type = "breakfast" if message.text in TIME_SLOTS["breakfast"] else "dinner"
    food = next((item for sublist in FOOD_MENU.values() for item in sublist if item in message.text), None)
    
    bot.send_message(user_id, "✅ Заказ отправлен!", reply_markup=types.ReplyKeyboardRemove())
    bot.send_message(OWNER_ID, f"🛎️ Новый заказ!\n👤 {user_id}\n🍽️ {meal_type}\n🍲 {food}\n⏰ {message.text}")

@bot.message_handler(func=lambda m: m.text == "🌆 Город")
def handle_city(message):
    city_submenu = types.ReplyKeyboardMarkup(resize_keyboard=True)
    city_submenu.add(types.KeyboardButton("🏛️ Музей"), types.KeyboardButton("🔙 Назад"))
    bot.send_message(message.chat.id, "Информация о городе...", reply_markup=city_submenu)

@bot.message_handler(func=lambda m: m.text == "🏛️ Музей")
def handle_museum(message):
    bot.send_message(message.chat.id, "🏛️ Музей Карельского фронта\n📍 Адрес: г. Беломорск...")
    start(message)  # Возврат в главное меню

@bot.message_handler(func=lambda m: m.text == "🛍️ Сувениры")
def handle_souvenirs(message):
    souvenir_submenu = types.ReplyKeyboardMarkup(resize_keyboard=True)
    souvenir_submenu.add(types.KeyboardButton("🧲 Магнит"), types.KeyboardButton("🔙 Назад"))
    bot.send_message(message.chat.id, "Доступные сувениры...", reply_markup=souvenir_submenu)

@bot.message_handler(func=lambda m: m.text == "🧲 Магнит")
def handle_magnet(message):
    bot.send_message(message.chat.id, "🧲 Магнит на холодильник - 100р")
    start(message)

@bot.message_handler(func=lambda m: m.text == "Обратная связь")
def handle_feedback(message):
    msg = bot.send_message(message.chat.id, "Напишите ваш отзыв:")
    bot.register_next_step_handler(msg, send_feedback)

def send_feedback(message):
    bot.send_message(OWNER_ID, f"📬 Отзыв от {message.chat.id}:\n{message.text}")
    bot.send_message(message.chat.id, "✅ Спасибо за отзыв!")

@bot.message_handler(func=lambda m: m.text == "🛎 Помощь")
def handle_help(message):
    help_menu = types.ReplyKeyboardMarkup(resize_keyboard=True)
    help_menu.add(types.KeyboardButton("🚖 Такси"), types.KeyboardButton("🏥 Больница"), types.KeyboardButton("🔙 Назад"))
    bot.send_message(message.chat.id, "Помощь:", reply_markup=help_menu)

@bot.message_handler(func=lambda m: m.text in ["🚖 Такси", "🏥 Больница"])
def handle_services(message):
    if message.text == "🚖 Такси":
        bot.send_message(message.chat.id, "Телефон такси: +7-XXX-XXX-XX-XX")
    else:
        bot.send_message(message.chat.id, "Адрес больницы: ул. Больничная, 1")

@bot.message_handler(func=lambda m: m.text == "🔙 Назад")
def go_back(message):
    start(message)

# ================= FLASK ROUTES =================
@app.route("/")
def index():
    return "Bot is running!"

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    if request.method == "POST":
        update = types.Update.de_json(request.get_json(force=True))
        bot.process_new_updates([update])
    return "", 200

@app.route("/ping")
def ping():
    return "OK", 200

# ================= ЗАПУСК =================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
