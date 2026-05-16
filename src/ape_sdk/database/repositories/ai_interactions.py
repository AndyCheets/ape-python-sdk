from sqlalchemy import select
from sqlalchemy.orm import Session

from ape_sdk.database.models import AIInteraction


class AIInteractionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def latest(self, limit: int = 10) -> list[AIInteraction]:
        return list(
            self.session.scalars(
                select(AIInteraction).order_by(AIInteraction.created_at_utc.desc()).limit(limit)
            ).all()
        )

