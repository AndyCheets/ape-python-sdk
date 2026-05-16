from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ape_sdk.common.ids import new_id
from ape_sdk.common.time import utc_now
from ape_sdk.database.models import AIConversation, AIConversationMessage, AIInteraction


class AIConversationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_or_create_conversation(
        self,
        *,
        source: str,
        source_conversation_id: str,
        recipient_id: str | None,
        default_lookback_days: int | None = 90,
    ) -> tuple[AIConversation, bool]:
        conversation = self.session.scalars(
            select(AIConversation).where(
                AIConversation.source == source,
                AIConversation.source_conversation_id == source_conversation_id,
            )
        ).first()
        now = utc_now()
        if conversation is not None:
            conversation.updated_at_utc = now
            if recipient_id and conversation.recipient_id is None:
                conversation.recipient_id = recipient_id
            return conversation, False

        conversation = AIConversation(
            conversation_id=new_id(),
            source=source,
            source_conversation_id=source_conversation_id,
            recipient_id=recipient_id,
            active_email_account_id=None,
            active_email_account_name=None,
            default_lookback_days=default_lookback_days,
            summary=None,
            created_at_utc=now,
            updated_at_utc=now,
        )
        self.session.add(conversation)
        return conversation, True

    def add_message(
        self,
        *,
        conversation_id: str,
        role: str,
        direction: str,
        source: str,
        content: str,
        created_at_utc: datetime,
        interaction_id: str | None = None,
        source_message_id: str | None = None,
        content_type: str = "text",
        metadata_json: str | None = None,
    ) -> AIConversationMessage:
        message = AIConversationMessage(
            message_id=new_id(),
            conversation_id=conversation_id,
            interaction_id=interaction_id,
            role=role,
            direction=direction,
            source=source,
            source_message_id=source_message_id,
            content=content,
            content_type=content_type,
            created_at_utc=created_at_utc,
            metadata_json=metadata_json,
        )
        self.session.add(message)
        return message

    def create_interaction(
        self,
        *,
        interaction_type: str,
        conversation_id: str,
        trigger_message_id: str,
        model: str | None,
        metadata_json: str | None = None,
        prompt_text: str | None = None,
    ) -> AIInteraction:
        interaction = AIInteraction(
            interaction_id=new_id(),
            interaction_type=interaction_type,
            conversation_id=conversation_id,
            trigger_message_id=trigger_message_id,
            prompt_text=prompt_text,
            response_text=None,
            model=model,
            status="started",
            created_at_utc=utc_now(),
            completed_at_utc=None,
            error_message=None,
            metadata_json=metadata_json,
        )
        self.session.add(interaction)
        return interaction

    def recent_messages_before(
        self,
        *,
        conversation_id: str,
        current_message_id: str,
        limit: int = 10,
    ) -> list[AIConversationMessage]:
        messages = list(
            self.session.scalars(
                select(AIConversationMessage)
                .where(AIConversationMessage.conversation_id == conversation_id)
                .order_by(AIConversationMessage.created_at_utc.desc())
                .limit(limit + 1)
            ).all()
        )
        previous = [message for message in messages if message.message_id != current_message_id]
        return list(reversed(previous[:limit]))

    def complete_interaction(
        self,
        interaction: AIInteraction,
        *,
        prompt_text: str,
        response_text: str,
        model: str,
        metadata_json: str | None = None,
    ) -> None:
        interaction.prompt_text = prompt_text
        interaction.response_text = response_text
        interaction.model = model
        interaction.status = "completed"
        interaction.completed_at_utc = utc_now()
        if metadata_json is not None:
            interaction.metadata_json = metadata_json

    def fail_interaction(
        self,
        interaction: AIInteraction,
        *,
        error_message: str,
    ) -> None:
        interaction.status = "failed"
        interaction.completed_at_utc = utc_now()
        interaction.error_message = error_message
