import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, delete, func, select
from sqlalchemy.orm import Session

from ape_sdk.common.ids import new_id
from ape_sdk.common.time import utc_now
from ape_sdk.database.models import (
    CampaignMetricSnapshot,
    EmailAccount,
    EmailAudienceSegment,
    EmailCampaign,
    EmailCampaignAudienceSegment,
    EmailCampaignContent,
    EmailCampaignContentAnalysis,
)


@dataclass
class AudienceSegmentPerformance:
    name: str
    segment_type: str
    member_count: int | None


@dataclass
class CampaignPerformanceData:
    campaign_id: str
    campaign_external_id: str
    campaign_name: str
    subject: str | None
    sent_at_utc: datetime | None
    status: str
    emails_sent: int | None
    open_rate: float | None
    click_rate: float | None
    captured_at_utc: datetime | None
    emails_delivered: int | None = None
    opens_total: int | None = None
    opens_unique: int | None = None
    clicks_total: int | None = None
    clicks_unique: int | None = None
    unsubscribes: int | None = None
    unsubscribe_rate: float | None = None
    bounces_total: int | None = None
    bounce_rate: float | None = None
    spam_complaints: int | None = None
    spam_complaint_rate: float | None = None
    audience_segments: list[AudienceSegmentPerformance] = field(default_factory=list)
    content_analysis: dict[str, Any] = field(default_factory=lambda: {"analysis_available": False})


@dataclass
class AccountCampaignPerformance:
    email_account_id: str
    client_name: str
    provider: str
    account_external_id: str | None
    most_recent_sent_at_utc: datetime
    campaigns: list[CampaignPerformanceData]


class CampaignRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_accounts(self) -> list[EmailAccount]:
        return list(self.session.scalars(select(EmailAccount).order_by(EmailAccount.name)).all())

    def get_email_accounts(self) -> list[EmailAccount]:
        return list(self.session.scalars(select(EmailAccount).order_by(EmailAccount.name)).all())

    def find_email_accounts_by_name(self, name: str) -> list[EmailAccount]:
        search_term = name.strip()
        if not search_term:
            return []
        like_term = f"%{search_term}%"
        statement = (
            select(EmailAccount)
            .where(EmailAccount.name.ilike(like_term))
            .order_by(
                func.lower(EmailAccount.name) == func.lower(search_term),
                EmailAccount.name.asc(),
            )
        )
        return list(self.session.scalars(statement).all())

    def get_campaigns_for_account_since(
        self, email_account_id: str, sent_since_utc
    ) -> list[EmailCampaign]:
        statement = (
            select(EmailCampaign)
            .where(
                EmailCampaign.account_id == email_account_id,
                EmailCampaign.sent_at_utc.is_not(None),
                EmailCampaign.sent_at_utc >= sent_since_utc,
            )
            .order_by(EmailCampaign.sent_at_utc.desc())
        )
        return list(self.session.scalars(statement).all())

    def get_metric_snapshots_for_campaign_since(
        self, campaign_id: str, captured_since_utc
    ) -> list[CampaignMetricSnapshot]:
        statement = (
            select(CampaignMetricSnapshot)
            .where(
                CampaignMetricSnapshot.campaign_id == campaign_id,
                CampaignMetricSnapshot.captured_at_utc >= captured_since_utc,
            )
            .order_by(CampaignMetricSnapshot.captured_at_utc.asc())
        )
        return list(self.session.scalars(statement).all())

    def get_campaign_performance_data(
        self, days: int = 7
    ) -> list[AccountCampaignPerformance]:
        sent_since_utc = utc_now() - timedelta(days=days)
        latest_snapshot_subquery = (
            select(
                CampaignMetricSnapshot.campaign_id.label("campaign_id"),
                func.max(CampaignMetricSnapshot.captured_at_utc).label("latest_captured_at_utc"),
            )
            .group_by(CampaignMetricSnapshot.campaign_id)
            .subquery()
        )

        statement = (
            select(EmailAccount, EmailCampaign, CampaignMetricSnapshot)
            .join(EmailCampaign, EmailCampaign.account_id == EmailAccount.account_id)
            .outerjoin(
                latest_snapshot_subquery,
                EmailCampaign.campaign_id == latest_snapshot_subquery.c.campaign_id,
            )
            .outerjoin(
                CampaignMetricSnapshot,
                and_(
                    CampaignMetricSnapshot.campaign_id == EmailCampaign.campaign_id,
                    CampaignMetricSnapshot.captured_at_utc
                    == latest_snapshot_subquery.c.latest_captured_at_utc,
                ),
            )
            .where(
                EmailCampaign.sent_at_utc.is_not(None),
                EmailCampaign.sent_at_utc >= sent_since_utc,
            )
            .order_by(EmailCampaign.sent_at_utc.desc(), EmailAccount.name.asc())
        )

        rows = self.session.execute(statement).all()
        campaign_segments = self._audience_segments_by_campaign(
            [campaign.campaign_id for _, campaign, _ in rows]
        )

        groups: dict[str, AccountCampaignPerformance] = {}
        for account, campaign, snapshot in rows:
            account_group = groups.get(account.account_id)
            if account_group is None:
                account_group = AccountCampaignPerformance(
                    email_account_id=account.account_id,
                    client_name=account.name,
                    provider=account.provider,
                    account_external_id=account.external_account_id,
                    most_recent_sent_at_utc=campaign.sent_at_utc,
                    campaigns=[],
                )
                groups[account.account_id] = account_group

            account_group.campaigns.append(
                CampaignPerformanceData(
                    campaign_id=campaign.campaign_id,
                    campaign_external_id=campaign.external_campaign_id,
                    campaign_name=campaign.name,
                    subject=campaign.subject,
                    sent_at_utc=campaign.sent_at_utc,
                    status=campaign.status,
                    emails_sent=snapshot.emails_sent if snapshot else None,
                    open_rate=snapshot.open_rate if snapshot else None,
                    click_rate=snapshot.click_rate if snapshot else None,
                    captured_at_utc=snapshot.captured_at_utc if snapshot else None,
                    emails_delivered=snapshot.emails_delivered if snapshot else None,
                    opens_total=snapshot.opens_total if snapshot else None,
                    opens_unique=snapshot.opens_unique if snapshot else None,
                    clicks_total=snapshot.clicks_total if snapshot else None,
                    clicks_unique=snapshot.clicks_unique if snapshot else None,
                    unsubscribes=snapshot.unsubscribes if snapshot else None,
                    unsubscribe_rate=snapshot.unsubscribe_rate if snapshot else None,
                    bounces_total=snapshot.bounces_total if snapshot else None,
                    bounce_rate=snapshot.bounce_rate if snapshot else None,
                    spam_complaints=snapshot.spam_complaints if snapshot else None,
                    spam_complaint_rate=snapshot.spam_complaint_rate if snapshot else None,
                    audience_segments=campaign_segments.get(campaign.campaign_id, []),
                )
            )

        return sorted(
            groups.values(),
            key=lambda group: group.most_recent_sent_at_utc,
            reverse=True,
        )

    def get_campaigns_by_account(
        self, email_account_id: str, days: int = 90
    ) -> list[EmailCampaign]:
        sent_since_utc = utc_now() - timedelta(days=days)
        return self.get_campaigns_for_account_since(
            email_account_id=email_account_id,
            sent_since_utc=sent_since_utc,
        )

    def get_campaign_performance_by_account(
        self, email_account_id: str, days: int = 90
    ) -> AccountCampaignPerformance | None:
        account = self.session.get(EmailAccount, email_account_id)
        if account is None:
            return None

        sent_since_utc = utc_now() - timedelta(days=days)
        latest_snapshot_subquery = (
            select(
                CampaignMetricSnapshot.campaign_id.label("campaign_id"),
                func.max(CampaignMetricSnapshot.captured_at_utc).label("latest_captured_at_utc"),
            )
            .group_by(CampaignMetricSnapshot.campaign_id)
            .subquery()
        )
        statement = (
            select(EmailCampaign, CampaignMetricSnapshot)
            .outerjoin(
                latest_snapshot_subquery,
                EmailCampaign.campaign_id == latest_snapshot_subquery.c.campaign_id,
            )
            .outerjoin(
                CampaignMetricSnapshot,
                and_(
                    CampaignMetricSnapshot.campaign_id == EmailCampaign.campaign_id,
                    CampaignMetricSnapshot.captured_at_utc
                    == latest_snapshot_subquery.c.latest_captured_at_utc,
                ),
            )
            .where(
                EmailCampaign.account_id == email_account_id,
                EmailCampaign.sent_at_utc.is_not(None),
                EmailCampaign.sent_at_utc >= sent_since_utc,
            )
            .order_by(EmailCampaign.sent_at_utc.desc())
        )
        rows = self.session.execute(statement).all()
        campaigns = [campaign for campaign, _ in rows]
        campaign_segments = self._audience_segments_by_campaign([c.campaign_id for c in campaigns])
        compact_analyses = self.get_compact_content_analysis_for_campaigns(
            [campaign.campaign_id for campaign in campaigns]
        )
        return AccountCampaignPerformance(
            email_account_id=account.account_id,
            client_name=account.name,
            provider=account.provider,
            account_external_id=account.external_account_id,
            most_recent_sent_at_utc=campaigns[0].sent_at_utc if campaigns else utc_now(),
            campaigns=[
                CampaignPerformanceData(
                    campaign_id=campaign.campaign_id,
                    campaign_external_id=campaign.external_campaign_id,
                    campaign_name=campaign.name,
                    subject=campaign.subject,
                    sent_at_utc=campaign.sent_at_utc,
                    status=campaign.status,
                    emails_sent=snapshot.emails_sent if snapshot else None,
                    open_rate=snapshot.open_rate if snapshot else None,
                    click_rate=snapshot.click_rate if snapshot else None,
                    captured_at_utc=snapshot.captured_at_utc if snapshot else None,
                    emails_delivered=snapshot.emails_delivered if snapshot else None,
                    opens_total=snapshot.opens_total if snapshot else None,
                    opens_unique=snapshot.opens_unique if snapshot else None,
                    clicks_total=snapshot.clicks_total if snapshot else None,
                    clicks_unique=snapshot.clicks_unique if snapshot else None,
                    unsubscribes=snapshot.unsubscribes if snapshot else None,
                    unsubscribe_rate=snapshot.unsubscribe_rate if snapshot else None,
                    bounces_total=snapshot.bounces_total if snapshot else None,
                    bounce_rate=snapshot.bounce_rate if snapshot else None,
                    spam_complaints=snapshot.spam_complaints if snapshot else None,
                    spam_complaint_rate=snapshot.spam_complaint_rate if snapshot else None,
                    audience_segments=campaign_segments.get(campaign.campaign_id, []),
                    content_analysis=compact_analyses.get(
                        campaign.campaign_id, {"analysis_available": False}
                    ),
                )
                for campaign, snapshot in rows
            ],
        )

    def get_campaign_content_metadata(self, campaign_id: str) -> dict[str, Any] | None:
        campaign = self.session.get(EmailCampaign, campaign_id)
        if campaign is None:
            return None
        content = self.get_campaign_body(campaign_id)
        analysis = self.get_campaign_content_analysis(campaign_id=campaign_id)
        return {"campaign": campaign, "content": content, "analysis": analysis}

    def get_campaign_content_analysis(
        self, campaign_id: str, prompt_version: str | None = None
    ) -> EmailCampaignContentAnalysis | None:
        statement = select(EmailCampaignContentAnalysis).where(
            EmailCampaignContentAnalysis.email_campaign_id == campaign_id,
            EmailCampaignContentAnalysis.status == "completed",
        )
        if prompt_version is not None:
            statement = statement.where(
                EmailCampaignContentAnalysis.prompt_version == prompt_version
            )
        statement = statement.order_by(EmailCampaignContentAnalysis.completed_at_utc.desc())
        return self.session.scalars(statement).first()

    def get_campaign_body(self, campaign_id: str) -> EmailCampaignContent | None:
        return self.session.scalars(
            select(EmailCampaignContent).where(
                EmailCampaignContent.email_campaign_id == campaign_id
            )
        ).first()

    def get_compact_content_analysis_for_campaign(self, campaign_id: str) -> dict[str, Any]:
        return self.get_compact_content_analysis_for_campaigns([campaign_id]).get(
            campaign_id, {"analysis_available": False}
        )

    def get_compact_content_analysis_for_campaigns(
        self, campaign_ids: list[str]
    ) -> dict[str, dict[str, Any]]:
        unique_campaign_ids = list(dict.fromkeys(campaign_ids))
        if not unique_campaign_ids:
            return {}
        statement = (
            select(EmailCampaignContentAnalysis)
            .where(
                EmailCampaignContentAnalysis.email_campaign_id.in_(unique_campaign_ids),
                EmailCampaignContentAnalysis.status == "completed",
            )
            .order_by(
                EmailCampaignContentAnalysis.email_campaign_id.asc(),
                EmailCampaignContentAnalysis.completed_at_utc.desc(),
            )
        )
        analyses_by_campaign: dict[str, dict[str, Any]] = {}
        for analysis in self.session.scalars(statement).all():
            if analysis.email_campaign_id in analyses_by_campaign:
                continue
            result = json.loads(analysis.result_json) if analysis.result_json else {}
            primary_cta = result.get("primary_cta") if isinstance(result, dict) else {}
            primary_cta = primary_cta if isinstance(primary_cta, dict) else {}
            analyses_by_campaign[analysis.email_campaign_id] = {
                "summary": result.get("summary"),
                "primary_cta_text": primary_cta.get("text"),
                "primary_cta_url": primary_cta.get("url"),
                "campaign_intent": result.get("campaign_intent"),
                "offer_type": result.get("offer_type"),
                "audience_action": result.get("audience_action"),
                "has_clear_cta": result.get("has_clear_cta"),
                "confidence": result.get("confidence"),
                "analysis_available": True,
            }
        return analyses_by_campaign

    def get_active_email_accounts(
        self, *, provider: str | None = None, account_id: str | None = None
    ) -> list[EmailAccount]:
        statement = select(EmailAccount).where(EmailAccount.is_active.is_(True))
        if provider is not None:
            statement = statement.where(EmailAccount.provider == provider)
        if account_id is not None:
            statement = statement.where(EmailAccount.account_id == account_id)
        return list(self.session.scalars(statement.order_by(EmailAccount.name)).all())

    def account_has_campaigns(self, account_id: str) -> bool:
        return (
            self.session.scalars(
                select(EmailCampaign.campaign_id)
                .where(EmailCampaign.account_id == account_id)
                .limit(1)
            ).first()
            is not None
        )

    def upsert_campaign(
        self,
        *,
        account: EmailAccount,
        external_campaign_id: str,
        name: str,
        subject: str | None,
        sent_at_utc,
        status: str,
    ) -> EmailCampaign:
        now = utc_now()
        campaign = self.session.scalars(
            select(EmailCampaign).where(
                EmailCampaign.account_id == account.account_id,
                EmailCampaign.provider == account.provider,
                EmailCampaign.external_campaign_id == external_campaign_id,
            )
        ).first()
        if campaign is None:
            campaign = EmailCampaign(
                campaign_id=new_id(),
                account_id=account.account_id,
                provider=account.provider,
                external_campaign_id=external_campaign_id,
                name=name,
                subject=subject,
                sent_at_utc=sent_at_utc,
                status=status,
                created_at_utc=now,
                updated_at_utc=now,
            )
            self.session.add(campaign)
            return campaign

        campaign.name = name
        campaign.subject = subject
        campaign.sent_at_utc = sent_at_utc
        campaign.status = status
        campaign.updated_at_utc = now
        return campaign

    def upsert_audience_segment(
        self,
        *,
        account: EmailAccount,
        provider_segment_id: str,
        name: str,
        segment_type: str,
        member_count: int | None,
    ) -> EmailAudienceSegment:
        now = utc_now()
        segment = self.session.scalars(
            select(EmailAudienceSegment).where(
                EmailAudienceSegment.email_account_id == account.account_id,
                EmailAudienceSegment.provider_segment_id == provider_segment_id,
                EmailAudienceSegment.segment_type == segment_type,
            )
        ).first()
        if segment is None:
            segment = EmailAudienceSegment(
                id=new_id(),
                email_account_id=account.account_id,
                provider_segment_id=provider_segment_id,
                name=name,
                segment_type=segment_type,
                member_count=member_count,
                created_at_utc=now,
                updated_at_utc=now,
            )
            self.session.add(segment)
            return segment

        segment.name = name
        segment.member_count = member_count
        segment.updated_at_utc = now
        return segment

    def link_campaign_to_audience_segment(
        self,
        *,
        campaign_id: str,
        audience_segment_id: str,
    ) -> EmailCampaignAudienceSegment:
        for pending in self.session.new:
            if (
                isinstance(pending, EmailCampaignAudienceSegment)
                and pending.email_campaign_id == campaign_id
                and pending.email_audience_segment_id == audience_segment_id
            ):
                return pending

        link = self.session.scalars(
            select(EmailCampaignAudienceSegment).where(
                EmailCampaignAudienceSegment.email_campaign_id == campaign_id,
                EmailCampaignAudienceSegment.email_audience_segment_id == audience_segment_id,
            )
        ).first()
        if link is not None:
            return link

        link = EmailCampaignAudienceSegment(
            id=new_id(),
            email_campaign_id=campaign_id,
            email_audience_segment_id=audience_segment_id,
            created_at_utc=utc_now(),
        )
        self.session.add(link)
        return link

    def replace_campaign_audience_segments(
        self,
        *,
        campaign_id: str,
        audience_segment_ids: list[str],
    ) -> None:
        unique_segment_ids = list(dict.fromkeys(audience_segment_ids))
        self.session.execute(
            delete(EmailCampaignAudienceSegment).where(
                EmailCampaignAudienceSegment.email_campaign_id == campaign_id,
                EmailCampaignAudienceSegment.email_audience_segment_id.not_in(unique_segment_ids),
            )
        )
        for audience_segment_id in unique_segment_ids:
            self.link_campaign_to_audience_segment(
                campaign_id=campaign_id,
                audience_segment_id=audience_segment_id,
            )

    def insert_campaign_metric_snapshot(
        self,
        *,
        campaign_id: str,
        captured_at_utc,
        emails_sent: int | None,
        emails_delivered: int | None,
        opens_total: int | None,
        opens_unique: int | None,
        open_rate: float | None,
        clicks_total: int | None,
        clicks_unique: int | None,
        click_rate: float | None,
        unsubscribes: int | None,
        unsubscribe_rate: float | None,
        bounces_total: int | None,
        bounce_rate: float | None,
        spam_complaints: int | None,
        spam_complaint_rate: float | None,
        forwards: int | None,
        revenue: float | None,
        raw_provider_stats: dict[str, Any] | None,
    ) -> CampaignMetricSnapshot:
        snapshot = CampaignMetricSnapshot(
            metric_snapshot_id=new_id(),
            campaign_id=campaign_id,
            captured_at_utc=captured_at_utc,
            emails_sent=emails_sent,
            emails_delivered=emails_delivered,
            opens_total=opens_total,
            opens_unique=opens_unique,
            open_rate=open_rate,
            clicks_total=clicks_total,
            clicks_unique=clicks_unique,
            click_rate=click_rate,
            unsubscribes=unsubscribes,
            unsubscribe_rate=unsubscribe_rate,
            bounces_total=bounces_total,
            bounce_rate=bounce_rate,
            spam_complaints=spam_complaints,
            spam_complaint_rate=spam_complaint_rate,
            forwards=forwards,
            revenue=revenue,
            raw_provider_stats_json=(
                json.dumps(raw_provider_stats, sort_keys=True) if raw_provider_stats else None
            ),
            created_at_utc=utc_now(),
        )
        self.session.add(snapshot)
        return snapshot

    def upsert_email_campaign_content(
        self,
        *,
        campaign_id: str,
        subject: str | None,
        preheader: str | None,
        from_name: str | None,
        from_email: str | None,
        reply_to_email: str | None,
        html_body: str | None,
        text_body: str | None,
        content_source: str | None,
        content_fetched_at_utc,
        provider_content_id: str | None,
        raw_content_metadata: dict[str, Any] | None,
    ) -> EmailCampaignContent:
        now = utc_now()
        content = next(
            (
                pending
                for pending in self.session.new
                if isinstance(pending, EmailCampaignContent)
                and pending.email_campaign_id == campaign_id
            ),
            None,
        )
        if content is None:
            content = self.session.scalars(
                select(EmailCampaignContent).where(
                    EmailCampaignContent.email_campaign_id == campaign_id
                )
            ).first()
        if content is None:
            content = EmailCampaignContent(
                id=new_id(),
                email_campaign_id=campaign_id,
                created_at_utc=now,
                updated_at_utc=now,
                subject=subject,
                preheader=preheader,
                from_name=from_name,
                from_email=from_email,
                reply_to_email=reply_to_email,
                html_body=html_body,
                text_body=text_body,
                content_source=content_source,
                content_fetched_at_utc=content_fetched_at_utc,
                provider_content_id=provider_content_id,
                raw_content_metadata_json=(
                    json.dumps(raw_content_metadata, sort_keys=True)
                    if raw_content_metadata
                    else None
                ),
            )
            self.session.add(content)
            return content

        content.subject = subject
        content.preheader = preheader
        content.from_name = from_name
        content.from_email = from_email
        content.reply_to_email = reply_to_email
        content.html_body = html_body
        content.text_body = text_body
        content.content_source = content_source
        content.content_fetched_at_utc = content_fetched_at_utc
        content.provider_content_id = provider_content_id
        content.raw_content_metadata_json = (
            json.dumps(raw_content_metadata, sort_keys=True) if raw_content_metadata else None
        )
        content.updated_at_utc = now
        return content

    def get_email_campaign_content_by_id(self, content_id: str) -> EmailCampaignContent | None:
        return self.session.get(EmailCampaignContent, content_id)

    def get_content_analysis(
        self, content_id: str, prompt_key: str, prompt_version: str
    ) -> EmailCampaignContentAnalysis | None:
        return self.session.scalars(
            select(EmailCampaignContentAnalysis).where(
                EmailCampaignContentAnalysis.email_campaign_content_id == content_id,
                EmailCampaignContentAnalysis.prompt_key == prompt_key,
                EmailCampaignContentAnalysis.prompt_version == prompt_version,
            )
        ).first()

    def _audience_segments_by_campaign(
        self,
        campaign_ids: list[str],
    ) -> dict[str, list[AudienceSegmentPerformance]]:
        unique_campaign_ids = list(dict.fromkeys(campaign_ids))
        if not unique_campaign_ids:
            return {}

        statement = (
            select(EmailCampaignAudienceSegment.email_campaign_id, EmailAudienceSegment)
            .join(
                EmailAudienceSegment,
                EmailAudienceSegment.id
                == EmailCampaignAudienceSegment.email_audience_segment_id,
            )
            .where(EmailCampaignAudienceSegment.email_campaign_id.in_(unique_campaign_ids))
            .order_by(EmailAudienceSegment.name.asc())
        )
        segments_by_campaign: dict[str, list[AudienceSegmentPerformance]] = {
            campaign_id: [] for campaign_id in unique_campaign_ids
        }
        for campaign_id, segment in self.session.execute(statement).all():
            segments_by_campaign[campaign_id].append(
                AudienceSegmentPerformance(
                    name=segment.name,
                    segment_type=segment.segment_type,
                    member_count=segment.member_count,
                )
            )
        return segments_by_campaign

    def recent_campaigns(self, limit: int = 10) -> list[EmailCampaign]:
        return list(
            self.session.scalars(
                select(EmailCampaign).order_by(EmailCampaign.sent_at_utc.desc()).limit(limit)
            ).all()
        )

    def metrics_for_campaign(self, campaign_id: str) -> list[CampaignMetricSnapshot]:
        return list(
            self.session.scalars(
                select(CampaignMetricSnapshot).where(
                    CampaignMetricSnapshot.campaign_id == campaign_id
                )
            ).all()
        )
