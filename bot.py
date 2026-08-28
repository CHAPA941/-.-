import asyncio
import logging
import os
import re
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_ID = int(os.getenv("GROUP_ID"))
PORT = int(os.getenv("PORT", 10000))
OWNER_IDS = set(map(int, (os.getenv("OWNER_IDS", "") or "").split(",") if os.getenv("OWNER_IDS") else []))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

user_topics = {}   # user_id -> topic_id
blocked_users = set()
admins = set()
owners = OWNER_IDS

WELCOME_TEXT = (
    "Привет солнце🥰\n\n"
    "чтобы получить администратора нужно указать категорию, "
    "а так же пол админа который(ая) вас интересует:\n\n"
    "— категория: поддержка или общение\n"
    "— пол админа: мальчик или девочка\n\n"
    "Например:\n"
    "«привет поддержка мальчик»\n"
    "«мне нужна поддержка девочка»\n\n"
    "Если хочешь конкретного хранителя, напиши его тег (например, #ангел)\n"
    "Просто напиши сообщение, и я передам его админам."
)

def parse_request(text: str):
    text_lower = text.lower()
    type_comm = None
    if 'поддержка' in text_lower or '#поддержка' in text_lower:
        type_comm = 'Поддержка'
    elif 'общение' in text_lower or '#общение' in text_lower:
        type_comm = 'Общение'

    admin_gender = None
    if 'мальчик' in text_lower or '#мальчик' in text_lower:
        admin_gender = 'Мальчик'
    elif 'девочка' in text_lower or '#девочка' in text_lower or 'девушка' in text_lower or '#девушка' in text_lower:
        admin_gender = 'Девочка'

    return type_comm, admin_gender

def get_keyboard(user_id: int) -> InlineKeyboardMarkup:
    if user_id in blocked_users:
        buttons = [[InlineKeyboardButton(text="🔓 Разблокировать", callback_data=f"unblock:{user_id}")]]
    else:
        buttons = [[
            InlineKeyboardButton(text="🔒 Заблокировать", callback_data=f"block:{user_id}"),
            InlineKeyboardButton(text="✅ Прочитать", callback_data=f"read:{user_id}")
        ]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_confirm_keyboard(user_id: int) -> InlineKeyboardMarkup:
    buttons = [[
        InlineKeyboardButton(text="✅ Да, разблокировать", callback_data=f"confirm_unblock:{user_id}"),
        InlineKeyboardButton(text="❌ Нет", callback_data=f"cancel_unblock:{user_id}")
    ]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def is_owner(user_id: int) -> bool:
    return user_id in owners

def is_admin(user_id: int) -> bool:
    return user_id in admins or is_owner(user_id)

# ---------- Команды ----------
@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(WELCOME_TEXT)

@dp.message(Command("help"), F.chat.id == GROUP_ID)
async def cmd_help(message: Message):
    help_text = (
        "📋 Команды для админов:\n"
        "/help - эта справка\n"
        "/stats - статистика бота\n"
        "/id - узнать user_id текущей темы\n"
        "/close - удалить текущую тему (закрыть диалог) [только владелец]\n"
        "/block - заблокировать пользователя (текстовая команда)\n"
        "/unblock - разблокировать пользователя (текстовая команда)\n"
        "/myrank - узнать свой ранг\n\n"
        "Команды для владельца:\n"
        "/setrank <user_id> <admin|owner> - назначить ранг\n"
        "/removerank <user_id> - снять ранг\n"
        "/liststaff - показать всех владельцев и админов\n"
        "/clear - сбросить все данные (осторожно!)\n\n"
        "Сообщения без // пересылаются пользователю.\n"
        "Сообщения с // остаются в теме как заметки."
    )
    await message.answer(help_text)

@dp.message(Command("myrank"))
async def cmd_myrank(message: Message):
    user_id = message.from_user.id
    if is_owner(user_id):
        rank = "👑 Владелец"
    elif is_admin(user_id):
        rank = "🛡️ Админ"
    else:
        rank = "👤 Пользователь"
    await message.answer(f"Ваш ранг: {rank}")

@dp.message(Command("stats"), F.chat.id == GROUP_ID)
async def cmd_stats(message: Message):
    active_topics = len(user_topics)
    blocked = len(blocked_users)
    await message.answer(f"📊 Активных диалогов: {active_topics}\n🔒 Заблокировано пользователей: {blocked}")

@dp.message(Command("id"), F.chat.id == GROUP_ID)
async def cmd_id(message: Message):
    topic_id = message.message_thread_id
    user_id = None
    for uid, tid in user_topics.items():
        if tid == topic_id:
            user_id = uid
            break
    if user_id:
        await message.answer(f"ID пользователя: {user_id}")
    else:
        await message.answer("Не удалось определить пользователя.")

@dp.message(Command("close"), F.chat.id == GROUP_ID)
async def cmd_close(message: Message):
    if not is_owner(message.from_user.id):
        await message.answer("⛔ Недостаточно прав. Команда доступна только владельцу.")
        return
    topic_id = message.message_thread_id
    user_id = None
    for uid, tid in user_topics.items():
        if tid == topic_id:
            user_id = uid
            break
    if user_id:
        try:
            await bot.delete_forum_topic(chat_id=GROUP_ID, message_thread_id=topic_id)
            user_topics.pop(user_id, None)
            await message.answer("Тема удалена.")
        except Exception as e:
            logging.error(f"Ошибка удаления темы: {e}")
            await message.answer("Не удалось удалить тему.")
    else:
        await message.answer("Эта тема не связана с пользователем.")

@dp.message(Command("clear"), F.chat.id == GROUP_ID)
async def cmd_clear(message: Message):
    if not is_owner(message.from_user.id):
        await message.answer("⛔ Недостаточно прав. Команда доступна только владельцу.")
        return
    user_topics.clear()
    blocked_users.clear()
    await message.answer("Все данные сброшены.")

@dp.message(Command("setrank"), F.chat.id == GROUP_ID)
async def cmd_setrank(message: Message):
    if not is_owner(message.from_user.id):
        await message.answer("⛔ Недостаточно прав. Команда доступна только владельцу.")
        return
    args = message.text.split()
    if len(args) != 3:
        await message.answer("Формат: /setrank <user_id> <admin|owner>")
        return
    try:
        target_id = int(args[1])
        rank = args[2].lower()
    except:
        await message.answer("Неверный user_id.")
        return
    if rank == "admin":
        admins.add(target_id)
        await message.answer(f"Пользователь {target_id} назначен админом.")
    elif rank == "owner":
        owners.add(target_id)
        await message.answer(f"Пользователь {target_id} назначен владельцем.")
    else:
        await message.answer("Ранг может быть только admin или owner.")

@dp.message(Command("removerank"), F.chat.id == GROUP_ID)
async def cmd_removerank(message: Message):
    if not is_owner(message.from_user.id):
        await message.answer("⛔ Недостаточно прав. Команда доступна только владельцу.")
        return
    args = message.text.split()
    if len(args) != 2:
        await message.answer("Формат: /removerank <user_id>")
        return
    try:
        target_id = int(args[1])
    except:
        await message.answer("Неверный user_id.")
        return
    admins.discard(target_id)
    owners.discard(target_id)
    await message.answer(f"Ранг пользователя {target_id} снят.")

@dp.message(Command("liststaff"), F.chat.id == GROUP_ID)
async def cmd_liststaff(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Недостаточно прав.")
        return
    owners_list = ", ".join(map(str, owners)) if owners else "нет"
    admins_list = ", ".join(map(str, admins)) if admins else "нет"
    await message.answer(f"👑 Владельцы: {owners_list}\n🛡️ Админы: {admins_list}")

# Текстовые команды блокировки/разблокировки
@dp.message(Command("block"), F.chat.id == GROUP_ID)
async def block_user_cmd(message: Message):
    topic_id = message.message_thread_id
    user_id = None
    for uid, tid in user_topics.items():
        if tid == topic_id:
            user_id = uid
            break
    if user_id:
        blocked_users.add(user_id)
        await message.answer(f"Пользователь {user_id} заблокирован.")
    else:
        await message.answer("Не удалось определить пользователя.")

@dp.message(Command("unblock"), F.chat.id == GROUP_ID)
async def unblock_user_cmd(message: Message):
    topic_id = message.message_thread_id
    user_id = None
    for uid, tid in user_topics.items():
        if tid == topic_id:
            user_id = uid
            break
    if user_id:
        blocked_users.discard(user_id)
        await message.answer(f"Пользователь {user_id} разблокирован.")
    else:
        await message.answer("Не удалось определить пользователя.")

# Обработка личных сообщений
@dp.message(F.chat.type == "private")
async def handle_user_message(message: Message):
    user_id = message.from_user.id

    if user_id in blocked_users:
        await message.answer("Вы заблокированы и не можете отправлять сообщения.")
        return

    if user_id not in user_topics:
        text = message.text or ""
        type_comm, admin_gender = parse_request(text)
        if type_comm and admin_gender:
            username = message.from_user.username or f"id{user_id}"
            try:
                topic = await bot.create_forum_topic(chat_id=GROUP_ID, name=f"{username}")
                topic_id = topic.message_thread_id
                user_topics[user_id] = topic_id

                info = (
                    f"🆕 Новый запрос!\n"
                    f"👤 Имя: {message.from_user.full_name}\n"
                    f"🔖 Username: @{message.from_user.username or 'нет'}\n"
                    f"📌 Тип: {type_comm}\n"
                    f"🚻 Предпочтительный пол админа: {admin_gender}\n\n"
                    f"Начинайте общение. Сообщения без // будут отправлены пользователю."
                )
                await bot.send_message(GROUP_ID, info, message_thread_id=topic_id, reply_markup=get_keyboard(user_id))
                await message.answer("Готово! Твой запрос принят. Администратор скоро свяжется с тобой в этом чате. Все сообщения, которые ты напишешь, будут переданы ему.")
            except Exception as e:
                logging.error(f"Не удалось создать тему: {e}")
                await message.answer("Произошла ошибка. Попробуй позже или обратись к администратору напрямую.")
        else:
            await message.answer("Пожалуйста, укажи в сообщении и категорию, и пол админа.\nНапример: «привет поддержка мальчик» или «общение девочка».\nМожно и с хэштегами: #поддержка #мальчик")
        return

    topic_id = user_topics[user_id]
    text = f"💬 Сообщение от пользователя:\n{message.text}"
    await bot.send_message(GROUP_ID, text, message_thread_id=topic_id)

# Обработка сообщений из тем (админы)
@dp.message(F.chat.id == GROUP_ID, F.message_thread_id.is_not(None))
async def handle_admin_message(message: Message):
    if message.from_user.is_bot or message.is_topic_message is False:
        return
    if message.text and message.text.startswith('/'):
        return  # команды уже обработаны выше, не пересылаем
    topic_id = message.message_thread_id
    user_id = None
    for uid, tid in user_topics.items():
        if tid == topic_id:
            user_id = uid
            break
    if user_id is None:
        return
    text = message.text or ""
    if text.startswith("//"):
        return
    try:
        await bot.send_message(user_id, text)
    except Exception as e:
        logging.error(f"Не удалось отправить сообщение пользователю {user_id}: {e}")

# Обработка callback-кнопок
@dp.callback_query(F.data.startswith("block:"))
async def process_block_button(callback: CallbackQuery):
    user_id = int(callback.data.split(":")[1])
    if user_id not in blocked_users:
        blocked_users.add(user_id)
        try:
            await bot.send_message(user_id, "Вы были заблокированы.")
        except:
            pass
        await callback.message.edit_text(callback.message.text + "\n\n🔒 Заблокирован", reply_markup=get_keyboard(user_id))
        await callback.answer("Пользователь заблокирован")
    else:
        await callback.answer("Пользователь уже заблокирован")

@dp.callback_query(F.data.startswith("unblock:"))
async def process_unblock_button(callback: CallbackQuery):
    user_id = int(callback.data.split(":")[1])
    await callback.message.edit_text(callback.message.text + "\n\n❓ Вы точно хотите разблокировать?", reply_markup=get_confirm_keyboard(user_id))
    await callback.answer()

@dp.callback_query(F.data.startswith("confirm_unblock:"))
async def process_confirm_unblock(callback: CallbackQuery):
    user_id = int(callback.data.split(":")[1])
    if user_id in blocked_users:
        blocked_users.discard(user_id)
        try:
            await bot.send_message(user_id, "Вы были разблокированы.")
        except:
            pass
        lines = callback.message.text.split('\n')
        while lines and lines[-1].startswith(('🔒', '❓')):
            lines.pop()
        clean_text = '\n'.join(lines)
        await callback.message.edit_text(clean_text, reply_markup=get_keyboard(user_id))
        await callback.answer("Пользователь разблокирован")
    else:
        await callback.answer("Пользователь не заблокирован")

@dp.callback_query(F.data.startswith("cancel_unblock:"))
async def process_cancel_unblock(callback: CallbackQuery):
    user_id = int(callback.data.split(":")[1])
    lines = callback.message.text.split('\n')
    if lines and lines[-1].startswith('❓'):
        lines.pop()
    clean_text = '\n'.join(lines)
    await callback.message.edit_text(clean_text, reply_markup=get_keyboard(user_id))
    await callback.answer()

@dp.callback_query(F.data.startswith("read:"))
async def process_read_button(callback: CallbackQuery):
    user_id = int(callback.data.split(":")[1])
    try:
        await bot.send_message(user_id, "Ваш запрос прочитан, скоро с вами свяжутся.")
    except:
        pass
    await callback.answer("Запрос отмечен как прочитанный")
    try:
        await callback.message.edit_text(callback.message.text + "\n\n✅ Прочитано", reply_markup=None)
    except:
        pass

async def main():
    logging.basicConfig(level=logging.INFO)
    await bot.delete_webhook(drop_pending_updates=True)

    polling_task = asyncio.create_task(dp.start_polling(bot))

    app = web.Application()
    app.router.add_get('/', lambda request: web.Response(text="Bot is running"))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logging.info(f"Web server started on port {PORT}")

    await polling_task

if __name__ == "__main__":
    asyncio.run(main())
