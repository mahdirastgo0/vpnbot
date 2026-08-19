from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery

from app.config import settings


class IsAdmin(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        return event.from_user.id in settings.ADMIN_IDS
