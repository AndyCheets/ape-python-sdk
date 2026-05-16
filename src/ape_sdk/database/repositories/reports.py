from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ape_sdk.common.ids import new_id
from ape_sdk.common.time import utc_now
from ape_sdk.database.models import AIInteraction, DailyReport, WeeklyEmailReport


class ReportRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_ai_interaction(
        self,
        *,
        interaction_type: str,
        prompt_text: str | None,
        response_text: str | None,
        model: str | None,
        metadata_json: str | None = None,
        conversation_id: str | None = None,
        trigger_message_id: str | None = None,
        status: str = "completed",
        completed_at_utc=None,
        error_message: str | None = None,
    ) -> AIInteraction:
        interaction = AIInteraction(
            interaction_id=new_id(),
            interaction_type=interaction_type,
            prompt_text=prompt_text,
            response_text=response_text,
            model=model,
            created_at_utc=utc_now(),
            metadata_json=metadata_json,
            conversation_id=conversation_id,
            trigger_message_id=trigger_message_id,
            status=status,
            completed_at_utc=completed_at_utc or utc_now() if status == "completed" else None,
            error_message=error_message,
        )
        self.session.add(interaction)
        return interaction

    def create_daily_report(
        self,
        *,
        report_date: date,
        report_text: str,
        source_ai_interaction_id: str | None,
        structured_summary_json: str | None = None,
    ) -> DailyReport:
        report = DailyReport(
            report_id=new_id(),
            report_date=report_date,
            report_text=report_text,
            structured_summary_json=structured_summary_json,
            created_at_utc=utc_now(),
            source_ai_interaction_id=source_ai_interaction_id,
        )
        self.session.add(report)
        return report

    def latest(self) -> DailyReport | None:
        return self.session.scalars(
            select(DailyReport).order_by(DailyReport.created_at_utc.desc()).limit(1)
        ).first()

    def get_latest_daily_report(self) -> DailyReport | None:
        return self.latest()



    def create_weekly_email_report(
        self,
        *,
        report_date: date,
        period_start_date: date | None,
        period_end_date: date | None,
        title: str,
        subject: str,
        body_text: str | None,
        body_html: str | None,
        source: str | None,
        metadata_json: str | None = None,
    ) -> WeeklyEmailReport:
        now = utc_now()
        report = WeeklyEmailReport(
            report_id=new_id(),
            report_date=report_date,
            period_start_date=period_start_date,
            period_end_date=period_end_date,
            title=title,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            report_type="weekly_email_summary",
            channel="email",
            created_at_utc=now,
            updated_at_utc=now,
            source=source,
            metadata_json=metadata_json,
        )
        self.session.add(report)
        return report

    def get_weekly_email_report_by_id(self, report_id: str) -> WeeklyEmailReport | None:
        return self.session.get(WeeklyEmailReport, report_id)
    def get_daily_report_by_id(self, report_id: str) -> DailyReport | None:
        return self.session.get(DailyReport, report_id)
