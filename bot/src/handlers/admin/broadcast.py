from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InputMediaPhoto, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from fluent.runtime import FluentLocalization
import logging
from datetime import datetime
import json

from src.states.broadcast import BroadcastStates
from src.database.db_manager import DatabaseManager
from src.utils.config import settings
from src.utils.logger import get_logger

router = Router()
logger = get_logger(__name__)

class BroadcastManager:
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        
        # Определяем сегменты для рассылки
        self.segments = {
            "all": {"name": "👥 Все пользователи", "filter": {}},
            "male": {"name": "👨 Мужчины", "filter": {"sex": "male"}},
            "female": {"name": "👩 Женщины", "filter": {"sex": "female"}},
            "students": {"name": "🎓 Студенты", "filter": {"major": "student"}},
            "entrepreneurs": {"name": "💼 Предприниматели", "filter": {"major": "entrepreneur"}},
            "employees": {"name": "💻 Работающие по найму", "filter": {"major": "hire"}},
            "freelancers": {"name": "🚀 Фрилансеры", "filter": {"major": "frilans"}}
        }
        
        # Типы контента для рассылки
        self.content_types = {
            "text": {"name": "📝 Только текст", "icon": "📝"},
            "image": {"name": "🖼️ Картинка + текст", "icon": "🖼️"}
        }
    
    async def get_segment_users_count(self, segment_key: str) -> int:
        """Получение количества пользователей в сегменте"""
        try:
            if segment_key == "all":
                stats = await self.db_manager.get_general_stats()
                return stats.get('total_users', 0)
            elif segment_key in ["male", "female"]:
                segments = await self.db_manager.get_target_segments()
                return segments.get(f'{segment_key}_count', 0)
            elif segment_key in ["students", "entrepreneurs", "employees", "freelancers"]:
                segment_map = {
                    "students": "students_count",
                    "entrepreneurs": "entrepreneurs_count", 
                    "employees": "employees_count",
                    "freelancers": "freelancers_count"
                }
                segments = await self.db_manager.get_target_segments()
                return segments.get(segment_map[segment_key], 0)
            else:
                # Для сложных сегментов пока возвращаем примерное количество
                stats = await self.db_manager.get_general_stats()
                return max(1, stats.get('total_users', 0) // 10)
        except Exception as e:
            logger.error(f"❌ Error getting segment count: {e}")
            return 0
    
    async def send_broadcast_message(self, bot: Bot, user_id: int, message_type: str, 
                                text: str, image_file_id: str = None) -> bool:
        """Отправка сообщения пользователю в зависимости от типа"""
        try:
            if message_type == "text":
                await bot.send_message(
                    chat_id=user_id,
                    text=text,
                    parse_mode="HTML"
                )
                return True
                
            elif message_type == "image":
                if not image_file_id:
                    logger.error(f"❌ No image_file_id for image broadcast to {user_id}")
                    # Fallback to text only
                    await bot.send_message(
                        chat_id=user_id,
                        text=text,
                        parse_mode="HTML"
                    )
                    return True
                
                try:
                    # Ограничиваем длину подписи для фото
                    caption = text[:1024] if len(text) > 1024 else text
                    await bot.send_photo(
                        chat_id=user_id,
                        photo=image_file_id,
                        caption=caption,
                        parse_mode="HTML"
                    )
                    return True
                except Exception as photo_error:
                    logger.error(f"❌ Failed to send photo to {user_id}: {photo_error}")
                    # Fallback to text only
                    await bot.send_message(
                        chat_id=user_id,
                        text=f"🖼️ {text}",  # Добавляем эмодзи чтобы показать, что должно было быть изображение
                        parse_mode="HTML"
                    )
                    return True
                    
            else:
                # Fallback для неизвестного типа
                await bot.send_message(
                    chat_id=user_id,
                    text=text,
                    parse_mode="HTML"
                )
                return True
                
        except Exception as e:
            logger.error(f"❌ Failed to send broadcast to {user_id}: {e}")
            return False

@router.message(F.text == "📢 Сделать рассылку подписчикам")
async def start_broadcast(message: Message, state: FSMContext, l10n: FluentLocalization, db_manager: DatabaseManager):
    """Начало процесса создания рассылки"""
    if not await db_manager.is_admin(message.from_user.id):
        await message.answer("❌ Эта команда доступна только администраторам.")
        return
    
    try:
        # Гарантируем, что пользователь существует в базе
        await db_manager.ensure_user_exists(
            user_id=message.from_user.id,
            username=message.from_user.username,
            full_name=message.from_user.full_name
        )
        
        broadcast_manager = BroadcastManager(db_manager)
        
        # Создаем клавиатуру для выбора сегмента
        builder = InlineKeyboardBuilder()
        
        for segment_key, segment_info in broadcast_manager.segments.items():
            users_count = await broadcast_manager.get_segment_users_count(segment_key)
            builder.button(
                text=f"{segment_info['name']} ({users_count})",
                callback_data=f"broadcast_segment_{segment_key}"
            )
        
        builder.button(text="❌ Отмена", callback_data="broadcast_cancel")
        builder.adjust(1)
        
        await message.answer(
            "📤 <b>СОЗДАНИЕ РАССЫЛКИ</b>\n\n"
            "👥 <b>Выберите аудиторию для рассылки:</b>",
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )
        
        await state.set_state(BroadcastStates.choosing_segment)
        await db_manager.add_user_action(
            user_id=message.from_user.id,
            action_type='broadcast_started'
        )
        
    except Exception as e:
        logger.error(f"❌ Error starting broadcast: {e}")
        await message.answer("❌ Ошибка при запуске рассылки")
        await state.clear()

@router.callback_query(BroadcastStates.choosing_segment, F.data.startswith("broadcast_segment_"))
async def choose_broadcast_segment(callback: CallbackQuery, state: FSMContext, db_manager: DatabaseManager):
    """Обработка выбора сегмента для рассылки"""
    try:
        segment_key = callback.data.split("_")[2]
        broadcast_manager = BroadcastManager(db_manager)
        
        if segment_key not in broadcast_manager.segments:
            await callback.answer("❌ Неверный сегмент")
            return
        
        segment_info = broadcast_manager.segments[segment_key]
        users_count = await broadcast_manager.get_segment_users_count(segment_key)
        
        await state.update_data(
            segment_key=segment_key,
            segment_name=segment_info["name"],
            users_count=users_count
        )
        
        # Создаем клавиатуру для выбора типа контента
        builder = InlineKeyboardBuilder()
        
        for content_key, content_info in broadcast_manager.content_types.items():
            builder.button(
                text=f"{content_info['icon']} {content_info['name']}",
                callback_data=f"broadcast_type_{content_key}"
            )
        
        builder.button(text="🔙 Назад", callback_data="broadcast_back_to_segments")
        builder.adjust(1)
        
        await callback.message.edit_text(
            f"✅ <b>Выбран сегмент:</b> {segment_info['name']}\n"
            f"👥 <b>Количество пользователей:</b> {users_count}\n\n"
            "🎨 <b>Выберите тип контента:</b>",
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )
        
        await state.set_state(BroadcastStates.choosing_type)
        await callback.answer()
        
    except Exception as e:
        logger.error(f"❌ Error choosing broadcast segment: {e}")
        await callback.answer("❌ Ошибка при выборе сегмента")

@router.callback_query(BroadcastStates.choosing_type, F.data.startswith("broadcast_type_"))
async def choose_broadcast_type(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора типа контента"""
    try:
        content_type = callback.data.split('_')[2]

        
        
        await state.update_data(content_type=content_type)
        
        if content_type == "text":
            await callback.message.edit_text(
                "📝 <b>Введите текст рассылки:</b>\n\n"
                "💡 <i>Поддерживается HTML-разметка</i>\n"
                "• <b>жирный текст</b>\n" 
                "• <i>курсив</i>\n"
                "• <code>моноширинный</code>\n\n"
                "❌ Для отмены введите /cancel",
                parse_mode="HTML"
            )
            await state.set_state(BroadcastStates.entering_text)
        elif content_type == "image":
            await callback.message.edit_text(
                "🖼️ <b>Отправьте изображение для рассылки:</b>\n\n"
                "💡 <i>Отправьте картинку как фото (не файлом)</i>\n\n"
                "❌ Для отмены введите /cancel",
                parse_mode="HTML"
            )
            await state.set_state(BroadcastStates.entering_image)
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"❌ Error choosing broadcast type: {e}")
        await callback.answer("❌ Ошибка при выборе типа")

@router.message(BroadcastStates.entering_image, F.photo)
async def process_broadcast_image(message: Message, state: FSMContext, bot: Bot):
    """Обработка загруженного изображения"""
    try:
        # Сохраняем file_id изображения (берем самое высокое качество)
        image_file_id = message.photo[-1].file_id
        
        # Проверяем, что file_id валидный
        try:
            # Пробуем получить информацию о файле
            file_info = await bot.get_file(image_file_id)
            logger.info(f"✅ Image file validated: {file_info.file_id}, size: {file_info.file_size}")
        except Exception as file_error:
            logger.error(f"❌ Invalid image file_id: {file_error}")
            await message.answer("❌ Ошибка: неверный формат изображения. Попробуйте отправить другое изображение.")
            return
        
        # Сохраняем в состояние
        await state.update_data(image_file_id=image_file_id)
        
        # Показываем предпросмотр и запрашиваем текст
        await message.answer_photo(
            photo=image_file_id,
            caption="✅ <b>Изображение получено!</b>\n\n"
                   "📝 Теперь введите текст для рассылки:\n\n"
                   "💡 <i>Этот текст будет подписью к изображению</i>\n"
                   "⚠️ <i>Ограничение: 1024 символа</i>",
            parse_mode="HTML"
        )
        
        await state.set_state(BroadcastStates.entering_text)
        
    except Exception as e:
        logger.error(f"❌ Error processing broadcast image: {e}")
        await message.answer("❌ Ошибка при обработке изображения. Попробуйте отправить другое изображение.")

@router.message(BroadcastStates.entering_image)
async def wrong_image_input(message: Message):
    """Неправильный ввод для изображения"""
    await message.answer("❌ Пожалуйста, отправьте изображение как фото (не файлом)")

@router.message(BroadcastStates.entering_text, F.text)
async def process_broadcast_text(message: Message, state: FSMContext, bot: Bot, db_manager: DatabaseManager):
    """Обработка текста рассылки и показ предпросмотра"""
    try:
        text = message.text
        
        if text.startswith('/cancel'):
            await message.answer("❌ Рассылка отменена")
            await state.clear()
            return
        
        # Проверяем длину текста для изображений
        data = await state.get_data()
        content_type = data.get('content_type', 'text')
        
        if content_type == "image" and len(text) > 1024:
            await message.answer(
                f"❌ <b>Слишком длинный текст!</b>\n\n"
                f"Для изображений максимальная длина подписи: 1024 символа\n"
                f"Ваш текст: {len(text)} символов\n\n"
                f"Сократите текст и отправьте снова:",
                parse_mode="HTML"
            )
            return
        
        await state.update_data(broadcast_text=text)
        
        data = await state.get_data()
        segment_name = data.get('segment_name', 'Неизвестно')
        users_count = data.get('users_count', 0)
        content_type = data.get('content_type', 'text')
        image_file_id = data.get('image_file_id')
        
        # Показываем предпросмотр
        preview_text = (
            f"👁️ <b>ПРЕДПРОСМОТР РАССЫЛКИ</b>\n\n"
            f"👥 <b>Аудитория:</b> {segment_name}\n"
            f"📊 <b>Пользователей:</b> {users_count}\n"
            f"🎨 <b>Тип:</b> {content_type}\n\n"
            f"💬 <b>Сообщение:</b>\n{text}\n\n"
            f"⚠️ <b>Внимание!</b> После подтверждения рассылка начнется немедленно."
        )
        
        # Создаем клавиатуру подтверждения
        builder = InlineKeyboardBuilder()
        builder.button(text="✅ Подтвердить рассылку", callback_data="broadcast_confirm")
        builder.button(text="✏️ Изменить текст", callback_data="broadcast_edit_text")
        builder.button(text="🔄 Выбрать другой сегмент", callback_data="broadcast_back_to_segments")
        builder.button(text="❌ Отмена", callback_data="broadcast_cancel")
        builder.adjust(1)
        
        if content_type == "image" and image_file_id:
            try:
                await message.answer_photo(
                    photo=image_file_id,
                    caption=preview_text,
                    parse_mode="HTML",
                    reply_markup=builder.as_markup()
                )
            except Exception as preview_error:
                logger.error(f"❌ Error showing image preview: {preview_error}")
                await message.answer(
                    f"❌ <b>Ошибка предпросмотра изображения</b>\n\n"
                    f"{preview_text}",
                    parse_mode="HTML",
                    reply_markup=builder.as_markup()
                )
        else:
            await message.answer(
                preview_text,
                parse_mode="HTML",
                reply_markup=builder.as_markup()
            )
        
        await state.set_state(BroadcastStates.confirming)
        
    except Exception as e:
        logger.error(f"❌ Error processing broadcast text: {e}")
        await message.answer("❌ Ошибка при обработке текста")

@router.callback_query(BroadcastStates.confirming, F.data == "broadcast_confirm")
async def confirm_broadcast(callback: CallbackQuery, state: FSMContext, bot: Bot, db_manager: DatabaseManager):
    """Подтверждение и запуск рассылки"""
    try:
        await callback.answer()

        data = await state.get_data()
        segment_key = data.get('segment_key')
        segment_name = data.get('segment_name')
        users_count = data.get('users_count', 0)
        content_type = data.get('content_type')
        text = data.get('broadcast_text')
        image_file_id = data.get('image_file_id')
        
        logger.info(f"📤 Starting broadcast: type={content_type}, segment={segment_key}, users={users_count}, has_image={bool(image_file_id)}")
        
        # Вместо редактирования существующего сообщения, отправляем новое
        progress_message = await callback.message.answer(
            f"🚀 <b>ЗАПУСК РАССЫЛКИ</b>\n\n"
            f"📤 Отправка {users_count} сообщений...\n"
            f"⏳ Это может занять несколько минут",
            parse_mode="HTML"
        )
        
        # Создаем запись о рассылке в БД
        broadcast_id = await db_manager.create_broadcast(
            title=f"Рассылка {datetime.now().strftime('%d.%m.%Y %H:%M')}",
            message_text=text,
            target_sex='all',
            target_major='all',
            message_type=content_type,
            image_file_id=image_file_id
        )
        
        if not broadcast_id:
            await progress_message.edit_text("❌ Ошибка при создании рассылки в БД")
            await state.clear()
            return
        
        # Получаем пользователей для рассылки
        users = await db_manager.get_users_by_segment(segment_key)
        
        # Запускаем рассылку
        broadcast_manager = BroadcastManager(db_manager)
        sent_count = 0
        failed_count = 0
        
        for user in users:
            try:
                success = await broadcast_manager.send_broadcast_message(
                    bot=bot,
                    user_id=user['user_id'],
                    message_type=content_type,
                    text=text,
                    image_file_id=image_file_id
                )
                
                if success:
                    sent_count += 1
                else:
                    failed_count += 1
                    
                # Обновляем прогресс каждые 10 сообщений
                if (sent_count + failed_count) % 10 == 0:
                    try:
                        await progress_message.edit_text(
                            f"📤 <b>РАССЫЛКА В ПРОЦЕССЕ</b>\n\n"
                            f"✅ Отправлено: {sent_count}\n"
                            f"❌ Ошибок: {failed_count}\n"
                            f"⏳ Осталось: {len(users) - sent_count - failed_count}",
                            parse_mode="HTML"
                        )
                    except Exception as edit_error:
                        logger.error(f"Ошибка редактирования progress_message: {edit_error}")
                        # Продолжаем рассылку даже если не удалось обновить прогресс
                        
            except Exception as e:
                logger.error(f"❌ Failed to send to {user['user_id']}: {e}")
                failed_count += 1
        
        # Финальный отчет
        report_text = (
            f"✅ <b>РАССЫЛКА ЗАВЕРШЕНА</b>\n\n"
            f"📊 <b>Итоги:</b>\n"
            f"• ✅ Успешно: {sent_count}\n"
            f"• ❌ Ошибок: {failed_count}\n"
            f"• 📈 Эффективность: {sent_count/max(1, len(users))*100:.1f}%\n\n"
            f"👥 <b>Аудитория:</b> {segment_name}\n"
            f"🎨 <b>Тип:</b> {content_type}\n"
            f"🆔 <b>ID рассылки:</b> {broadcast_id}"
        )
        
        if content_type == "image":
            report_text += f"\n🖼️ <b>Изображение:</b> {'✅' if image_file_id else '❌'}"
        
        # Обновляем статистику рассылки в БД
        await db_manager.update_broadcast_stats(broadcast_id, sent_count)
        
        await progress_message.edit_text(report_text, parse_mode="HTML")
        
        # Логируем действие
        await db_manager.add_user_action(
            user_id=callback.from_user.id,
            action_type='broadcast_completed',
            action_data={
                'broadcast_id': broadcast_id,
                'segment': segment_key,
                'sent_count': sent_count,
                'failed_count': failed_count,
                'content_type': content_type,
                'has_image': bool(image_file_id)
            }
        )
        
        logger.info(f"✅ Broadcast #{broadcast_id} completed: {sent_count} sent, {failed_count} failed")
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"❌ Error confirming broadcast: {e}")
        try:
            # Пытаемся отправить сообщение об ошибке новым сообщением
            await callback.message.answer("❌ Ошибка при запуске рассылки")
        except Exception as send_error:
            logger.error(f"❌ Failed to send error message: {send_error}")
        await state.clear()

@router.callback_query(F.data == "broadcast_back_to_segments")
async def back_to_segments(callback: CallbackQuery, state: FSMContext, db_manager: DatabaseManager, l10n: FluentLocalization):
    """Возврат к выбору сегмента"""
    # Используем существующую функцию start_broadcast, но передаем правильные параметры
    if not settings.is_admin(callback.from_user.id):
        await callback.answer("❌ Эта команда доступна только администраторам.")
        return
    
    try:
        # Гарантируем, что пользователь существует в базе
        await db_manager.ensure_user_exists(
            user_id=callback.from_user.id,
            username=callback.from_user.username,
            full_name=callback.from_user.full_name
        )
        
        broadcast_manager = BroadcastManager(db_manager)
        
        # Создаем клавиатуру для выбора сегмента
        builder = InlineKeyboardBuilder()
        
        for segment_key, segment_info in broadcast_manager.segments.items():
            users_count = await broadcast_manager.get_segment_users_count(segment_key)
            builder.button(
                text=f"{segment_info['name']} ({users_count})",
                callback_data=f"broadcast_segment_{segment_key}"
            )
        
        builder.button(text="❌ Отмена", callback_data="broadcast_cancel")
        builder.adjust(1)
        
        await callback.message.edit_text(
            "📤 <b>СОЗДАНИЕ РАССЫЛКИ</b>\n\n"
            "👥 <b>Выберите аудиторию для рассылки:</b>",
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )
        
        await state.set_state(BroadcastStates.choosing_segment)
        await db_manager.add_user_action(
            user_id=callback.from_user.id,
            action_type='broadcast_restarted'
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"❌ Error in back_to_segments: {e}")
        await callback.answer("❌ Ошибка при возврате к выбору сегмента")

@router.callback_query(F.data == "broadcast_edit_text")
async def edit_broadcast_text(callback: CallbackQuery, state: FSMContext):
    """Редактирование текста рассылки"""
    data = await state.get_data()
    content_type = data.get('content_type', 'text')
    
    if content_type == "text":
        await callback.message.edit_text(
            "📝 <b>Введите новый текст рассылки:</b>\n\n"
            "💡 <i>Поддерживается HTML-разметка</i>",
            parse_mode="HTML"
        )
    else:
        await callback.message.edit_text(
            "📝 <b>Введите новый текст для изображения:</b>",
            parse_mode="HTML"
        )
    
    await state.set_state(BroadcastStates.entering_text)
    await callback.answer()

@router.callback_query(F.data == "broadcast_cancel")
async def cancel_broadcast(callback: CallbackQuery, state: FSMContext):
    """Отмена рассылки"""
    await callback.message.edit_text("❌ Рассылка отменена")
    await state.clear()
    await callback.answer()

# Обработка команды отмены
@router.message(BroadcastStates.entering_text, F.text == "/cancel")
@router.message(BroadcastStates.entering_image, F.text == "/cancel")
async def cancel_broadcast_command(message: Message, state: FSMContext):
    """Отмена рассылки по команде"""
    await message.answer("❌ Рассылка отменена")
    await state.clear()