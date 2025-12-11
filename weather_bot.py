import asyncio
import logging
import sys
import requests
import datetime

from config import tg_bot_token, open_weather_token
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Настройка логирования
logging.basicConfig(level=logging.INFO, stream=sys.stdout)

# Кеш
weather_cache = {}
CACHE_TIMEOUT = 300  # 5 минут

# Бот
bot = Bot(token=tg_bot_token)
dp = Dispatcher()

# Смайлики
code_to_smile = {
    "Clear": "Ясно \U00002600",
    "Clouds": "Облачно \U00002601",
    "Rain": "Дождь \U00002614",
    "Drizzle": "Морось \U00002614",
    "Thunderstorm": "Гроза \U000026A1",
    "Snow": "Снег \U0001F328",
    "Mist": "Туман \U0001F32B"
}

def wind_direction(deg):
    dirs = ['С', 'СВ', 'В', 'ЮВ', 'Ю', 'ЮЗ', 'З', 'СЗ']
    idx = round(deg / 45) % 8
    return dirs[idx]

def get_cached_weather(city: str):
    current_time = asyncio.get_event_loop().time()
    if city in weather_cache:
        data, timestamp = weather_cache[city]
        if current_time - timestamp < CACHE_TIMEOUT:
            logging.info(f"📦 Кэш: {city}")
            return data
    try:
        r = requests.get(
            f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={open_weather_token}&units=metric&lang=ru"
        )
        r.raise_for_status()
        data = r.json()
        weather_cache[city] = (data, current_time)
        return data
    except Exception as e:
        logging.error(f"Ошибка API: {e}")
        raise

def create_weather_keyboard(city: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="☁️ Облачность", callback_data=f"cloudiness:{city}"),
            InlineKeyboardButton(text="👁️ Видимость", callback_data=f"visibility:{city}"),
            InlineKeyboardButton(text="📍 Координаты", callback_data=f"coordinates:{city}")
        ],
        [
            InlineKeyboardButton(text="📝 Резюме", callback_data=f"summary:{city}")
        ]
    ])

@dp.message(CommandStart())
async def start_command(message: types.Message):
    await message.reply("🌤 Привет! Напиши город или координаты (широта,долгота) — пришлю погоду!")

@dp.message()
async def get_weather(message: types.Message):
    try:
        text = message.text.strip()
        coords = text.split(',')

        if len(coords) == 2:
            lat, lon = float(coords[0]), float(coords[1])
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError("Некорректные координаты")
            r = requests.get(
                f"http://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={open_weather_token}&units=metric&lang=ru"
            )
            r.raise_for_status()
            data = r.json()
            city = data["name"]
        else:
            data = get_cached_weather(text)
            city = data["name"]

        # Основные данные
        cur_weather = round(data["main"]["temp"])
        feels_like_temp = round(data["main"]["feels_like"])
        temp_min = round(data["main"]["temp_min"])
        temp_max = round(data["main"]["temp_max"])
        wd = code_to_smile.get(data["weather"][0]["main"], "❓")
        humidity = data["main"]["humidity"]
        pressure = round(data["main"]["pressure"] * 0.750062, 1)
        wind = round(data["wind"]["speed"])
        wind_dir = wind_direction(data["wind"]["deg"])

        # 🕰 Время: UTC+5 (без указания пояса)
        local_time = datetime.datetime.utcnow() + datetime.timedelta(hours=5)
        time_str = local_time.strftime('%Y-%m-%d %H:%M')

        # 🌅 Восход / 🌇 Закат — по часовому поясу города
        timezone_offset = data["timezone"]
        sunrise_time = datetime.datetime.utcfromtimestamp(data["sys"]["sunrise"] + timezone_offset).strftime('%H:%M')
        sunset_time = datetime.datetime.utcfromtimestamp(data["sys"]["sunset"] + timezone_offset).strftime('%H:%M')
        length_of_day = datetime.timedelta(seconds=data["sys"]["sunset"] - data["sys"]["sunrise"])

        # Ответ
        await message.reply(
            f"***{time_str}***\n"
            f"🌤 <b>Погода в {city}</b>\n\n"
            f"🌡 Температура: <b>{cur_weather}°C</b> {wd}\n"
            f"🧍 Ощущается: {feels_like_temp}°C\n"
            f"📉 Мин: {temp_min}°C | Макс: {temp_max}°C\n"
            f"💧 Влажность: {humidity}%\n"
            f"🔽 Давление: {pressure} мм рт.ст\n"
            f"🌬 Ветер: {wind} м/с, {wind_dir}\n\n"
            f"🌅 Восход: {sunrise_time}\n"
            f"🌇 Закат: {sunset_time}\n"
            f"⏳ День: {length_of_day}\n\n"
            f"Хорошего дня! ✨",
            parse_mode="HTML",
            reply_markup=create_weather_keyboard(city)
        )

    except ValueError as e:
        if "координаты" in str(e):
            await message.reply("⚠️ Неправильные координаты. Формат: `широта,долгота`")
        else:
            await message.reply("⚠️ Некорректный ввод.")
    except Exception:
        await message.reply("❌ Город не найден. Проверь название.")

# --- Обработчики кнопок (остаются без изменений) ---
@dp.callback_query(lambda c: c.data.startswith('cloudiness:'))
async def handle_cloudiness(callback: types.CallbackQuery):
    try:
        city = callback.data.split(":", 1)[1]
        data = get_cached_weather(city)
        cloudiness = data["clouds"]["all"]
        emoji = "☀️" if cloudiness <= 20 else "⛅" if cloudiness <= 50 else "☁️" if cloudiness <= 80 else "🌧️"
        text = f"☁️ {city}: {cloudiness}% облачности {emoji}"
        await callback.answer(text, show_alert=True)
    except Exception:
        await callback.answer("⚠️ Ошибка при загрузке облачности", show_alert=True)

@dp.callback_query(lambda c: c.data.startswith('visibility:'))
async def handle_visibility(callback: types.CallbackQuery):
    try:
        city = callback.data.split(":", 1)[1]
        data = get_cached_weather(city)
        km = data.get("visibility", 10000) / 1000
        text = f"👁️ Видимость в {city}: {km:.1f} км 🌤️" if km >= 10 else f"👁️ {km:.1f} км {'🌫️' if km < 5 else '⛅'}"
        await callback.answer(text, show_alert=True)
    except Exception:
        await callback.answer("⚠️ Не удалось получить данные", show_alert=True)

@dp.callback_query(lambda c: c.data.startswith('coordinates:'))
async def handle_coordinates(callback: types.CallbackQuery):
    try:
        city = callback.data.split(":", 1)[1]
        data = get_cached_weather(city)
        lat, lon = data["coord"]["lat"], data["coord"]["lon"]
        text = f"📍 {city}\nШирота: {lat}° | Долгота: {lon}°\n\n👉 {lat},{lon}"
        await callback.answer(text, show_alert=True)
    except Exception:
        await callback.answer("⚠️ Не удалось получить координаты", show_alert=True)

@dp.callback_query(lambda c: c.data.startswith('summary:'))
async def handle_summary(callback: types.CallbackQuery):
    try:
        city = callback.data.split(":", 1)[1]
        data = get_cached_weather(city)
        temp = round(data["main"]["temp"])
        feel = round(data["main"]["feels_like"])
        hum = data["main"]["humidity"]
        wd = code_to_smile.get(data["weather"][0]["main"], "❓")
        text = f"📝 {city}\n🌡 {temp}°C {wd}\n🧍 {feel}°C\n💧 {hum}%"
        await callback.answer(text, show_alert=True)
    except Exception:
        await callback.answer("⚠️ Не удалось создать резюме", show_alert=True)

# Запуск
async def main():
    logging.info("🤖 Бот запущен")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())