from sqlalchemy import select
from sqlalchemy.orm import Session

from ape_sdk.common.ids import new_id
from ape_sdk.common.time import utc_now
from ape_sdk.database.models import TelegramRecipient

AWAITING_NAME_NOTE = "registration:awaiting_name"
PENDING_APPROVAL_NOTE = "Registration pending approval"


class TelegramRecipientRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_active_telegram_recipients(self) -> list[TelegramRecipient]:
        return list(
            self.session.scalars(
                select(TelegramRecipient)
                .where(TelegramRecipient.is_active.is_(True))
                .order_by(TelegramRecipient.display_name.asc())
            )
        )

    def get_telegram_recipient_by_chat_id(self, chat_id: str) -> TelegramRecipient | None:
        return self.session.scalars(
            select(TelegramRecipient).where(TelegramRecipient.chat_id == chat_id).limit(1)
        ).first()

    def get_active_telegram_recipient_by_chat_id(self, chat_id: str) -> TelegramRecipient | None:
        return self.session.scalars(
            select(TelegramRecipient)
            .where(TelegramRecipient.chat_id == chat_id, TelegramRecipient.is_active.is_(True))
            .limit(1)
        ).first()

    def start_registration(
        self,
        *,
        chat_id: str,
        display_name: str,
        recipient_type: str = "internal",
    ) -> TelegramRecipient:
        now = utc_now()
        existing = self.get_telegram_recipient_by_chat_id(chat_id)
        if existing is not None:
            if existing.is_active:
                return existing
            existing.notes = AWAITING_NAME_NOTE
            existing.updated_at_utc = now
            if not existing.display_name:
                existing.display_name = display_name
            return existing

        recipient = TelegramRecipient(
            recipient_id=new_id(),
            display_name=display_name,
            chat_id=chat_id,
            is_active=False,
            recipient_type=recipient_type,
            notes=AWAITING_NAME_NOTE,
            last_sent_at_utc=None,
            last_error_message=None,
            created_at_utc=now,
            updated_at_utc=now,
        )
        self.session.add(recipient)
        return recipient

    def complete_registration_name(
        self,
        *,
        chat_id: str,
        display_name: str,
    ) -> TelegramRecipient | None:
        recipient = self.get_telegram_recipient_by_chat_id(chat_id)
        if recipient is None:
            return None
        recipient.display_name = display_name[:255]
        recipient.is_active = False
        recipient.notes = PENDING_APPROVAL_NOTE
        recipient.updated_at_utc = utc_now()
        return recipient

    def mark_telegram_recipient_sent(self, recipient_id: str) -> None:
        recipient = self.session.get(TelegramRecipient, recipient_id)
        if recipient is None:
            return
        now = utc_now()
        recipient.last_sent_at_utc = now
        recipient.last_error_message = None
        recipient.updated_at_utc = now

    def mark_telegram_recipient_error(self, recipient_id: str, error_message: str) -> None:
        recipient = self.session.get(TelegramRecipient, recipient_id)
        if recipient is None:
            return
        recipient.last_error_message = error_message[:1000]
        recipient.updated_at_utc = utc_now()
