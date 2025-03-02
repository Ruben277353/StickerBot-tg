import json
from PIL import Image
import os
import shutil
from pathlib import Path
import string
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.keys import Keys
import time
import random
import asyncio
import logging
import sqlite3
import pyautogui
from webdriver_manager.chrome import ChromeDriverManager  # Автоматическая установка драйвера

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Конфигурация
TELEGRAM_TOKEN = '7889127081:AAFfxysWqHdHRioKcNSAjvbnCcbzFp44ryk'  # Ваш токен Telegram бота
CHROME_PROFILE_PATH = r'C:\Users\WoW\AppData\Local\Google\Chrome\SeleniumProfile'  # Уникальный профиль
SAVE_FOLDER = "telegram_stickers"  # Папка для сохранения стикеров
WHATSAPP_CONTACT = "sd"  # Имя контакта/группы в WhatsApp
DATABASE_PATH = "stickers.db"  # Путь к базе данных

# Инициализация папок
os.makedirs(SAVE_FOLDER, exist_ok=True)
os.makedirs(CHROME_PROFILE_PATH, exist_ok=True)

# Глобальная переменная для драйвера
driver = None

# Инициализация Selenium WebDriver для WhatsApp
def init_whatsapp_driver():
    chrome_options = Options()
    chrome_options.add_argument(f"--user-data-dir={CHROME_PROFILE_PATH}")
    chrome_options.add_argument("--profile-directory=Default")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--remote-allow-origins=*")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--remote-debugging-port=9222")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])

    # Используем webdriver_manager для автоматической загрузки драйвера
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

# Инициализация базы данных
def init_database():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stickers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id TEXT NOT NULL,
            file_path TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

# Добавление стикера в базу данных
def add_sticker_to_db(file_id, file_path):
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO stickers (file_id, file_path) VALUES (?, ?)
    ''', (file_id, file_path))
    conn.commit()
    conn.close()

# Обработка изображения
def process_image(input_path):
    output_path = os.path.join(SAVE_FOLDER, f"processed_{os.path.basename(input_path)}")
    with Image.open(input_path) as img:
        img = img.resize((512, 512), Image.Resampling.LANCZOS)
        if img.mode != 'RGB':
            img = img.convert('RGB')
        img.save(output_path, "WEBP", quality=90)
    return output_path

# Отправка стикера в WhatsApp
def send_to_whatsapp(image_path):
    global driver
    try:
        if driver is None:
            driver = init_whatsapp_driver()
            driver.get("https://web.whatsapp.com")
            time.sleep(20)  # Ожидание сканирования QR-кода

        # Поиск контакта
        search_box = WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.XPATH, '//div[@contenteditable="true"][@data-tab="3"]'))
        )
        search_box.send_keys(WHATSAPP_CONTACT)
        time.sleep(2)
        search_box.send_keys(Keys.ENTER)
        time.sleep(2)

        # Прикрепление стикера
        attach_button = WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.XPATH, '//div[@title="Прикрепить"]')))
        attach_button.click()
        time.sleep(1)

        # Загрузка изображения
        image_input = driver.find_element(By.XPATH, '//input[@accept="image/*,video/mp4,video/3gpp,video/quicktime"]')
        image_input.send_keys(os.path.abspath(image_path))
        time.sleep(2)

        # Отправка стикера
        send_button = driver.find_element(By.XPATH, '//span[@data-icon="send"]')
        send_button.click()
        time.sleep(2)

        logger.info("Стикер отправлен в WhatsApp.")
    except Exception as e:
        logger.error(f"Ошибка при отправке в WhatsApp: {e}")

# Обработчик стикеров Telegram
async def handle_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        sticker = update.message.sticker
        file = await context.bot.get_file(sticker.file_id)

        # Скачивание
        original_path = os.path.join(SAVE_FOLDER, f"original_{sticker.file_id}.webp")
        await file.download_to_drive(original_path)

        # Обработка
        processed_path = process_image(original_path)

        # Сохранение в базу данных
        add_sticker_to_db(sticker.file_id, processed_path)
        logger.info(f"Стикер {sticker.file_id} сохранён в базу данных.")

        # Отправка в WhatsApp
        await update.message.reply_text("✅ Стикер обработан! Отправляю в WhatsApp...")
        await asyncio.to_thread(send_to_whatsapp, processed_path)

        # Очистка
        os.remove(original_path)
        os.remove(processed_path)

    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 Отправьте мне стикер, и я:\n"
        "1. Скачаю его\n"
        "2. Изменю размер до 512x512\n"
        "3. Автоматически отправлю в WhatsApp!"
    )

# Запуск приложения
def main():
    global driver
    try:
        # Инициализация базы данных
        init_database()

        application = Application.builder().token(TELEGRAM_TOKEN).build()

        application.add_handler(CommandHandler("start", start))
        application.add_handler(MessageHandler(filters.Sticker.ALL, handle_sticker))

        logger.info("Запуск бота...")
        application.run_polling()

    finally:
        if driver is not None:
            logger.info("Закрытие драйвера...")
            driver.quit()

if __name__ == '__main__':
    main()