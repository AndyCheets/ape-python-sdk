from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class EmailAccount(Base):
    __tablename__ = "email_accounts"

    account_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    provider: Mapped[str] = mapped_column(String(50), index=True)
    external_account_id: Mapped[str | None] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255))
    api_key_encrypted: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime)


class EmailCampaign(Base):
    __tablename__ = "email_campaigns"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "provider",
            "external_campaign_id",
            name="uq_email_campaigns_account_provider_external",
        ),
    )

    campaign_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("email_accounts.account_id"))
    provider: Mapped[str] = mapped_column(String(50), index=True)
    external_campaign_id: Mapped[str] = mapped_column(String(255), index=True)
    name: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str | None] = mapped_column(String(255))
    sent_at_utc: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(50))
    created_at_utc: Mapped[datetime] = mapped_column(DateTime)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime)
    account: Mapped[EmailAccount] = relationship()


class EmailAudienceSegment(Base):
    __tablename__ = "email_audience_segments"
    __table_args__ = (
        UniqueConstraint(
            "email_account_id",
            "provider_segment_id",
            "segment_type",
            name="uq_email_audience_segments_account_segment",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email_account_id: Mapped[str] = mapped_column(ForeignKey("email_accounts.account_id"))
    provider_segment_id: Mapped[str] = mapped_column(String(255), index=True)
    name: Mapped[str] = mapped_column(String(255))
    segment_type: Mapped[str] = mapped_column(String(50), index=True)
    member_count: Mapped[int | None] = mapped_column(Integer)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime)
    account: Mapped[EmailAccount] = relationship()


class EmailCampaignAudienceSegment(Base):
    __tablename__ = "email_campaign_audience_segments"
    __table_args__ = (
        UniqueConstraint(
            "email_campaign_id",
            "email_audience_segment_id",
            name="uq_email_campaign_audience_segments_campaign_segment",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email_campaign_id: Mapped[str] = mapped_column(
        ForeignKey("email_campaigns.campaign_id"), index=True
    )
    email_audience_segment_id: Mapped[str] = mapped_column(
        ForeignKey("email_audience_segments.id"), index=True
    )
    created_at_utc: Mapped[datetime] = mapped_column(DateTime)
    campaign: Mapped[EmailCampaign] = relationship()
    audience_segment: Mapped[EmailAudienceSegment] = relationship()


class CampaignMetricSnapshot(Base):
    __tablename__ = "campaign_metric_snapshots"

    metric_snapshot_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("email_campaigns.campaign_id"), index=True)
    captured_at_utc: Mapped[datetime] = mapped_column(DateTime, index=True)
    emails_sent: Mapped[int | None] = mapped_column(Integer)
    emails_delivered: Mapped[int | None] = mapped_column(Integer)
    opens_total: Mapped[int | None] = mapped_column(Integer)
    opens_unique: Mapped[int | None] = mapped_column(Integer)
    open_rate: Mapped[float | None] = mapped_column(Float)
    clicks_total: Mapped[int | None] = mapped_column(Integer)
    clicks_unique: Mapped[int | None] = mapped_column(Integer)
    click_rate: Mapped[float | None] = mapped_column(Float)
    unsubscribes: Mapped[int | None] = mapped_column(Integer)
    unsubscribe_rate: Mapped[float | None] = mapped_column(Float)
    bounces_total: Mapped[int | None] = mapped_column(Integer)
    bounce_rate: Mapped[float | None] = mapped_column(Float)
    spam_complaints: Mapped[int | None] = mapped_column(Integer)
    spam_complaint_rate: Mapped[float | None] = mapped_column(Float)
    forwards: Mapped[int | None] = mapped_column(Integer)
    revenue: Mapped[float | None] = mapped_column(Float)
    raw_provider_stats_json: Mapped[str | None] = mapped_column(Text)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime)


class EmailCampaignContent(Base):
    __tablename__ = "email_campaign_content"
    __table_args__ = (
        UniqueConstraint("email_campaign_id", name="uq_email_campaign_content_campaign"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email_campaign_id: Mapped[str] = mapped_column(
        ForeignKey("email_campaigns.campaign_id"), index=True
    )
    subject: Mapped[str | None] = mapped_column(String(255))
    preheader: Mapped[str | None] = mapped_column(String(255))
    from_name: Mapped[str | None] = mapped_column(String(255))
    from_email: Mapped[str | None] = mapped_column(String(255))
    reply_to_email: Mapped[str | None] = mapped_column(String(255))
    html_body: Mapped[str | None] = mapped_column(Text)
    text_body: Mapped[str | None] = mapped_column(Text)
    content_source: Mapped[str | None] = mapped_column(String(100))
    content_fetched_at_utc: Mapped[datetime | None] = mapped_column(DateTime)
    provider_content_id: Mapped[str | None] = mapped_column(String(255))
    raw_content_metadata_json: Mapped[str | None] = mapped_column(Text)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime)


class EmailCampaignContentAnalysis(Base):
    __tablename__ = "email_campaign_content_analysis"
    __table_args__ = (
        UniqueConstraint(
            "email_campaign_content_id",
            "prompt_key",
            "prompt_version",
            name="uq_email_campaign_content_analysis_content_prompt",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email_campaign_content_id: Mapped[str] = mapped_column(
        ForeignKey("email_campaign_content.id"), index=True
    )
    email_campaign_id: Mapped[str] = mapped_column(
        ForeignKey("email_campaigns.campaign_id"), index=True
    )
    prompt_key: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(50))
    model: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(50), index=True)
    summary: Mapped[str | None] = mapped_column(Text)
    primary_cta_text: Mapped[str | None] = mapped_column(String(255))
    primary_cta_url: Mapped[str | None] = mapped_column(String(2048))
    primary_cta_confidence: Mapped[str | None] = mapped_column(String(20))
    secondary_ctas_json: Mapped[str | None] = mapped_column(Text)
    key_links_json: Mapped[str | None] = mapped_column(Text)
    offer_type: Mapped[str | None] = mapped_column(String(100))
    campaign_intent: Mapped[str | None] = mapped_column(String(100))
    audience_action: Mapped[str | None] = mapped_column(String(255))
    tone: Mapped[str | None] = mapped_column(String(100))
    has_clear_cta: Mapped[bool | None] = mapped_column(Boolean)
    confidence: Mapped[str | None] = mapped_column(String(20))
    warnings_json: Mapped[str | None] = mapped_column(Text)
    analysis_json: Mapped[str | None] = mapped_column(Text)
    started_at_utc: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at_utc: Mapped[datetime | None] = mapped_column(DateTime)
    failed_at_utc: Mapped[datetime | None] = mapped_column(DateTime)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error_message: Mapped[str | None] = mapped_column(Text)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime)


class SyncRun(Base):
    __tablename__ = "sync_runs"

    sync_run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    provider: Mapped[str | None] = mapped_column(String(50), index=True)
    started_at_utc: Mapped[datetime] = mapped_column(DateTime)
    completed_at_utc: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(50))
    triggered_by_message_id: Mapped[str | None] = mapped_column(String(36))
    accounts_processed: Mapped[int] = mapped_column(Integer, default=0)
    campaigns_found: Mapped[int] = mapped_column(Integer, default=0)
    campaigns_upserted: Mapped[int] = mapped_column(Integer, default=0)
    metric_snapshots_created: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime)


CampaignMetric = CampaignMetricSnapshot


class AIInteraction(Base):
    __tablename__ = "ai_interactions"
    __table_args__ = (
        Index("idx_ai_interactions_conversation_created", "conversation_id", "created_at_utc"),
    )

    interaction_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    interaction_type: Mapped[str] = mapped_column(String(100))
    prompt_text: Mapped[str | None] = mapped_column(Text)
    response_text: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(String(100))
    created_at_utc: Mapped[datetime] = mapped_column(DateTime)
    metadata_json: Mapped[str | None] = mapped_column(Text)
    conversation_id: Mapped[str | None] = mapped_column(String(36))
    trigger_message_id: Mapped[str | None] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(String(50), default="completed")
    completed_at_utc: Mapped[datetime | None] = mapped_column(DateTime)
    error_message: Mapped[str | None] = mapped_column(Text)


class AIConversation(Base):
    __tablename__ = "ai_conversations"
    __table_args__ = (
        UniqueConstraint(
            "source",
            "source_conversation_id",
            name="uq_ai_conversations_source_conversation",
        ),
    )

    conversation_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source: Mapped[str] = mapped_column(String(50))
    source_conversation_id: Mapped[str] = mapped_column(String(100))
    recipient_id: Mapped[str | None] = mapped_column(String(36))
    active_email_account_id: Mapped[str | None] = mapped_column(String(36))
    active_email_account_name: Mapped[str | None] = mapped_column(String(255))
    default_lookback_days: Mapped[int | None] = mapped_column(Integer)
    summary: Mapped[str | None] = mapped_column(Text)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime)


class AIConversationMessage(Base):
    __tablename__ = "ai_conversation_messages"
    __table_args__ = (
        Index(
            "idx_ai_conversation_messages_conversation_created",
            "conversation_id",
            "created_at_utc",
        ),
    )

    message_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("ai_conversations.conversation_id"))
    interaction_id: Mapped[str | None] = mapped_column(ForeignKey("ai_interactions.interaction_id"))
    role: Mapped[str] = mapped_column(String(50))
    direction: Mapped[str] = mapped_column(String(50))
    source: Mapped[str] = mapped_column(String(50))
    source_message_id: Mapped[str | None] = mapped_column(String(100))
    content: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(String(50), default="text")
    created_at_utc: Mapped[datetime] = mapped_column(DateTime)
    metadata_json: Mapped[str | None] = mapped_column(Text)
    conversation: Mapped[AIConversation] = relationship()
    interaction: Mapped[AIInteraction | None] = relationship()


class DailyReport(Base):
    __tablename__ = "daily_reports"

    report_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    report_date: Mapped[date] = mapped_column(Date, index=True)
    report_text: Mapped[str] = mapped_column(Text)
    structured_summary_json: Mapped[str | None] = mapped_column(Text)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime)
    source_ai_interaction_id: Mapped[str | None] = mapped_column(
        ForeignKey("ai_interactions.interaction_id")
    )




class WeeklyEmailReport(Base):
    __tablename__ = "weekly_email_reports"

    report_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    report_date: Mapped[date] = mapped_column(Date, index=True)
    period_start_date: Mapped[date | None] = mapped_column(Date)
    period_end_date: Mapped[date | None] = mapped_column(Date)
    title: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(255))
    body_text: Mapped[str | None] = mapped_column(Text)
    body_html: Mapped[str | None] = mapped_column(Text)
    report_type: Mapped[str] = mapped_column(String(100), default="weekly_email_summary")
    channel: Mapped[str] = mapped_column(String(50), default="email")
    created_at_utc: Mapped[datetime] = mapped_column(DateTime)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime)
    source: Mapped[str | None] = mapped_column(String(100))
    metadata_json: Mapped[str | None] = mapped_column(Text)


class EmailReportRecipient(Base):
    __tablename__ = "email_report_recipients"

    recipient_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(255))
    email_address: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    recipient_type: Mapped[str | None] = mapped_column(String(50))
    receives_weekly_email_report: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    receives_daily_email_report: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime)
    last_sent_at_utc: Mapped[datetime | None] = mapped_column(DateTime)
    last_error_message: Mapped[str | None] = mapped_column(Text)


class TelegramRecipient(Base):
    __tablename__ = "telegram_recipients"

    recipient_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(255))
    chat_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    recipient_type: Mapped[str | None] = mapped_column(String(50))
    notes: Mapped[str | None] = mapped_column(Text)
    last_sent_at_utc: Mapped[datetime | None] = mapped_column(DateTime)
    last_error_message: Mapped[str | None] = mapped_column(Text)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime)


class OutboundMessage(Base):
    __tablename__ = "outbound_messages"

    outbound_message_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    channel: Mapped[str] = mapped_column(String(50), index=True)
    destination: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50))
    report_id: Mapped[str | None] = mapped_column(ForeignKey("daily_reports.report_id"))
    created_at_utc: Mapped[datetime] = mapped_column(DateTime)
