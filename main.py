import os
import logging
import requests
import threading
from flask import Flask, request
import telebot
from telebot import types
from waitress import serve

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Константы
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OWNER_ID = os.getenv("OWNER_TELEGRAM_ID")  # Telegram ID владельца
RENDER_URL = os.getenv("RENDER_URL", "https://barskiehoromi.onrender.com ")

# Проверка переменных окружения
if not all([TOKEN, OWNER_ID, RENDER_URL]):
    raise EnvironmentError("Не заданы обязательные переменные окружения!")

# Конфигурации
TIME_SLOTS = {
    "breakfast": ["08:00", "09:00", "10:00"],
    "dinner": ["18:00", "19:00", "20:00"]
}

FOOD_MENU = {
    "breakfast": {
        "🥞 Яичница": "omelette",
        "🧇 Блины": "pancakes",
        "🍵 Чай": "tea"
    },
    "dinner": {
        "🍲 Суп 1": "soup1",
        "🍲 Суп 2": "soup2",
        "🍖 Пюре с мясом": "meat_puree"
    }
}

PHOTO_PATHS = {
    "main": "photos/main_photo.jpg",
    "museum": "photos/museum_carpathian_front.jpg",
    "souvenir": "photos/souvenir_magnet.jpg"
}

# Flask-приложение
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
        types.KeyboardButton("🛎 Помощь"),
        types.KeyboardButton("Обратная связь")
    )
    bot.send_message(
        message.chat.id,
        "👋 Добро пожаловать в наш дом! 🏡\n"
        "Правила использования:\n"
        "1) Выберите раздел из меню\n"
        "2) Следуйте инструкциям\n"
        "3) При заказе еды укажите удобное время\n"
        "4) Информация отправится хозяевам\n"
        "5) Они свяжутся для уточнения деталей",
        reply_markup=main_keyboard
    )

@bot.message_handler(func=lambda m: m.text == "🏠 О доме")
def handle_home(message):
    with open(PHOTO_PATHS["main"], "rb") as photo:
        bot.send_photo(
            message.chat.id,
            photo,
            caption="🏡 О доме:\n"
                    "Наш дом расположен в живописном месте. Здесь вы найдете уют и комфорт.\n"
                    "Можно заказать еду или получить помощь."
        )
    home_submenu = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    home_submenu.add(types.KeyboardButton("🍽 Еда"), types.KeyboardButton("🔙 Назад"))
    bot.send_message(message.chat.id, "Выберите нужный раздел:", reply_markup=home_submenu)

@bot.message_handler(func=lambda m: m.text == "🍽 Еда")
def handle_food(message):
    meal_keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    meal_keyboard.add(
        types.KeyboardButton("🍳 Завтрак"),
        types.KeyboardButton("🍽 Ужин"),
        types.KeyboardButton("🔙 Назад")
    )
    bot.send_message(
        message.chat.id,
        "🍽 Меню на завтра:\n"
        "Здесь можно заказать еду на завтрак или ужин.\n"
        "Выберите один из пунктов, и информация будет отправлена хозяевам.",
        reply_markup=meal_keyboard
    )

@bot.message_handler(func=lambda m: m.text in ["🍳 Завтрак", "🍽 Ужин"])
def choose_meal_type(message):
    meal_type = "breakfast" if message.text == "🍳 Завтрак" else "dinner"
    user_id = message.chat.id
    bot.reply_to(message, "Выберите блюдо:", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1))
    
    buttons = [types.KeyboardButton(food) for food in FOOD_MENU[meal_type]]
    buttons.append(types.KeyboardButton("🔙 Назад"))
    bot.send_message(user_id, "Выберите блюдо:", reply_markup=types.ReplyKeyboardMarkup(keyboard=[buttons], resize_keyboard=True))

@bot.message_handler(func=lambda m: m.text in FOOD_MENU["breakfast"] or m.text in FOOD_MENU["dinner"])
def choose_food(message):
    user_id = message.chat.id
    meal_type = "breakfast" if message.text in FOOD_MENU["breakfast"] else "dinner"
    
    bot.reply_to(message, "Выберите удобное время:", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1))
    
    buttons = [types.KeyboardButton(slot) for slot in TIME_SLOTS[meal_type]]
    buttons.append(types.KeyboardButton("🔙 Назад"))
    bot.send_message(user_id, "Выберите удобное время:", reply_markup=types.ReplyKeyboardMarkup(keyboard=[buttons], resize_keyboard=True))

@bot.message_handler(func=lambda m: m.text in TIME_SLOTS["breakfast"] or m.text in TIME_SLOTS["dinner"])
def confirm_order(message):
    user_id = message.chat.id
    meal_type = "breakfast" if message.text in TIME_SLOTS["breakfast"] else "dinner"
    food = next(k for k, v in FOOD_MENU[meal_type].items() if v == bot.get_user_context()[user_id].get("food_choice"))
    
    bot.send_message(
        user_id,
        "✅ Ваш заказ отправлен хозяевам дома!",
        reply_markup=types.ReplyKeyboardRemove()
    )
    
    message_text = (
        f"🛎️ Новый заказ!\n"
        f"👤 Пользователь: {user_id}\n"
        f"🍽️ Тип: {meal_type.capitalize()}\n"
        f"🍲 Блюдо: {food}\n"
        f"⏰ Время: {message.text}"
    )
    bot.send_message(OWNER_ID, message_text)

@bot.message_handler(func=lambda m: m.text == "🌆 Город")
def handle_city(message):
    city_submenu = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    city_submenu.add(types.KeyboardButton("🏛️ Достопримечательности"), types.KeyboardButton("🔙 Назад"))
    bot.send_message(
        message.chat.id,
        "🌆 Г. Беломорск, Республика Карелия:\n"
        "Население: ~12 000 чел.\n"
        "Штаб Карельского фронта во время ВОВ находился здесь.",
        reply_markup=city_submenu
    )

@bot.message_handler(func=lambda m: m.text == "🏛️ Достопримечательности")
def handle_attractions(message):
    attractions_submenu = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    attractions_submenu.add(types.KeyboardButton("🏛️ Музей Карельского фронта"), types.KeyboardButton("🔙 Назад"))
    bot.send_message(
        message.chat.id,
        "🏛️ Выберите достопримечательность:",
        reply_markup=attractions_submenu
    )

@bot.message_handler(func=lambda m: m.text == "🏛️ Музей Карельского фронта")
def handle_museum(message):
    with open(PHOTO_PATHS["museum"], "rb") as photo:
        bot.send_photo(
            message.chat.id,
            photo,
            caption="🏛️ Музей Карельского фронта\n📍 Адрес: г. Беломорск, ул. Банковская, д. 26"
        )
    main_keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    main_keyboard.add(
        types.KeyboardButton("🏠 О доме"),
        types.KeyboardButton("🛍️ Сувениры"),
        types.KeyboardButton("Обратная связь"),
        types.KeyboardButton("🛎 Помощь")
    )
    bot.send_message(message.chat.id, "Выберите нужный раздел:", reply_markup=main_keyboard)

@bot.message_handler(func=lambda m: m.text == "🛍️ Сувениры")
def handle_souvenirs(message):
    souvenir_submenu = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    souvenir_submenu.add(types.KeyboardButton("🧲 Магнит на холодильник"), types.KeyboardButton("🔙 Назад"))
    bot.send_message(
        message.chat.id,
        "🛍️ Сувениры:",
        reply_markup=souvenir_submenu
    )

@bot.message_handler(func=lambda m: m.text == "🧲 Магнит на холодильник")
def handle_magnet(message):
    with open(PHOTO_PATHS["souvenir"], "rb") as photo:
        bot.send_photo(
            message.chat.id,
            photo,
            caption="🧲 Магнит на холодильник (50 гр) - 100р"
        )
    main_keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    main_keyboard.add(
        types.KeyboardButton("🏠 О доме"),
        types.KeyboardButton("🛍️ Сувениры"),
        types.KeyboardButton("Обратная связь"),
        types.KeyboardButton("🛎 Помощь")
    )
    bot.send_message(message.chat.id, "Выберите нужный раздел:", reply_markup=main_keyboard)

@bot.message_handler(func=lambda m: m.text == "Обратная связь")
def handle_feedback(message):
    bot.send_message(
        message.chat.id,
        "💬 Здесь можно оставить обратную связь:\n"
        "Расскажите, что можно улучшить или что доставило дискомфорт.\n"
        "Напишите ваше сообщение и нажмите '✅ Отправить'."
    )
    bot.register_next_step_handler(message, send_feedback)

@bot.message_handler(func=lambda m: m.text == "✅ Отправить")
def send_feedback(message):
    user_message = message.text
    message_text = f"📬 Новая обратная связь:\n{user_message}"
    bot.send_message(OWNER_ID, message_text)
    bot.send_message(
        message.chat.id,
        "✅ Сообщение отправлено хозяевам!",
        reply_markup=types.ReplyKeyboardRemove()
    )

@bot.message_handler(func=lambda m: m.text == "🛎 Помощь")
def handle_help(message):
    help_submenu = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    help_submenu.add(
        types.KeyboardButton("🚖 Такси"),
        types.KeyboardButton("🏥 Больница"),
        types.KeyboardButton("🔙 Назад")
    )
    bot.send_message(
        message.chat.id,
        "🛎️ Помощь:\n"
        "Здесь можно найти важную информацию о городе и услугах.",
        reply_markup=help_submenu
    )

@bot.message_handler(func=lambda m: m.text == "🚖 Такси")
def handle_taxi(message):
    bot.send_message(
        message.chat.id,
        "🚖 Такси:\n"
        "Телефон такси: +7-999-999-99-99",
        reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True, keyboard=[[types.KeyboardButton("🔙 Назад")]])
    )

@bot.message_handler(func=lambda m: m.text == "🏥 Больница")
def handle_hospital(message):
    bot.send_message(
        message.chat.id,
        "🏥 Больница:\n"
        "Адрес: г. Беломорск, ул. Больничная, д. 1",
        reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True, keyboard=[[types.KeyboardButton("🔙 Назад")]])
    )

@bot.message_handler(func=lambda m: m.text == "🔙 Назад")
def go_back(message):
    main_keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    main_keyboard.add(
        types.KeyboardButton("🏠 О доме"),
        types.KeyboardButton("🌆 Город"),
        types.KeyboardButton("🛍️ Сувениры"),
        types.KeyboardButton("Обратная связь"),
        types.KeyboardButton("🛎 Помощь")
    )
    bot.send_message(message.chat.id, "Выберите нужный раздел:", reply_markup=main_keyboard)

# ================= ФЛЭШ-МАРШРУТЫ =================
@app.route("/")
def index():
    return "Telegram-бот работает!", 200

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = types.Update.de_json(request.get_data(as_text=True))
    bot.process_new_updates([update])
    return "", 200

@app.route("/ping")
def ping():
    return "OK", 200

# ================= ЗАПУСК СЕРВИСА =================
def self_ping():
    while True:
        try:
            response = requests.get(f"{RENDER_URL}/ping")
            logger.info(f"Self-ping: Status {response.status_code}")
        except Exception as e:
            logger.error(f"Ошибка self-ping: {str(e)}")
        threading.Event().wait(300)

if __name__ == "__main__":
    # Запуск Flask-сервера
    PORT = int(os.getenv("PORT", 8000))
    serve(app, host="0.0.0.0", port=PORT)
    
    # Запуск автопинга
    ping_thread = threading.Thread(target=self_ping, daemon=True)
    ping_thread.start()
