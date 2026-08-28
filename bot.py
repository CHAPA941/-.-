import asyncio
import logging
import os
import re
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_ID = int(os.getenv("GROUP_ID"))
PORT = int(os.getenv("PORT", 10000))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

user_topics = {}
blocked_users = set()

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
    """Извлекает тип общения и пол админа из текста (с # или без)."""
    text_lower = text.lower()
    # Убираем хэштеги для удобства
    words = re.findall(r'[а-яa-z]+', text_lower)

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

@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(WELCOME_TEXT)

@dp.message(F.chat.type == "private")
async def handle_user_message(message: Message):
    user_id = message.from_user.id

    if user_id in blocked_users:
        await message.answer("Вы заблокированы и не можете отправлять сообщения.")
        return

    # Если темы ещё нет, пытаемся создать из этого сообщения
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
                await bot.send_message(GROUP_ID, info, message_thread_id=topic_id)
                await message.answer(
                    "Готово! Твой запрос принят. Администратор скоро свяжется с тобой в этом чате. "
                    "Все сообщения, которые ты напишешь, будут переданы ему."
                )
            except Exception as e:
                logging.error(f"Не удалось создать тему: {e}")
                await message.answer("Произошла ошибка. Попробуй позже или обратись к администратору напрямую.")
        else:
            await message.answer(
                "Пожалуйста, укажи в сообщении и категорию, и пол админа.\n"
                "Например: «привет поддержка мальчик» или «общение девочка».\n"
                "Можно и с хэштегами: #поддержка #мальчик"
            )
        return

    # Если тема уже есть — пересылаем сообщение в неё
    topic_id = user_topics[user_id]
    text = f"💬 Сообщение от пользователя:\n{message.text}"
    await bot.send_message(GROUP_ID, text, message_thread_id=topic_id)

@dp.message(F.chat.id == GROUP_ID, F.message_thread_id.is_not(None))
async def handle_admin_message(message: Message):
    if message.from_user.is_bot or message.is_topic_message is False:
        return
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

@dp.message(Command("block"), F.chat.id == GROUP_ID)
async def block_user(message: Message):
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
async def unblock_user(message: Message):
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

async def main():
    logging.basicConfig(level=logging.INFO)
    # Удаляем вебхук, если он был установлен ранее
    await bot.delete_webhook(drop_pending_updates=True)

    # Запускаем поллинг в фоне
    polling_task = asyncio.create_task(dp.start_polling(bot))

    # Веб-сервер для Render (чтобы не ругался на порт)
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
