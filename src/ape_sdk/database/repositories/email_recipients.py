from sqlalchemy import select
from sqlalchemy.orm import Session

from ape_sdk.common.time import utc_now
from ape_sdk.database.models import EmailReportRecipient


class EmailReportRecipientRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_active_weekly_email_report_recipients(self) -> list[EmailReportRecipient]:
        return list(
            self.session.scalars(
                select(EmailReportRecipient)
                .where(
                    EmailReportRecipient.is_active.is_(True),
                    EmailReportRecipient.receives_weekly_email_report.is_(True),
                )
                .order_by(EmailReportRecipient.display_name.asc())
            )
        )

    def mark_email_report_recipient_sent(self, recipient_id: str, sent_at_utc=None) -> None:
        recipient = self.session.get(EmailReportRecipient, recipient_id)
        if recipient is None:
            return
        now = sent_at_utc or utc_now()
        recipient.last_sent_at_utc = now
        recipient.last_error_message = None
        recipient.updated_at_utc = now

    def mark_email_report_recipient_error(self, recipient_id: str, error_message: str) -> None:
        recipient = self.session.get(EmailReportRecipient, recipient_id)
        if recipient is None:
            return
        recipient.last_error_message = error_message[:1000]
        recipient.updated_at_utc = utc_now()
