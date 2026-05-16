from datetime import UTC, datetime, timedelta

from ape_sdk.common.ids import new_id
from ape_sdk.database.models import (
    Base,
    CampaignMetricSnapshot,
    EmailAccount,
    EmailAudienceSegment,
    EmailCampaign,
)
from ape_sdk.database.repositories.campaigns import CampaignRepository
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def _setup():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _seed_account(session, name: str):
    now = datetime.now(UTC)
    account = EmailAccount(
        account_id=new_id(),
        provider="mailerlite",
        external_account_id="ext",
        name=name,
        api_key_encrypted="x",
        is_active=True,
        created_at_utc=now,
        updated_at_utc=now,
    )
    session.add(account)
    session.flush()
    return account


def test_campaign_performance_data_empty():
    sf = _setup()
    with sf() as s:
        assert CampaignRepository(s).get_campaign_performance_data(days=7) == []


def test_campaign_performance_data_grouping_sorting_and_latest_snapshot():
    sf = _setup()
    now = datetime.now(UTC)
    with sf() as s:
        a1 = _seed_account(s, "A Client")
        a2 = _seed_account(s, "B Client")
        c1 = _campaign(a1, "c1", "One", "S1", now - timedelta(days=1), now)
        c2 = _campaign(a1, "c2", "Two", "S2", now - timedelta(days=2), now)
        c3 = _campaign(a2, "c3", "Three", "S3", now - timedelta(days=8), now)
        s.add_all([c1, c2, c3])
        s.add(
            _snapshot(
                campaign_id=c1.campaign_id,
                captured_at_utc=now - timedelta(hours=2),
                emails_sent=100,
                open_rate=0.1,
                click_rate=0.01,
                now=now,
            )
        )
        s.add(
            _snapshot(
                campaign_id=c1.campaign_id,
                captured_at_utc=now - timedelta(hours=1),
                emails_sent=110,
                open_rate=0.2,
                click_rate=0.02,
                now=now,
            )
        )
        repo = CampaignRepository(s)
        segment = repo.upsert_audience_segment(
            account=a1,
            provider_segment_id="group-1",
            name="VIP Customers",
            segment_type="mailerlite_group",
            member_count=1200,
        )
        s.flush()
        repo.link_campaign_to_audience_segment(
            campaign_id=c1.campaign_id,
            audience_segment_id=segment.id,
        )
        s.commit()

    with sf() as s:
        groups = CampaignRepository(s).get_campaign_performance_data(days=7)
        assert len(groups) == 1
        assert groups[0].client_name == "A Client"
        assert [c.campaign_external_id for c in groups[0].campaigns] == ["c1", "c2"]
        assert groups[0].campaigns[0].emails_sent == 110
        assert groups[0].campaigns[0].audience_segments[0].name == "VIP Customers"
        assert groups[0].campaigns[0].audience_segments[0].segment_type == "mailerlite_group"
        assert groups[0].campaigns[0].audience_segments[0].member_count == 1200
        assert groups[0].campaigns[1].audience_segments == []
        assert groups[0].campaigns[1].captured_at_utc is None


def test_find_email_account_by_name_case_insensitive_and_partial_and_empty() -> None:
    sf = _setup()
    with sf() as s:
        _seed_account(s, "SSWC")
        _seed_account(s, "Jono Restaurant")
        s.commit()
    with sf() as s:
        repo = CampaignRepository(s)
        assert [a.name for a in repo.find_email_accounts_by_name("sswc")] == ["SSWC"]
        assert [a.name for a in repo.find_email_accounts_by_name("ono")] == ["Jono Restaurant"]
        assert repo.find_email_accounts_by_name("missing") == []


def test_get_campaigns_and_performance_by_account_filters_days_and_latest_snapshot() -> None:
    sf = _setup()
    now = datetime.now(UTC)
    with sf() as s:
        account = _seed_account(s, "SSWC")
        recent_campaign = _campaign(account, "r1", "Recent", "R", now - timedelta(days=1), now)
        old_campaign = _campaign(account, "o1", "Old", "O", now - timedelta(days=100), now)
        s.add_all([recent_campaign, old_campaign])
        s.add(
            _snapshot(
                campaign_id=recent_campaign.campaign_id,
                captured_at_utc=now - timedelta(hours=2),
                emails_sent=100,
                open_rate=0.1,
                click_rate=0.01,
                now=now,
            )
        )
        s.add(
            _snapshot(
                campaign_id=recent_campaign.campaign_id,
                captured_at_utc=now - timedelta(hours=1),
                emails_sent=150,
                open_rate=0.2,
                click_rate=0.02,
                now=now,
            )
        )
        segment = EmailAudienceSegment(
            id=new_id(),
            email_account_id=account.account_id,
            provider_segment_id="g1",
            name="GNR Parking Customers",
            segment_type="mailerlite_group",
            member_count=1240,
            created_at_utc=now,
            updated_at_utc=now,
        )
        s.add(segment)
        s.flush()
        CampaignRepository(s).link_campaign_to_audience_segment(
            campaign_id=recent_campaign.campaign_id, audience_segment_id=segment.id
        )
        s.commit()
    with sf() as s:
        repo = CampaignRepository(s)
        campaigns = repo.get_campaigns_by_account(account.account_id, days=90)
        assert [c.external_campaign_id for c in campaigns] == ["r1"]
        performance = repo.get_campaign_performance_by_account(account.account_id, days=90)
        assert performance is not None
        assert len(performance.campaigns) == 1
        assert performance.campaigns[0].emails_sent == 150
        assert performance.campaigns[0].audience_segments[0].name == "GNR Parking Customers"


def _campaign(
    account: EmailAccount,
    external_campaign_id: str,
    name: str,
    subject: str,
    sent_at_utc: datetime,
    now: datetime,
) -> EmailCampaign:
    return EmailCampaign(
        campaign_id=new_id(),
        account_id=account.account_id,
        provider="mailerlite",
        external_campaign_id=external_campaign_id,
        name=name,
        subject=subject,
        sent_at_utc=sent_at_utc,
        status="sent",
        created_at_utc=now,
        updated_at_utc=now,
    )


def _snapshot(
    *,
    campaign_id: str,
    captured_at_utc: datetime,
    emails_sent: int,
    open_rate: float,
    click_rate: float,
    now: datetime,
) -> CampaignMetricSnapshot:
    return CampaignMetricSnapshot(
        metric_snapshot_id=new_id(),
        campaign_id=campaign_id,
        captured_at_utc=captured_at_utc,
        emails_sent=emails_sent,
        emails_delivered=None,
        opens_total=None,
        opens_unique=None,
        open_rate=open_rate,
        clicks_total=None,
        clicks_unique=None,
        click_rate=click_rate,
        unsubscribes=None,
        unsubscribe_rate=None,
        bounces_total=None,
        bounce_rate=None,
        spam_complaints=None,
        spam_complaint_rate=None,
        forwards=None,
        revenue=None,
        raw_provider_stats_json=None,
        created_at_utc=now,
    )
