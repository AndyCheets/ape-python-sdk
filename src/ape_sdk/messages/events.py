from typing import Any
from datetime import date, datetime
from pydantic import BaseModel


class ExampleTaskCompleted(BaseModel):
    """Example completed event payload for services generated from the worker template."""

    result: dict[str, Any]


class ExampleTaskFailed(BaseModel):
    """Example failed event payload for services generated from the worker template."""

    error_type: str
    error_message: str

class EmailDataSyncCompleted(BaseModel):
    sync_run_id: str
    provider: str | None = None
    accounts_processed: int
    campaigns_found: int
    campaigns_upserted: int
    metric_snapshots_created: int
    completed_at_utc: datetime


class EmailDataSyncFailed(BaseModel):
    sync_run_id: str | None = None
    provider: str | None = None
    error_message: str
    failed_at_utc: datetime


class DailyReportGenerated(BaseModel):
    report_id: str
    report_date: date


class DailyReportGenerationFailed(BaseModel):
    report_date: date | None = None
    error_message: str


class BiteChatResponseGenerated(BaseModel):
    interaction_id: str
    conversation_id: str | None = None
    telegram_chat_id: str
    telegram_user_id: str | None = None
    telegram_username: str | None = None
    telegram_display_name: str | None = None
    source_message_id: str | None = None
    message_text: str
    response_text: str
    responded_at_utc: datetime
    source: str = "telegram"


class TelegramMessageSent(BaseModel):
    outbound_message_id: str
    report_id: str | None = None


class TelegramMessageFailed(BaseModel):
    report_id: str | None = None
    error_message: str


class DailyTelegramReportSent(BaseModel):
    report_id: str
    recipients_attempted: int
    recipients_sent: int
    recipients_failed: int
    sent_at_utc: datetime


class DailyTelegramReportFailed(BaseModel):
    report_id: str | None = None
    error_message: str
    failed_at_utc: datetime


class EmailSummarySent(BaseModel):
    outbound_message_id: str
    report_id: str
    recipient: str


class EmailSummaryFailed(BaseModel):
    report_id: str
    recipient: str
    error_message: str


class WeeklyEmailReportGenerated(BaseModel):
    report_id: str
    report_date: date
    period_start_date: date | None = None
    period_end_date: date | None = None
    generated_at_utc: datetime


class WeeklyEmailReportSent(BaseModel):
    report_id: str
    recipients_attempted: int
    recipients_sent: int
    recipients_failed: int
    sent_at_utc: datetime


class WeeklyEmailReportSendFailed(BaseModel):
    report_id: str | None = None
    error_message: str
    failed_at_utc: datetime


class CampaignContentAnalysed(BaseModel):
    email_campaign_content_id: str
    email_campaign_id: str
    analysis_id: str
    prompt_key: str
    prompt_version: str
    model: str
    analysed_at_utc: datetime


class CampaignContentAnalysisFailed(BaseModel):
    email_campaign_content_id: str
    email_campaign_id: str | None = None
    prompt_key: str
    prompt_version: str
    error_message: str
    failed_at_utc: datetime