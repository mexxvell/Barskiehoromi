import os
import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Константы
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
OWNER_ID = os.getenv('OWNER_TELEGRAM_ID')  # Telegram ID владельца

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
            ["🏛️ Музей", "🛏️ Комната 1"],
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

# Обработчик выбора комнаты
async def choose_room(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    room_number = text[-1]
    context.user_data['room'] = room_number

    with open(PHOTO_PATHS[f'room{room_number}'], 'rb') as photo:
        await update.message.reply_photo(photo=photo)

    meal_keyboard = ReplyKeyboardMarkup(
        [
            ["🍳 Завтрак", "🍽️ Ужин"]
        ],
        resize_keyboard=True
    )
    await update.message.reply_text("Выберите, что бы вы хотели:", reply_markup=meal_keyboard)

# Обработчик выбора типа еды
async def choose_meal_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    meal_type = text.strip().lower()
    context.user_data['meal_type'] = meal_type

    menu = FOOD_MENU[meal_type]
    buttons = [[key] for key in menu.keys()]
    keyboard = ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    await update.message.reply_text("Выберите блюдо:", reply_markup=keyboard)

# Обработчик выбора блюда
async def choose_food(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    meal_type = context.user_data['meal_type']
    food_choice = next(k for k, v in FOOD_MENU[meal_type].items() if k == text)
    context.user_data['food_choice'] = food_choice

    time_slots = TIME_SLOTS[meal_type]
    buttons = [[slot] for slot in time_slots]
    keyboard = ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    await update.message.reply_text("Выберите удобное время:", reply_markup=keyboard)

# Обработчик выбора времени
async def confirm_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
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

# Обработчик музея
async def handle_museum(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with open(PHOTO_PATHS['museum'], 'rb') as photo:
        await update.message.reply_photo(
            photo=photo,
            caption="🏛️ Музей Карельского фронта\n📍 Адрес: г. Беломорск, ул. Банковская, д. 26"
        )
    await update.message.reply_text("Выберите нужный раздел:", reply_markup=ReplyKeyboardMarkup(
        [["🏛️ Музей", "🛏️ Комната 1"], ["🛏️ Комната 2", "🛍️ Сувенир"]],
        resize_keyboard=True
    ))

# Обработчик сувенира
async def handle_souvenir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with open(PHOTO_PATHS['souvenir'], 'rb') as photo:
        await update.message.reply_photo(
            photo=photo,
            caption="🛍️ Магнит на холодильник"
        )
    await update.message.reply_text("Выберите нужный раздел:", reply_markup=ReplyKeyboardMarkup(
        [["🏛️ Музей", "🛏️ Комната 1"], ["🛏️ Комната 2", "🛍️ Сувенир"]],
        resize_keyboard=True
    ))

# Основной запуск
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Regex(r'^🏛️ Музей$'), handle_museum))
    app.add_handler(MessageHandler(filters.Regex(r'^🛍️ Сувенир$'), handle_souvenir))
    app.add_handler(MessageHandler(filters.Regex(r'^🛏️ Комната [12]$'), choose_room))
    app.add_handler(MessageHandler(filters.Regex(r'^🍳 Завтрак$|^🍽️ Ужин$'), choose_meal_type))
    app.add_handler(MessageHandler(filters.Regex(r'^ pancakes|omelette|tea|soup1|soup2|meat_puree$'), choose_food))
    app.add_handler(MessageHandler(filters.Regex(r'^\d{2}:\d{2}$'), confirm_order))

    app.run_polling()

if __name__ == '__main__':
    main()