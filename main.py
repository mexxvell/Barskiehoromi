import os
import logging
import threading
import requests
import asyncio
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    Application,
)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Константы
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
OWNER_ID = os.getenv('OWNER_TELEGRAM_ID')  # Telegram ID владельца
RENDER_URL = os.getenv('RENDER_URL', 'https://barskiehoromi.onrender.com ')

# Проверка обязательных переменных
if not all([TOKEN, RENDER_URL]):
    raise EnvironmentError("Отсутствуют обязательные переменные окружения!")

# Словари
TIME_SLOTS = {
    'breakfast': ['08:00', '09:00', '10:00'],
    'dinner': ['18:00', '19:00', '20:00']
}

FOOD_MENU = {
    'breakfast': {
        '🥞 Яичница': 'omelette',
        '🧇 Блины': 'pancakes',
        '🍵 Чай': 'tea'
    },
    'dinner': {
        '🍲 Суп 1': 'soup1',
        '🍲 Суп 2': 'soup2',
        '🍖 Пюре с мясом': 'meat_puree'
    }
}

PHOTO_PATHS = {
    'main': 'photos/main_photo.jpg',
    'room1': 'photos/room1.jpg',
    'room2': 'photos/room2.jpg',
    'museum': 'photos/museum_carpathian_front.jpg',
    'souvenir': 'photos/souvenir_magnet.jpg'
}

# Стартовая команда
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    main_keyboard = ReplyKeyboardMarkup(
        [
            ["🏛️ Достопримечательности", "🛏️ Комната 1"],
            ["🛏️ Комната 2", "🛍️ Сувенир"]
        ],
        resize_keyboard=True
    )

    with open(PHOTO_PATHS['main'], 'rb') as photo:
        await update.message.reply_photo(
            photo=photo,
            caption="👋 Добро пожаловать в наш дом! 🏡\nВыберите нужный раздел:",
            reply_markup=main_keyboard
        )
    context.user_data['current_menu'] = 'main'

# Обработчик выбора комнаты
async def choose_room(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    room_number = text[-1]
    context.user_data['room'] = room_number
    context.user_data['current_menu'] = 'meal'

    with open(PHOTO_PATHS[f'room{room_number}'], 'rb') as photo:
        await update.message.reply_photo(photo=photo)

    meal_keyboard = ReplyKeyboardMarkup(
        [
            ["🍳 Завтрак", "🍽️ Ужин"],
            ["🔙 Назад"]
        ],
        resize_keyboard=True
    )
    await update.message.reply_text("Выберите, что бы вы хотели:", reply_markup=meal_keyboard)

# Обработчик выбора типа еды
async def choose_meal_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "🔙 Назад":
        await go_back(update, context)
        return

    # Маппинг кнопок к типам еды
    meal_type_map = {
        "🍳 Завтрак": "breakfast",
        "🍽️ Ужин": "dinner"
    }

    meal_type = meal_type_map.get(text)
    if not meal_type:
        await update.message.reply_text("Неизвестный выбор. Попробуйте ещё раз.")
        return

    context.user_data['meal_type'] = meal_type
    context.user_data['current_menu'] = 'food'

    menu = FOOD_MENU[meal_type]
    buttons = [[key] for key in menu.keys()]
    buttons.append(["🔙 Назад"])
    keyboard = ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    await update.message.reply_text("Выберите блюдо:", reply_markup=keyboard)

# Обработчик выбора блюда
async def choose_food(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "🔙 Назад":
        await go_back(update, context)
        return

    meal_type = context.user_data['meal_type']
    food_choice = next(k for k, v in FOOD_MENU[meal_type].items() if k == text)
    context.user_data['food_choice'] = food_choice
    context.user_data['current_menu'] = 'time'

    time_slots = TIME_SLOTS[meal_type]
    buttons = [[slot] for slot in time_slots]
    buttons.append(["🔙 Назад"])
    keyboard = ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    await update.message.reply_text("Выберите удобное время:", reply_markup=keyboard)

# Обработчик выбора времени
async def confirm_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "🔙 Назад":
        await go_back(update, context)
        return

    time_choice = text.strip()

    await update.message.reply_text("✅ Ваш заказ отправлен хозяевам дома!", reply_markup=ReplyKeyboardRemove())

    room = context.user_data['room']
    meal_type = context.user_data['meal_type']
    food = next(k for k, v in FOOD_MENU[meal_type].items() if v == context.user_data['food_choice'])

    message = (
        f"🛎️ Новый заказ!\n"
        f"🛏️ Комната: {room}\n"
        f"🍽️ Тип: {meal_type.capitalize()}\n"
        f"🍲 Блюдо: {food}\n"
        f"⏰ Время: {time_choice}"
    )
    await context.bot.send_message(chat_id=OWNER_ID, text=message)

# Обработчик "Достопримечательности"
async def handle_attractions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['current_menu'] = 'attractions'
    attractions_keyboard = ReplyKeyboardMarkup(
        [
            ["🏛️ Музей Карельского фронта"],
            ["🔙 Назад"]
        ],
        resize_keyboard=True
    )
    await update.message.reply_text("🏛️ Выберите достопримечательность:", reply_markup=attractions_keyboard)

# Обработчик "Музей Карельского фронта"
async def handle_museum(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with open(PHOTO_PATHS['museum'], 'rb') as photo:
        await update.message.reply_photo(
            photo=photo,
            caption="🏛️ Музей Карельского фронта\n📍 Адрес: г. Беломорск, ул. Банковская, д. 26"
        )
    await update.message.reply_text("Выберите нужный раздел:", reply_markup=ReplyKeyboardMarkup(
        [["🏛️ Достопримечательности", "🛏️ Комната 1"], ["🛏️ Комната 2", "🛍️ Сувенир"]],
        resize_keyboard=True
    ))

# Обработчик "Сувениры"
async def handle_souvenirs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['current_menu'] = 'souvenirs'
    souvenir_keyboard = ReplyKeyboardMarkup(
        [
            ["🧲 Магнит на холодильник"],
            ["🔙 Назад"]
        ],
        resize_keyboard=True
    )
    await update.message.reply_text("🛍️ Выберите сувенир:", reply_markup=souvenir_keyboard)

# Обработчик "Магнит на холодильник"
async def handle_magnet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with open(PHOTO_PATHS['souvenir'], 'rb') as photo:
        await update.message.reply_photo(
            photo=photo,
            caption="🧲 Магнит на холодильник"
        )
    await update.message.reply_text("Выберите нужный раздел:", reply_markup=ReplyKeyboardMarkup(
        [["🏛️ Достопримечательности", "🛏️ Комната 1"], ["🛏️ Комната 2", "🛍️ Сувенир"]],
        resize_keyboard=True
    ))

# Обработчик кнопки "Назад"
async def go_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current_menu = context.user_data.get('current_menu', 'main')
    if current_menu == 'main':
        return

    if current_menu == 'meal':
        main_keyboard = ReplyKeyboardMarkup(
            [
                ["🏛️ Достопримечательности", "🛏️ Комната 1"],
                ["🛏️ Комната 2", "🛍️ Сувенир"]
            ],
            resize_keyboard=True
        )
        await update.message.reply_text("Выберите нужный раздел:", reply_markup=main_keyboard)
    elif current_menu == 'attractions':
        main_keyboard = ReplyKeyboardMarkup(
            [
                ["🏛️ Достопримечательности", "🛏️ Комната 1"],
                ["🛏️ Комната 2", "🛍️ Сувенир"]
            ],
            resize_keyboard=True
        )
        await update.message.reply_text("Выберите нужный раздел:", reply_markup=main_keyboard)
    elif current_menu == 'food':
        meal_keyboard = ReplyKeyboardMarkup(
            [
                ["🍳 Завтрак", "🍽️ Ужин"],
                ["🔙 Назад"]
            ],
            resize_keyboard=True
        )
        await update.message.reply_text("Выберите, что бы вы хотели:", reply_markup=meal_keyboard)
    elif current_menu == 'time':
        food_keyboard = ReplyKeyboardMarkup(
            [
                [next(k for k, v in FOOD_MENU[context.user_data['meal_type']].items() if v == context.user_data['food_choice'])],
                ["🔙 Назад"]
            ],
            resize_keyboard=True
        )
        await update.message.reply_text("Выберите блюдо:", reply_markup=food_keyboard)
    elif current_menu == 'souvenirs':
        main_keyboard = ReplyKeyboardMarkup(
            [
                ["🏛️ Достопримечательности", "🛏️ Комната 1"],
                ["🛏️ Комната 2", "🛍️ Сувенир"]
            ],
            resize_keyboard=True
        )
        await update.message.reply_text("Выберите нужный раздел:", reply_markup=main_keyboard)

    context.user_data['current_menu'] = 'main'

# Автопинг каждые 5 минут
def self_ping():
    while True:
        try:
            response = requests.get(RENDER_URL)
            logging.info(f"Self-ping успешен: {response.status_code}")
        except Exception as e:
            logging.error(f"Ошибка self-ping: {str(e)}")
        threading.Event().wait(300)

# Основной запуск
async def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # Регистрация обработчиков
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Regex(r'^🏛️ Достопримечательности$'), handle_attractions))
    app.add_handler(MessageHandler(filters.Regex(r'^🏛️ Музей Карельского фронта$'), handle_museum))
    app.add_handler(MessageHandler(filters.Regex(r'^🛍️ Сувенир$'), handle_souvenirs))
    app.add_handler(MessageHandler(filters.Regex(r'^🧲 Магнит на холодильник$'), handle_magnet))
    app.add_handler(MessageHandler(filters.Regex(r'^🛏️ Комната [12]$'), choose_room))
    app.add_handler(MessageHandler(filters.Regex(r'^🍳 Завтрак$|^🍽️ Ужин$'), choose_meal_type))
    app.add_handler(MessageHandler(filters.Regex(r'^ pancakes|omelette|tea|soup1|soup2|meat_puree$'), choose_food))
    app.add_handler(MessageHandler(filters.Regex(r'^\d{2}:\d{2}$'), confirm_order))
    app.add_handler(MessageHandler(filters.Regex(r'^🔙 Назад$'), go_back))

    # Запуск автопинга
    ping_thread = threading.Thread(target=self_ping)
    ping_thread.start()

    # Установка вебхука
    PORT = int(os.getenv("PORT", 8000))
    WEBHOOK_URL = f"{RENDER_URL}/{TOKEN}"

    logging.info(f"Настройка вебхука на URL: {WEBHOOK_URL}")
    await app.bot.set_webhook(url=WEBHOOK_URL)

    # Запуск вебхука
    await app.run_webhook(listen="0.0.0.0", port=PORT, url_path=TOKEN)

if __name__ == '__main__':
    asyncio.run(main())