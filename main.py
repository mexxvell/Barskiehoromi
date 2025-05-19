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
user_data = {}

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
    with open("photos/main_photo.jpg", "rb") as photo:
        bot.send_photo(
            message.chat.id,
            photo,
            caption="🏡 О доме:\nНаш дом расположен в живописном месте. "
                   "Здесь вы найдете уют и комфорт.\n"
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
        "Выберите один из пунктов, и информация будет отправлена хозяевам.",
        reply_markup=meal_keyboard
    )

@bot.message_handler(func=lambda m: m.text in ["🍳 Завтрак", "🍽 Ужин"])
def choose_meal_type(message):
    meal_type = "breakfast" if message.text == "🍳 Завтрак" else "dinner"
    user_data[message.chat.id] = {"meal_type": meal_type}
    buttons = [types.KeyboardButton(food) for food in FOOD_MENU[meal_type]]
    buttons.append(types.KeyboardButton("🔙 Назад"))
    bot.send_message(
        message.chat.id,
        "Выберите блюдо:",
        reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add(*buttons)
    )

@bot.message_handler(func=lambda m: m.text in FOOD_MENU["breakfast"] + FOOD_MENU["dinner"])
def choose_food(message):
    user_id = message.chat.id
    meal_type = user_data[user_id]["meal_type"]
    user_data[user_id]["food"] = message.text
    buttons = [types.KeyboardButton(slot) for slot in TIME_SLOTS[meal_type]]
    buttons.append(types.KeyboardButton("🔙 Назад"))
    bot.send_message(
        message.chat.id,
        "Выберите удобное время:",
        reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add(*buttons)
    )

@bot.message_handler(func=lambda m: any(m.text in slots for slots in TIME_SLOTS.values()))
def confirm_order(message):
    user_id = message.chat.id
    data = user_data.get(user_id, {})
    meal_type = data.get("meal_type", "")
    food = data.get("food", "")
    
    if not meal_type or not food:
        bot.send_message(user_id, "❌ Ошибка обработки заказа.")
        return
    
    # Формирование username
    username = f"@{message.from_user.username}" if message.from_user.username else f"ID: {user_id}"
    
    # Отправка пользователю
    bot.send_message(user_id, "✅ Ваш заказ отправлен хозяевам!", reply_markup=types.ReplyKeyboardRemove())
    
    # Отправка владельцу
    meal_type_ru = "Завтрак" if meal_type == "breakfast" else "Ужин"
    owner_message = (
        f"🛎️ Новый заказ!\n"
        f"👤 Пользователь: {username}\n"
        f"🍽️ Тип: {meal_type_ru}\n"
        f"🍲 Блюдо: {food}\n"
        f"⏰ Время: {message.text}"
    )
    bot.send_message(OWNER_ID, owner_message)
    
    del user_data[user_id]

@bot.message_handler(func=lambda m: m.text == "🌆 Город")
def handle_city(message):
    city_submenu = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    city_submenu.add(
        types.KeyboardButton("🏛️ Музей Карельского фронта"),
        types.KeyboardButton("🚖 Такси"),
        types.KeyboardButton("🏥 Больница"),
        types.KeyboardButton("🔙 Назад")
    )
    bot.send_message(
        message.chat.id,
        "🌆 Г. Беломорск, Республика Карелия:\n"
        "Население: ~12 000 чел.\n"
        "Штаб Карельского фронта во время ВОВ находился здесь.",
        reply_markup=city_submenu
    )

@bot.message_handler(func=lambda m: m.text == "🏛️ Музей Карельского фронта")
def handle_museum(message):
    with open("photos/museum_carpathian_front.jpg", "rb") as photo:
        bot.send_photo(
            message.chat.id,
            photo,
            caption="🏛️ Музей Карельского фронта\n📍 Адрес: г. Беломорск, ул. Банковская, д. 26"
        )
    # Убрано автоматическое возвращение в главное меню

@bot.message_handler(func=lambda m: m.text in ["🚖 Такси", "🏥 Больница"])
def handle_services(message):
    if message.text == "🚖 Такси":
        bot.send_message(message.chat.id, "🚖 Телефон такси: +7-999-999-99-99")
    else:
        bot.send_message(message.chat.id, "🏥 Адрес больницы: г. Беломорск, ул. Больничная, д. 1")

@bot.message_handler(func=lambda m: m.text == "🛍️ Сувениры")
def handle_souvenirs(message):
    souvenir_submenu = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    souvenir_submenu.add(
        types.KeyboardButton("🧲 Магнит на холодильник"), 
        types.KeyboardButton("🔙 Назад")
    )
    bot.send_message(message.chat.id, "🛍️ Сувениры:", reply_markup=souvenir_submenu)

@bot.message_handler(func=lambda m: m.text == "🧲 Магнит на холодильник")
def handle_magnet(message):
    with open("photos/souvenir_magnet.jpg", "rb") as photo:
        bot.send_photo(
            message.chat.id,
            photo,
            caption="🧲 Магнит на холодильник (50 гр) - 100р"
        )
    # Убрано автоматическое возвращение в главное меню

@bot.message_handler(func=lambda m: m.text == "Обратная связь")
def handle_feedback(message):
    msg = bot.send_message(message.chat.id, "💬 Напишите ваш отзыв:")
    bot.register_next_step_handler(msg, send_feedback)

def send_feedback(message):
    username = f"@{message.from_user.username}" if message.from_user.username else f"ID: {message.chat.id}"
    bot.send_message(OWNER_ID, f"📬 Отзыв от {username}:\n{message.text}")
    bot.send_message(message.chat.id, "✅ Сообщение отправлено!", reply_markup=types.ReplyKeyboardRemove())

@bot.message_handler(func=lambda m: m.text == "🔙 Назад")
def go_back(message):
    start(message)

# ================= FLASK ROUTES =================
@app.route("/")
def index():
    return "Telegram-бот работает!", 200

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
