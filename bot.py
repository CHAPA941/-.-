import asyncio
import logging
import os
import re
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.storage.memory import MemoryStorage

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_ID = int(os.getenv("GROUP_ID"))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Хранилища
user_topics = {}   # user_id -> topic_id
blocked_users = set()

# Приветственное сообщение
WELCOME_TEXT = (
    "Привет солнце🥰\n\n"
    "чтобы получить администратора нужно указать категорию, "
    "а так же пол админа который(ая) вас интересует:\n\n"
    "#поддержка\n"
    "#общение\n"
    "#мальчик\n"
    "#девочка\n\n"
    "⌁ например:\n"
    "— «привет #общение #девушка/мальчик»\n"
    "— «мне нужна #поддержка #мальчик/девушка»\n\n"
    "⌁ если вы хотите попасть к конкретному хранителю, напишите:\n"
    "«позовите #тег»"
)

def extract_tags(text: str):
    """Извлекает хэштеги из текста (слова, начинающиеся с #)."""
    tags = re.findall(r'#(\w+)', text.lower())
    return tags

@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(WELCOME_TEXT)

@dp.message(F.chat.type == "private")
async def handle_user_message(message: Message):
    user_id = message.from_user.id

    if user_id in blocked_users:
        await message.answer("Вы заблокированы и не можете отправлять сообщения.")
        return

    # Если темы ещё нет — пробуем создать на основе первого сообщения с тегами
    if user_id not in user_topics:
        text = message.text or ""
        tags = extract_tags(text)

        # Определяем тип общения
        type_comm = None
        if "#поддержка" in tags:
            type_comm = "Поддержка"
        elif "#общение" in tags:
            type_comm = "Общение"

        # Определяем пол админа
        admin_gender = None
        if "#мальчик" in tags:
            admin_gender = "Мальчик"
        elif "#девочка" in tags or "#девушка" in tags:
            admin_gender = "Девочка"

        if type_comm and admin_gender:
            username = message.from_user.username or f"id{user_id}"
            try:
                # Создаём тему в группе
                topic = await bot.create_forum_topic(
                    chat_id=GROUP_ID,
                    name=f"{username}",
                )
                topic_id = topic.message_thread_id
                user_topics[user_id] = topic_id

                # Отправляем карточку запроса в тему
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
            # Если не хватает тегов — напоминаем инструкцию
            await message.answer(
                "Пожалуйста, укажи в сообщении:\n"
                "— тип: #поддержка или #общение\n"
                "— пол админа: #мальчик или #девочка\n\n"
                "Например: «привет #общение #мальчик»"
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
        return  # внутренняя заметка, не отправляем пользователю
    else:
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
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())