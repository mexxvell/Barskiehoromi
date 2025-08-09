import os
import logging
import sqlite3
import threading
import time
import requests
from io import BytesIO
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
    # корзина (оставляем прежнюю структуру, но при добавлении в корзину будем хранить цену)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS merch_cart (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            item TEXT,
            quantity INTEGER,
            price INTEGER
        )
    ''')
    # лог уникальных пользователей
    cur.execute('''
        CREATE TABLE IF NOT EXISTS user_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            date TEXT
        )
    ''')

    # таблица заказов с статусами
    cur.execute('''
        CREATE TABLE IF NOT EXISTS merch_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            item TEXT,
            quantity INTEGER,
            price INTEGER,
            total INTEGER,
            date TEXT,
            status TEXT
        )
    ''')

    # подписчики на события
    cur.execute('''
        CREATE TABLE IF NOT EXISTS subscriptions (
            user_id INTEGER PRIMARY KEY
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

# --- Словарь товаров мерча (название: (цена, файл фото или список фото)) ---
MERCH_ITEMS = {
    "👜 Сумка Шоппер":   (500, ["shopper.jpg", "shopper1.jpg"]),
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

# --- Рассылка статистики владельцу (ежедневно в 23:59) ---
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
            try:
                bot.send_message(OWNER_ID, f"📊 Уникальных пользователей за {today}: {count}")
            except Exception as e:
                logger.error(f"Ошибка при отправке статистики владельцу: {e}")
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
    conn = sqlite3.connect('bot_data.db')
    cur = conn.cursor()
    cur.execute("INSERT INTO merch_cart (user_id, item, quantity, price) VALUES (?, ?, ?, ?)",
                (user_id, item, quantity, price))
    conn.commit()
    conn.close()

def get_cart_items(user_id):
    conn = sqlite3.connect('bot_data.db')
    cur = conn.cursor()
    cur.execute("SELECT item, quantity, price FROM merch_cart WHERE user_id=?", (user_id,))
    rows = cur.fetchall()
    conn.close()
    return rows

def clear_cart(user_id):
    conn = sqlite3.connect('bot_data.db')
    cur = conn.cursor()
    cur.execute("DELETE FROM merch_cart WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

def create_order_from_cart(user_id, username):
    items = get_cart_items(user_id)
    if not items:
        return None
    conn = sqlite3.connect('bot_data.db')
    cur = conn.cursor()
    today = str(date.today())
    order_lines = []
    total_sum = 0
    for item, qty, price in items:
        total = qty * price
        total_sum += total
        cur.execute(
            "INSERT INTO merch_orders (user_id, username, item, quantity, price, total, date, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, username, item, qty, price, total, today, "В обработке")
        )
        order_lines.append(f"- {item} ×{qty} = {total}₽")
    conn.commit()
    conn.close()
    clear_cart(user_id)
    return total_sum, order_lines

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
    # админ может вызвать панель через /admin, не добавляем админ-кнопку в общий интерфейс
    bot.send_message(message.chat.id, "👋 Добро пожаловать!\n"
                "👥 Команда — познакомьтесь с нами\n"
                "🌍 Путешествия — авторские туры и ретриты\n"
                "🧘 Кундалини-йога — практика и трансформация\n"
                "📸 Медиа — вдохновляющие фото и видео\n"
                "🛍 Мерч — одежда и аксессуары ScanDream\n"
                "🎁 Доп. услуги — всё для вашего комфорта", reply_markup=kb)

# --- Разделы (без изменений логики, добавлены опции подписки в Доп. услуги) ---
@bot.message_handler(func=lambda m: m.text == "🌍 Путешествия")
def travels_menu(message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("📂 Архив путешествий", "🌍 Где мы сейчас", "🔙 Назад к меню")
    bot.send_message(message.chat.id, "✈️ Путешествия: архив и текущее местоположение.", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "🧘 Кундалини-йога")
def yoga_menu(message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🏢 Офлайн-мероприятия", "💻 Онлайн-йога", "📅 Ближайшие мероприятия", "🔙 Назад к меню")
    bot.send_message(message.chat.id, "🧘 Кундалини-йога: офлайн, онлайн и ближайшие события.", reply_markup=kb)

# --- Онлайн-йога (оставил как есть) ---
@bot.message_handler(func=lambda m: m.text == "💻 Онлайн-йога")
def online_yoga(message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("Да, хочу", "Приобрести подписку", "🔙 Назад к онлайн-йоге")
    bot.send_message(message.chat.id, """Это уникальная возможность быть в поле мастера онлайн. Практики диктуемые эпохой Водолея. Медитации. Работа в малых группах.
Занятия проходят каждый вт и чт в 05:00 по мск. Все записи хранятся в канале группы.
Ценность: 2500 рублей месяц, продление - 2300 руб.
Хотите посмотреть пробный класс?""", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "Да, хочу")
def try_online_yoga(message):
    bot.send_message(message.chat.id, "https://disk.yandex.ru/i/nCQFa8edIspzNA")
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("Приобрести подписку", "🔙 Назад к онлайн-йоге")
    bot.send_message(message.chat.id, "Если вам понравилось и вы хотели бы дополнительно узнать больше о онлайн занятии, нажмите кнопку приобрести подписку и мы обязательно свяжемся с вами!", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "Приобрести подписку")
def buy_subscription(message):
    # Отправляем информацию владельцу
    user_info = f"Пользователь @{message.from_user.username or message.chat.id} хочет приобрести подписку на онлайн-йогу."
    bot.send_message(OWNER_ID, user_info)
    # Сообщаем пользователю
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🔙 Назад к онлайн-йоге")
    bot.send_message(message.chat.id, "Спасибо, что выбрали нас, мы скоро свяжемся с вами! 😊", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "🔙 Назад к онлайн-йоге")
def back_to_online_yoga_menu(message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🏢 Офлайн-мероприятия", "💻 Онлайн-йога", "📅 Ближайшие мероприятия", "🔙 Назад к меню")
    bot.send_message(message.chat.id, "🧘 Кундалини-йога: офлайн, онлайн и ближайшие события.", reply_markup=kb)

# --- Новые обработчики (как были) ---
@bot.message_handler(func=lambda m: m.text == "📅 Ближайшие мероприятия")
def upcoming_events(message):
    bot.send_message(message.chat.id, """- 10 августа мы отправляемся в «Большой Волжский Путь», путешествие на автодоме из Карелии на фестиваль кундалини-йоги в Волгоград:

7 августа - Тольятти - <a href="https://t.me/+PosQ9pcHMIk4NjQ6">Большой класс и саундхидинг</a>
9 августа - Волгоград - <a href="https://t.me/+ii8MpmrGhMo2YTVi">Большой класс и саундхилинг</a>
10 августа - площадка 17 фестиваля кундалини-йоги - Большой класс.

11 - 19 августа фестиваль кундалини-йоги (Волгоград)""", parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "▶️ YouTube")
def youtube_channel(message):
    bot.send_message(message.chat.id, "https://www.youtube.com/@ScanDreamChannel")

@bot.message_handler(func=lambda m: m.text == "📸 Медиа")
def media_menu(message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("▶️ YouTube", "🔙 Назад к меню")
    bot.send_message(message.chat.id, "🎥 Медиа: наши видео на YouTube.", reply_markup=kb)

# --- Доп. услуги: добавлены кнопки подписки/отписки ---
@bot.message_handler(func=lambda m: m.text == "🎁 Доп. услуги")
def services_menu(message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("📢 Подписаться на события", "🚫 Отписаться от событий", "🔙 Назад к меню")
    bot.send_message(message.chat.id, "🔧 Дополнительные услуги: детали по запросу.", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "📢 Подписаться на события")
def subscribe_events(message):
    conn = sqlite3.connect('bot_data.db')
    cur = conn.cursor()
    try:
        cur.execute("INSERT OR IGNORE INTO subscriptions (user_id) VALUES (?)", (message.chat.id,))
        conn.commit()
        bot.send_message(message.chat.id, "Вы успешно подписались на события. Будем отправлять уведомления о новых ретритах и мероприятиях.")
    except Exception as e:
        logger.error(f"Ошибка подписки: {e}")
        bot.send_message(message.chat.id, "Ошибка при подписке. Попробуйте позже.")
    finally:
        conn.close()

@bot.message_handler(func=lambda m: m.text == "🚫 Отписаться от событий")
def unsubscribe_events(message):
    conn = sqlite3.connect('bot_data.db')
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM subscriptions WHERE user_id=?", (message.chat.id,))
        conn.commit()
        bot.send_message(message.chat.id, "Вы отписаны от рассылки событий.")
    except Exception as e:
        logger.error(f"Ошибка отписки: {e}")
        bot.send_message(message.chat.id, "Ошибка при отписке. Попробуйте позже.")
    finally:
        conn.close()

@bot.message_handler(func=lambda m: m.text == "👥 Команда")
def team_menu(message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🏷 О бренде", "🌐 Официальные источники", "🔙 Назад к меню")
    bot.send_message(message.chat.id, """Нас зовут Алексей Бабенко — учитель кундалини-йоги, визионер, путешественник, кинематографист, медиа-продюсер.
Более 20 лет личной практики, 18 лет преподавания. Преподаватель тренинга школы Амрит Нам Саровар (Франция) в России.
Создатель йога-кемпа и ретритов по Карелии, Северной Осетии, Грузии, Армении и Турции.
И Анастасия Голик — сертифицированный инструктор хатха-йоги, аромапрактик, вдохновитель и заботливая спутница ретритов.""", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "🏷 О бренде")
def about_brand(message):
    bot.send_message(message.chat.id, """ScanDream - https://t.me/scandream - зарегистрированный товарный знак, основная идея которого осознанные творческие коммуникации. ScanDream - это место, где мы пересобираем конструкт Мира, рассматривая и восхищаясь его строением. Быть #scandream - это сканировать свое жизненное предназначение действием и мечтой. В реальности оставаться активным, осознанным и логичным, а мечтать широко, мощно, свободно и не ощущая предела. 
Проект йога-кемп - это творческая интеграция опыта и пользы. Пользы через новые знания и умения. Умения через новые формы.""")

@bot.message_handler(func=lambda m: m.text == "🌐 Официальные источники")
def official_sources(message):
    bot.send_message(message.chat.id, """ОФИЦИАЛЬНЫЕ ИСТОЧНИКИ взаимодействия с командой ScanDream:
1. Личная страница в ВК Алексея - https://vk.ru/scandream
2. Моя личная страница в ВК - https://vk.ru/yoga.golik
3. Официальный ТГ канал ScanDream•Live - https://t.me/scandream
4. Личный ТГ канал Алексея - https://t.me/scandreamlife
5. Личный мой ТГ канал - https://t.me/yogagolik_dnevnik
6. Йога с Алексеем Бабенко в ВК (Петрозаводск) - https://vk.ru/kyogababenko""")

# Назад
@bot.message_handler(func=lambda m: m.text == "🔙 Назад к меню")
def back_to_menu(message):
    start(message)

# --- Мерч: меню (не тронул основной UX, добавил хранение цены в корзине) ---
@bot.message_handler(func=lambda m: m.text == "🛍 Мерч")
def merch_menu(message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for name in MERCH_ITEMS:
        kb.add(types.KeyboardButton(name))
    kb.add("🛍️ Корзина", "🔙 Назад к меню", "📦 Мои заказы")
    bot.send_message(message.chat.id, "🛍️ Выберите товар:", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text in MERCH_ITEMS)
def show_merch_item(message):
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

    # цена из словаря
    price = MERCH_ITEMS[item_name][0]
    # сохраняем в корзину с ценой
    add_to_cart_db(message.chat.id, item_name[2:], qty, price)
    bot.send_message(message.chat.id, f"✔️ Добавлено: {item_name[2:]} ×{qty} ({price}₽/шт)")
    merch_menu(message)

@bot.message_handler(func=lambda m: m.text == "🛍️ Корзина")
def show_merch_cart(message):
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
    text = "\n".join(lines) + f"\n\nИтого: {total}₽"
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("✅ Оформить заказ", "🗑 Очистить корзину", "🔙 Назад к Мерч")
    bot.send_message(message.chat.id, f"🛒 Корзина:\n{text}", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "🗑 Очистить корзину")
def clear_cart_handler(message):
    clear_cart(message.chat.id)
    bot.send_message(message.chat.id, "Корзина очищена.")
    merch_menu(message)

@bot.message_handler(func=lambda m: m.text == "✅ Оформить заказ")
def send_merch_order(message):
    # создаём заказы из корзины (несколько записей — по каждому предмету)
    username = f"@{message.from_user.username}" if message.from_user.username else str(message.chat.id)
    result = create_order_from_cart(message.chat.id, username)
    if not result:
        bot.send_message(message.chat.id, "Корзина пуста.")
        return
    total_sum, order_lines = result
    order_text = f"Новый заказ от {username}:\n" + "\n".join(order_lines) + f"\nИтого: {total_sum}₽"
    # отправляем владельцу
    bot.send_message(OWNER_ID, order_text)
    # подтверждение пользователю
    bot.send_message(message.chat.id, "Спасибо, заказ отправлен владельцу! 🎉\nСтатус заказа: В обработке")
    merch_menu(message)

@bot.message_handler(func=lambda m: m.text == "🔙 Назад к Мерч")
def back_to_merch(message):
    merch_menu(message)

# --- Мои заказы (пользователь) ---
@bot.message_handler(func=lambda m: m.text == "📦 Мои заказы")
def my_orders(message):
    conn = sqlite3.connect('bot_data.db')
    cur = conn.cursor()
    cur.execute("SELECT id, item, quantity, price, total, date, status FROM merch_orders WHERE user_id=? ORDER BY id DESC", (message.chat.id,))
    rows = cur.fetchall()
    conn.close()
    if not rows:
        bot.send_message(message.chat.id, "У вас нет заказов.")
        merch_menu(message)
        return
    text_lines = []
    for oid, item, qty, price, total, date_str, status in rows:
        text_lines.append(f"#{oid} — {item} ×{qty} ({price}₽/шт) = {total}₽ | {status} | {date_str}")
    bot.send_message(message.chat.id, "Ваши заказы:\n" + "\n".join(text_lines))
    merch_menu(message)

# --- Админ-панель и команды владельца ---
@bot.message_handler(commands=['admin'])
def admin_command(message):
    if message.chat.id != OWNER_ID:
        return
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("📊 Статистика", "🛍 Заказы", "📬 Рассылка", "📢 Подписчики", "🔙 В главное меню")
    bot.send_message(message.chat.id, "Админ-панель:", reply_markup=kb)

@bot.message_handler(func=lambda m: m.chat.id == OWNER_ID and m.text == "📊 Статистика")
def admin_stats(message):
    conn = sqlite3.connect('bot_data.db')
    cur = conn.cursor()
    # сегодня
    today = str(date.today())
    cur.execute("SELECT COUNT(DISTINCT user_id) FROM user_log WHERE date=?", (today,))
    today_count = cur.fetchone()[0]
    # всего уникальных пользователей (по всем датам)
    cur.execute("SELECT COUNT(DISTINCT user_id) FROM user_log")
    total_count = cur.fetchone()[0]
    conn.close()
    bot.send_message(OWNER_ID, f"📊 Статистика\nСегодня: {today_count}\nЗа всё время: {total_count}")

@bot.message_handler(func=lambda m: m.chat.id == OWNER_ID and m.text == "🛍 Заказы")
def admin_orders(message):
    conn = sqlite3.connect('bot_data.db')
    cur = conn.cursor()
    cur.execute("SELECT id, user_id, username, item, quantity, total, date, status FROM merch_orders ORDER BY id DESC LIMIT 50")
    rows = cur.fetchall()
    conn.close()
    if not rows:
        bot.send_message(OWNER_ID, "Заказов нет.")
        return
    lines = []
    for oid, user_id, username, item, qty, total, date_str, status in rows:
        lines.append(f"#{oid} | {username} ({user_id}) | {item}×{qty} | {total}₽ | {status}")
    bot.send_message(OWNER_ID, "Последние заказы:\n" + "\n".join(lines))
    bot.send_message(OWNER_ID, "Чтобы изменить статус заказа: отправьте `status <id> <новый статус>` (например: status 12 Отправлен)", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.chat.id == OWNER_ID and m.text and m.text.startswith("status "))
def admin_change_status(message):
    # формат: status <id> <новый статус>
    parts = message.text.split(" ", 2)
    if len(parts) < 3:
        bot.send_message(OWNER_ID, "Неправильный формат. Используйте: status <id> <новый статус>")
        return
    try:
        oid = int(parts[1])
        new_status = parts[2].strip()
    except:
        bot.send_message(OWNER_ID, "Неправильный формат id.")
        return
    conn = sqlite3.connect('bot_data.db')
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM merch_orders WHERE id=?", (oid,))
    row = cur.fetchone()
    if not row:
        bot.send_message(OWNER_ID, f"Заказ #{oid} не найден.")
        conn.close()
        return
    user_id = row[0]
    cur.execute("UPDATE merch_orders SET status=? WHERE id=?", (new_status, oid))
    conn.commit()
    conn.close()
    bot.send_message(OWNER_ID, f"Статус заказа #{oid} изменён на: {new_status}")
    try:
        bot.send_message(user_id, f"Обновление статуса вашего заказа #{oid}: {new_status}")
    except Exception as e:
        logger.error(f"Не удалось уведомить пользователя {user_id}: {e}")

@bot.message_handler(func=lambda m: m.chat.id == OWNER_ID and m.text == "📬 Рассылка")
def admin_broadcast_init(message):
    bot.send_message(OWNER_ID, "Отправьте текст рассылки (будет отправлено всем подписчикам).")
    msg = bot.send_message(OWNER_ID, "Жду текст для рассылки:")
    bot.register_next_step_handler(msg, admin_broadcast_send)

def admin_broadcast_send(message):
    text = message.text
    conn = sqlite3.connect('bot_data.db')
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM subscriptions")
    rows = cur.fetchall()
    conn.close()
    if not rows:
        bot.send_message(OWNER_ID, "Нет подписчиков для рассылки.")
        return
    sent = 0
    for (user_id,) in rows:
        try:
            bot.send_message(user_id, text)
            sent += 1
        except Exception as e:
            logger.error(f"Ошибка при отправке рассылки {user_id}: {e}")
    bot.send_message(OWNER_ID, f"Рассылка отправлена. Успешных отправок: {sent}")

@bot.message_handler(func=lambda m: m.chat.id == OWNER_ID and m.text == "📢 Подписчики")
def admin_list_subscribers(message):
    conn = sqlite3.connect('bot_data.db')
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM subscriptions")
    rows = cur.fetchall()
    conn.close()
    if not rows:
        bot.send_message(OWNER_ID, "Нет подписчиков.")
        return
    lst = ", ".join([str(r[0]) for r in rows])
    # при большом количестве можно ограничить вывод, но для простоты отдаём весь список
    bot.send_message(OWNER_ID, f"Подписчики: {lst}")

@bot.message_handler(func=lambda m: m.chat.id == OWNER_ID and m.text == "🔙 В главное меню")
def admin_back(message):
    start(message)

# --- Обработчик webhook для Flask ---
@app.route("/")
def index():
    return "Bot is running!"

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = types.Update.de_json(request.get_json(force=True))
    bot.process_new_updates([update])
    return "", 200

if __name__ == "__main__":
    # запуск Flask (как у тебя было)
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
