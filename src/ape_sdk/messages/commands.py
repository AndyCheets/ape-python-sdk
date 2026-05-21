from typing import Any
from datetime import date, datetime
from pydantic import BaseModel, Field


class ExampleCommand(BaseModel):
    """Example command payload for services generated from the worker template."""

    requested_by: str | None = Field(default=None, alias="requestedBy")
    parameters: dict[str, Any] = Field(default_factory=dict)


class RunEmailDataSync(BaseModel):
    provider: str | None = None
    account_id: str | None = None
    lookback_days: int | None = None
    requested_by: str | None = None
    tenant_key: str | None = None


class GenerateDailyReport(BaseModel):
    report_date: date | None = None


class SendTelegramMessage(BaseModel):
    chat_id: str
    text: str
    report_id: str | None = None


class SendDailyTelegramReport(BaseModel):
    report_id: str | None = None
    report_date: date | None = None
    requested_by: str | None = None
    tenant_key: str | None = None
    reason: str | None = None


class SendEmailSummary(BaseModel):
    report_id: str
    recipient: str


class ProcessBiteChatMessage(BaseModel):
    message_text: str
    telegram_chat_id: str
    telegram_user_id: str | None = None
    telegram_username: str | None = None
    telegram_display_name: str | None = None
    source_message_id: str | None = None
    requested_at_utc: datetime
    requested_by_recipient_id: str | None = None
    source: str = "telegram"


class GenerateWeeklyEmailReport(BaseModel):
    report_date: date | None = None
    period_start_date: date | None = None
    period_end_date: date | None = None
    requested_by: str | None = None
    tenant_key: str | None = None
    reason: str | None = None
    source: str = "scheduler"


class SendWeeklyEmailReport(BaseModel):
    report_id: str
    report_date: date | None = None
    requested_by: str | None = None
    tenant_key: str | None = None
    reason: str | None = None


class AnalyseCampaignContent(BaseModel):
    email_campaign_content_id: str
    email_campaign_id: str | None = None
    prompt_key: str = "campaign_content_analysis"
    prompt_version: str = "v1"
    requested_by: str | None = None
    tenant_key: str | None = None
    reason: str | None = None
    requested_at_utc: datetime
