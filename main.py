import os
import random
import time
from aiogram import Bot, Dispatcher, F, types
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from supabase import create_client, Client

# --- БЕЗОПАСНАЯ КОНФИГУРАЦИЯ (ЧЕРЕЗ ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ) ---
TOKEN = os.getenv("BOT_TOKEN")
UZS_PROVIDER_TOKEN = os.getenv("UZS_PAYMENT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Проверка на наличие всех ключей на сервере
if not all([TOKEN, UZS_PROVIDER_TOKEN, SUPABASE_URL, SUPABASE_KEY]):
    raise ValueError("КРИТИЧЕСКАЯ ОШИБКА: Забыли указать переменные окружения на хостинге!")

# Используем проверенный публичный прокси-зеркало для обхода блокировки файрвола
session = AiohttpSession(api=TelegramAPIServer.from_baseurl("https://chatlabs.space"))
bot = Bot(token=TOKEN, session=session)
dp = Dispatcher()

# Инициализируем клиент облачной базы данных
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

COOLDOWN_SECONDS = 60  # Ограничение на бесплатный тап (раз в минуту)


# --- ФУНКЦИИ РАБОТЫ С SUPABASE ---

def get_player(user_id: int):
    """Ищет игрока в облаке. Возвращает dict или None"""
    response = supabase.table("players").select("*").eq("user_id", user_id).execute()
    return response.data[0] if response.data else None


def create_player(user_id: int, name: str, p_class: str):
    """Создает новую запись в облаке"""
    data = {
        "user_id": user_id,
        "name": name,
        "class": p_class,
        "power": 10,
        "last_tap": 0
    }
    supabase.table("players").insert(data).execute()


def update_player_power(user_id: int, new_power: int, update_tap: bool = False):
    """Обновляет силу игрока и время тапа (если нужно)"""
    update_data = {"power": new_power}
    if update_tap:
        update_data["last_tap"] = int(time.time())

    supabase.table("players").update(update_data).eq("user_id", user_id).execute()


def get_top_players():
    """Берет ТОП-5 игроков, отсортированных по силе"""
    response = supabase.table("players").select("*").order("power", desc=True).limit(5).execute()
    return response.data


# --- ГЛАВНОЕ МЕНЮ И ЛОГИКА БОТА ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    builder = InlineKeyboardBuilder()
    builder.button(text="🎭 Создать Аватара", callback_data="menu_create")
    builder.button(text="🔋 Личный кабинет / Прокачка", callback_data="menu_profile")
    builder.button(text="💎 Магазин Бустов", callback_data="menu_shop")
    builder.button(text="🏆 Топ игроков", callback_data="menu_top")
    builder.adjust(1)

    await message.answer(
        "⚖️ **Нейро-Арена «МАНИПУЛЯТОР» на облаке Supabase!**\n\n"
        "Прокачивай Аватара, участвуй в батлах и доминируй. Данные игроков теперь никогда не сотрутся!\n"
        "Чтобы вызвать кого-то на батл в чате, ответь на его сообщение командой `/battle`!",
        reply_markup=builder.as_markup()
    )


@dp.callback_query(F.data == "menu_profile")
async def inline_profile(callback: types.CallbackQuery):
    p = get_player(callback.from_user.id)
    if not p:
        await callback.answer("❌ Сначала создай Аватара в главном меню!", show_alert=True)
        return

    builder = InlineKeyboardBuilder()
    builder.button(text="⚡ Качать Силу бесплатно", callback_data="action_tap")
    builder.button(text="⬅️ В меню", callback_data="menu_back")
    builder.adjust(1)

    await callback.message.edit_text(
        f"👤 **Аватар:** {p['name']} ({p['class']})\n"
        f"📊 **Сила:** {p['power']} ⚡\n"
        f"⏱ _Бесплатный тап доступен раз в минуту._",
        reply_markup=builder.as_markup()
    )


@dp.callback_query(F.data == "action_tap")
async def action_tap(callback: types.CallbackQuery):
    p = get_player(callback.from_user.id)
    current_time = int(time.time())

    last_tap = p.get("last_tap", 0)
    time_passed = current_time - last_tap

    if time_passed < COOLDOWN_SECONDS:
        time_left = COOLDOWN_SECONDS - time_passed
        await callback.answer(f"⏳ Подожди еще {time_left} сек. Или зайди в Магазин за мгновенным бустом!",
                              show_alert=True)
        return

    new_power = p['power'] + 5
    update_player_power(callback.from_user.id, new_power, update_tap=True)

    await callback.answer("🔥 +5 Силы успешно накачано!")
    await inline_profile(callback)


@dp.message(Command("battle"))
async def cmd_battle(message: types.Message):
    if not message.reply_to_message:
        await message.answer("⚔️ Чтобы начать батл, ответь этой командой на сообщение соперника!")
        return

    p1 = get_player(message.from_user.id)
    p2 = get_player(message.reply_to_message.from_user.id)

    if not p1 or not p2:
        await message.answer("❌ У обоих участников должны быть созданы Аватары! Напишите мне в ЛС.")
        return

    total_power = p1['power'] + p2['power']
    if random.randint(1, total_power) <= p1['power']:
        winner, loser = p1, p2
    else:
        winner, loser = p2, p1

    update_player_power(winner['user_id'], winner['power'] + 10)

    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ В меню", callback_data="menu_back")

    await message.answer(
        f"⚔️ **МЕНТАЛЬНЫЙ БАТЛ В ЧАТЕ** ⚔️\n\n"
        f"🎭 **{winner['name']}** ({winner['class']}) полностью переспорил и растоптал аргументами **{loser['name']}** ({loser['class']})!\n\n"
        f"🏆 Победитель забирает **+10 Силы** себе в профиль!",
        reply_markup=builder.as_markup()
    )


@dp.callback_query(F.data == "menu_shop")
async def inline_shop(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.button(text="⭐ +100 Силы за 50 Звезд", callback_data="buy_stars_100")
    builder.button(text="🇺🇿 +500 Силы за 20 000 Сум", callback_data="buy_uzs_500")
    builder.button(text="⬅️ Назад", callback_data="menu_back")
    builder.adjust(1)

    await callback.message.edit_text(
        "💎 **ДОНАТ-МАГАЗИН** 💎\n\n"
        "Выбери буст, чтобы мгновенно оторваться от соперников:",
        reply_markup=builder.as_markup()
    )


@dp.callback_query(F.data == "buy_stars_100")
async def buy_stars(callback: types.CallbackQuery):
    await callback.message.answer_invoice(
        title="⚡ Мега-Буст (+100 Силы)",
        description="Покупка силы за Telegram Stars.",
        payload="stars_boost_100",
        currency="XTR",
        prices=[types.LabeledPrice(label="Буст", amount=50)],
        provider_token=""
    )
    await callback.answer()


@dp.callback_query(F.data == "buy_uzs_500")
async def buy_uzs(callback: types.CallbackQuery):
    await callback.message.answer_invoice(
        title="🔥 Ультра-Пак (+500 Силы)",
        description="Покупка силы через платежные системы Узбекистана.",
        payload="uzs_boost_500",
        currency="UZS",
        prices=[types.LabeledPrice(label="Ультра Буст", amount=2000000)],
        provider_token=UZS_PROVIDER_TOKEN
    )
    await callback.answer()


@dp.pre_checkout_query()
async def pre_checkout_handler(pre_checkout_query: types.PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)


@dp.message(F.successful_payment)
async def success_payment_handler(message: types.Message):
    payload = message.successful_payment.invoice_payload
    p = get_player(message.from_user.id)

    if not p:
        await message.answer("⚠️ Оплата успешна, но Аватар не найден.")
        return

    if payload == "stars_boost_100":
        update_player_power(message.from_user.id, p['power'] + 100)
        await message.answer("🎉 Начислено +100 к Силе за Звезды! ⭐")
    elif payload == "uzs_boost_500":
        update_player_power(message.from_user.id, p['power'] + 500)
        await message.answer("🇺🇿 **Оплата принята!** Начислено +500 к Силе через Click/Payme!")


@dp.callback_query(F.data == "menu_top")
async def inline_top(callback: types.CallbackQuery):
    sorted_players = get_top_players()

    top_text = "🏆 **ТОП-5 ЛУЧШИХ МАНИПУЛЯТОРОВ:**\n\n"
    for i, p in enumerate(sorted_players, start=1):
        top_text += f"{i}. {p['name']} — {p['power']} ⚡ ({p['class']})\n"

    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Назад", callback_data="menu_back")

    await callback.message.edit_text(top_text, reply_markup=builder.as_markup())


@dp.callback_query(F.data == "menu_back")
async def menu_back(callback: types.CallbackQuery):
    await callback.message.delete()
    await cmd_start(callback.message)


@dp.callback_query(F.data == "menu_create")
async def inline_create(callback: types.CallbackQuery):
    if get_player(callback.from_user.id):
        await callback.answer("У тебя уже есть Аватар!", show_alert=True)
        return
    classes = ["Токсик", "Душнила", "Гигачад", "Инфоцыган"]
    p_class = random.choice(classes)
    create_player(callback.from_user.id, callback.from_user.first_name, p_class)
    await callback.answer(f"🎉 Создан Аватар класса {p_class}!")
    await inline_profile(callback)


if __name__ == "__main__":
    dp.run_polling(bot)

