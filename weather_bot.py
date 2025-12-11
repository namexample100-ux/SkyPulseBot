import asyncio
import logging
import sys
import requests
import datetime

from config import tg_bot_token, open_weather_token

from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import time

# Простой кеш в памяти: {город: (данные, timestamp)}
weather_cache = {}
CACHE_TIMEOUT = 300  # 5 минут в секундах

# Инициализация бота и диспетчера
bot = Bot(token=tg_bot_token)
dp = Dispatcher()

# Словарь смайликов для погоды (остаётся без изменений)
code_to_smile = {
    "Clear": "Ясно \U00002600",
    "Clouds": "Облачно \U00002601",
    "Rain": "Дождь \U00002614",
    "Drizzle": "Дождь \U00002614",
    "Thunderstorm": "Гроза \U000026A1",
    "Snow": "Снег \U0001F328",
    "Mist": "Туман \U0001F32B"
}

def feels_like(data):
    return data["main"]["feels_like"]

def get_current_time():
    """Возвращает текущее время в нужном формате."""
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M')

def wind_direction(deg):
    """Переводит градусы в направление по сторонам света."""
    dirs = ['С', 'СВ', 'В', 'ЮВ', 'Ю', 'ЮЗ', 'З', 'СЗ']
    idx = round(deg / 45) % 8
    return dirs[idx]

def get_cached_weather(city: str):
    """
    Получает данные из кеша или делает запрос к API.
    Возвращает данные о погоде для города.
    """
    current_time = time.time()

    # Проверяем, есть ли город в кеше и не устарели ли данные
    if city in weather_cache:
        cached_data, timestamp = weather_cache[city]
        if current_time - timestamp < CACHE_TIMEOUT:
            logging.info(f"📦 Используем кеш для города: {city}")
            return cached_data
        else:
            logging.info(f"🕒 Данные для {city} устарели, обновляем...")

    # Если данных нет или они устарели — делаем запрос
    logging.info(f"🌐 Запрашиваем API для города: {city}")
    r = requests.get(
        f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={open_weather_token}&units=metric&lang=ru"
    )
    data = r.json()

    # Сохраняем в кеш с текущим временем
    weather_cache[city] = (data, current_time)
    return data

def create_weather_keyboard(city: str):
    """
    Создаёт inline-клавиатуру для дополнительных параметров погоды.
    Теперь с двумя рядами кнопок.
    """
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        # Первый ряд: основные параметры
        [
            InlineKeyboardButton(text="☁️ Облачность", callback_data=f"cloudiness:{city}"),
            InlineKeyboardButton(text="👁️ Видимость", callback_data=f"visibility:{city}"),
            InlineKeyboardButton(text="📍 Координаты", callback_data=f"coordinates:{city}")
        ],
        # Второй ряд: одна центральная кнопка "Резюме"
        [
            InlineKeyboardButton(text="📝 Краткое резюме", callback_data=f"summary:{city}")
        ]
    ])
    return keyboard

# Обработчик команды /start с использованием фильтра CommandStart
@dp.message(CommandStart())
async def start_command(message: types.Message):
    await message.reply("Привет! Напиши мне название города или координаты (широта,долгота) и я пришлю сводку погоды!")

# Обработчик всех текстовых сообщений
@dp.message()
async def get_weather(message: types.Message):
    try:
        # Проверяем, является ли сообщение координатами (формат: широта,долгота)
        coords = message.text.strip().split(',')
        if len(coords) == 2:
            try:
                lat = float(coords[0].strip())
                lon = float(coords[1].strip())
                # Проверяем, что координаты в допустимом диапазоне
                if -90 <= lat <= 90 and -180 <= lon <= 180:
                    # Для координат используем прямой запрос (кеш не подходит, так как нет города)
                    r = requests.get(
                        f"http://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={open_weather_token}&units=metric&lang=ru"
                    )
                    data = r.json()
                    city = data["name"]
                else:
                    raise ValueError("Координаты вне допустимого диапазона")
            except ValueError as e:
                logging.error(f"Ошибка в обработке координат: {e}")
                await message.reply("⚠️ Неправильный формат координат. Используйте формат: широта,долгота (например: 55.75, 37.62)")
                return
        else:
            # Обычный запрос по названию города
            data = get_cached_weather(message.text)
            city = data["name"]
        cur_weather = round(data["main"]["temp"])

        feels_like_temp = round(data["main"]["feels_like"])

        temp_min = round(data["main"]["temp_min"])
        temp_max = round(data["main"]["temp_max"])

        weather_description = data["weather"][0]["main"]
        wd = code_to_smile.get(weather_description, "Посмотри в окно, не пойму что там за погода!")

        humidity = data["main"]["humidity"]
        pressure = round(data["main"]["pressure"] * 0.750062, 1)  # Конвертируем гПа в мм рт.ст.
        wind = round(data["wind"]["speed"])
        wind_dir = wind_direction(data["wind"]["deg"])  # Добавьте эту строку
        # Преобразуем timestamp в UTC время (без смещения)
        sunrise_timestamp = datetime.datetime.utcfromtimestamp(data["sys"]["sunrise"]).strftime('%Y-%m-%d %H:%M')
        sunset_timestamp = datetime.datetime.utcfromtimestamp(data["sys"]["sunset"]).strftime('%Y-%m-%d %H:%M')
        length_of_the_day = datetime.timedelta(seconds=data["sys"]["sunset"] - data["sys"]["sunrise"])

        await message.reply(
            f"***{get_current_time()}***\nПогода в городе: {city}\nТемпература: {cur_weather}C° {wd}\n"
            f"Ощущается как: {feels_like_temp}C°\n"
            f"Диапазон: от {temp_min}°C до {temp_max}°C\n"
            f"Влажность: {humidity}%\nДавление: {pressure} мм.рт.ст\nВетер: {wind} м/с, {wind_dir}\n"
            f"Восход солнца: {sunrise_timestamp}\nЗакат солнца: {sunset_timestamp}\nПродолжительность дня: {length_of_the_day}\n"
            f"***Хорошего дня!***",
            reply_markup=create_weather_keyboard(city)
        )

    except Exception as e:
        logging.error(f"Ошибка при запросе погоды: {e}")
        await message.reply("\U00002620 Проверьте название города \U00002620")

@dp.callback_query(lambda c: c.data.startswith('cloudiness:'))
async def handle_cloudiness_button(callback: types.CallbackQuery):
    """
    Обрабатывает нажатие кнопки "Облачность".
    """
    try:
        # Извлекаем город из callback_data
        city = callback.data.split(":", 1)[1]

        # Получаем данные с использованием кеша
        data = get_cached_weather(city)

        # Получаем облачность (в процентах)
        cloudiness = data["clouds"]["all"]

        # Форматируем ответ в зависимости от облачности
        if cloudiness <= 20:
            text = f"В {city} почти нет облаков: {cloudiness}% ☀️"
        elif cloudiness <= 50:
            text = f"В {city} немного облачно: {cloudiness}% ⛅"
        elif cloudiness <= 80:
            text = f"В {city} облачно: {cloudiness}% ☁️"
        else:
            text = f"В {city} пасмурно: {cloudiness}% 🌧️"

        # Показываем всплывающее окно с информацией
        await callback.answer(text, show_alert=True)

    except Exception as e:
        logging.error(f"Ошибка в обработчике облачности: {e}")
        await callback.answer("⚠️ Не удалось получить данные об облачности", show_alert=True)

    # Обязательно закрываем callback
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith('visibility:'))
async def handle_visibility_button(callback: types.CallbackQuery):
    """
    Обрабатывает нажатие кнопки "Видимость".
    """
    try:
        # Извлекаем город из callback_data
        city = callback.data.split(":", 1)[1]

        # Получаем данные с использованием кеша
        data = get_cached_weather(city)

        # Получаем видимость (в метрах по умолчанию)
        visibility_meters = data.get("visibility", 10000)  # 10000м = максимальная видимость в API

        # Конвертируем в километры
        visibility_km = visibility_meters / 1000

        # Форматируем ответ в зависимости от видимости
        if visibility_km >= 10:
            text = f"В {city} отличная видимость: {visibility_km:.1f} км 🌤️"
        elif visibility_km >= 5:
            text = f"В {city} хорошая видимость: {visibility_km:.1f} км ⛅"
        elif visibility_km >= 1:
            text = f"В {city} умеренная видимость: {visibility_km:.1f} км 🌫️"
        else:
            text = f"В {city} ограниченная видимость: {visibility_km:.1f} км 🚨"

        # Показываем всплывающее окно с информацией
        await callback.answer(text, show_alert=True)

    except Exception as e:
        logging.error(f"Ошибка в обработчике видимости: {e}")
        await callback.answer("⚠️ Не удалось получить данные о видимости", show_alert=True)

    # Обязательно закрываем callback
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith('coordinates:'))
async def handle_coordinates_button(callback: types.CallbackQuery):
    """
    Обрабатывает нажатие кнопки "Координаты".
    """
    try:
        # Извлекаем город из callback_data
        city = callback.data.split(":", 1)[1]

        # Получаем данные с использованием кеша
        data = get_cached_weather(city)

        # Получаем координаты
        lat = data["coord"]["lat"]
        lon = data["coord"]["lon"]

        # Форматируем ответ
        text = f"Координаты {city}:\nШирота: {lat}°\nДолгота: {lon}°\n\nВы можете использовать эти координаты для запроса погоды: {lat},{lon}"

        # Показываем всплывающее окно с информацией
        await callback.answer(text, show_alert=True)

    except Exception as e:
        logging.error(f"Ошибка в обработчике координат: {e}")
        await callback.answer("⚠️ Не удалось получить координаты", show_alert=True)

    # Обязательно закрываем callback
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith('summary:'))
async def handle_summary_button(callback: types.CallbackQuery):
    """
    Обрабатывает нажатие кнопки "Краткое резюме".
    """
    try:
        # Извлекаем город из callback_data
        city = callback.data.split(":", 1)[1]

        # Получаем данные с использованием кеша
        data = get_cached_weather(city)

        # Получаем основные данные
        cur_weather = round(data["main"]["temp"])
        weather_description = data["weather"][0]["main"]
        wd = code_to_smile.get(weather_description, "Погода")

        # Форматируем краткое резюме
        text = f"📝 Краткое резюме погоды в {city}:\n" \
               f"Температура: {cur_weather}°C {wd}\n" \
               f"Ощущается как: {round(data['main']['feels_like'])}°C\n" \
               f"Влажность: {data['main']['humidity']}%"

        # Показываем всплывающее окно с информацией
        await callback.answer(text, show_alert=True)

    except Exception as e:
        logging.error(f"Ошибка в обработчике резюме: {e}")
        await callback.answer("⚠️ Не удалось получить резюме погоды", show_alert=True)

    # Обязательно закрываем callback
    await callback.answer()

# Асинхронная функция для запуска бота
async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    # Настройка логирования
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    # Запуск асинхронного приложения
    asyncio.run(main())
