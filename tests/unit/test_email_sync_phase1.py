from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from ape_email_platforms import (
    AudienceSegmentDto,
    CampaignContentDto,
    EmailPlatformAccount,
    NormalisedCampaign,
    NormalisedCampaignStats,
)
from ape_email_platforms.factory import create_email_platform_client
from ape_email_platforms.http import EmailPlatformApiError
from ape_email_platforms.mailchimp_client import MailchimpClient
from ape_email_platforms.mailerlite_client import MailerLiteClient
from ape_email_platforms.transpond_client import TranspondClient
from ape_sdk.common.encryption import get_secret_encryption_provider
from ape_sdk.common.ids import new_id
from ape_sdk.database.models import (
    Base,
    CampaignMetricSnapshot,
    EmailAccount,
    EmailAudienceSegment,
    EmailCampaign,
    EmailCampaignAudienceSegment,
    EmailCampaignContent,
    SyncRun,
)
from ape_sdk.database.repositories.campaigns import CampaignRepository
from ape_sdk.messages.commands import RunEmailDataSync
from ape_sdk.messages.envelope import MessageEnvelope
from ape_sdk.messages.routing import (
    ANALYSE_CAMPAIGN_CONTENT,
    COMMANDS_EXCHANGE,
    EMAIL_DATA_SYNC_COMPLETED,
    EMAIL_DATA_SYNC_FAILED,
    EVENTS_EXCHANGE,
)
from email_sync_worker.handlers import (
    AccountSyncStatus,
    AllAccountsFailedError,
    EmailSyncHandler,
)
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker


class RecordingPublisher:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str, MessageEnvelope]] = []

    def publish(self, exchange: str, routing_key: str, envelope: MessageEnvelope) -> None:
        self.messages.append((exchange, routing_key, envelope))


class RecordingClient:
    def __init__(self, audience_segments: list[AudienceSegmentDto] | None = None) -> None:
        self.sent_since_values: list[datetime] = []
        self.accounts: list[EmailPlatformAccount] = []
        self.audience_segments = audience_segments or []

    def get_sent_campaigns(
        self,
        account: EmailPlatformAccount,
        sent_since: datetime,
    ) -> list[NormalisedCampaign]:
        self.accounts.append(account)
        self.sent_since_values.append(sent_since)
        return [
            NormalisedCampaign(
                provider=account.provider,
                external_id="campaign-1",
                name="Campaign One",
                subject="Hello",
                sent_at_utc=sent_since,
                status="sent",
                audience_segments=self.audience_segments,
            )
        ]

    def get_campaign_stats(
        self,
        account: EmailPlatformAccount,
        campaign_external_id: str,
    ) -> NormalisedCampaignStats:
        return NormalisedCampaignStats(
            external_campaign_id=campaign_external_id,
            captured_at_utc=datetime(2026, 1, 1, tzinfo=UTC),
            emails_sent=10,
            opens_unique=5,
            open_rate=0.5,
            clicks_unique=2,
            click_rate=0.2,
            raw_provider_stats={"source": "test"},
        )



    def get_campaign_content(
        self,
        account: EmailPlatformAccount,
        campaign: NormalisedCampaign,
    ) -> CampaignContentDto | None:
        return CampaignContentDto(
            campaign_external_id=campaign.external_id,
            subject=campaign.subject,
            html_body="<html>Hello</html>",
            text_body="Hello",
            content_source="mailerlite_campaign_response",
            fetched_at_utc=datetime(2026, 1, 1, tzinfo=UTC),
        )

class FailingClient(RecordingClient):
    def get_sent_campaigns(
        self,
        account: EmailPlatformAccount,
        sent_since: datetime,
    ) -> list[NormalisedCampaign]:
        raise RuntimeError("provider unavailable")


@pytest.fixture
def session_factory() -> Callable[[], Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def seed_account(
    session: Session,
    *,
    api_key: str = "db-secret",
    provider: str = "mailerlite",
    name: str = "Test Account",
) -> EmailAccount:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    encryption = get_secret_encryption_provider()
    account = EmailAccount(
        account_id=new_id(),
        provider=provider,
        external_account_id=None,
        name=name,
        api_key_encrypted=encryption.encrypt(api_key),
        is_active=True,
        created_at_utc=now,
        updated_at_utc=now,
    )
    session.add(account)
    session.commit()
    return account


def run_handler(
    session_factory: Callable[[], Session],
    client: RecordingClient,
    command: RunEmailDataSync | None = None,
) -> RecordingPublisher:
    publisher = RecordingPublisher()
    handler = EmailSyncHandler(
        publisher,  # type: ignore[arg-type]
        session_factory,
        client_factory=lambda provider: client,
    )
    handler.handle(MessageEnvelope.wrap(command or RunEmailDataSync()))
    return publisher


def test_first_sync_uses_28_day_lookback(session_factory: Callable[[], Session]) -> None:
    with session_factory() as session:
        seed_account(session)

    client = RecordingClient()
    run_handler(session_factory, client)

    lookback = datetime.now(UTC) - client.sent_since_values[0]
    assert 27 <= lookback.days <= 28


def test_subsequent_sync_uses_7_day_lookback(session_factory: Callable[[], Session]) -> None:
    with session_factory() as session:
        account = seed_account(session)
        session.add(
            EmailCampaign(
                campaign_id=new_id(),
                account_id=account.account_id,
                provider=account.provider,
                external_campaign_id="existing",
                name="Existing",
                subject=None,
                sent_at_utc=datetime(2026, 1, 1, tzinfo=UTC),
                status="sent",
                created_at_utc=datetime(2026, 1, 1, tzinfo=UTC),
                updated_at_utc=datetime(2026, 1, 1, tzinfo=UTC),
            )
        )
        session.commit()

    client = RecordingClient()
    run_handler(session_factory, client)

    lookback = datetime.now(UTC) - client.sent_since_values[0]
    assert 6 <= lookback.days <= 7


def test_campaign_upsert_does_not_duplicate_existing_campaign(
    session_factory: Callable[[], Session],
) -> None:
    with session_factory() as session:
        seed_account(session)

    client = RecordingClient()
    run_handler(session_factory, client)
    run_handler(session_factory, client)

    with session_factory() as session:
        campaigns = list(session.scalars(select(EmailCampaign)).all())
        assert len(campaigns) == 1


def test_metric_snapshots_are_timestamped_records(
    session_factory: Callable[[], Session],
) -> None:
    with session_factory() as session:
        seed_account(session)

    client = RecordingClient()
    run_handler(session_factory, client)
    run_handler(session_factory, client)

    with session_factory() as session:
        snapshots = list(session.scalars(select(CampaignMetricSnapshot)).all())
        assert len(snapshots) == 2
        assert all(snapshot.captured_at_utc is not None for snapshot in snapshots)


def test_sync_publishes_analyse_campaign_content_per_saved_content(
    session_factory: Callable[[], Session],
) -> None:
    with session_factory() as session:
        seed_account(session)
    client = RecordingClient()
    publisher = run_handler(session_factory, client)
    assert any(
        exchange == COMMANDS_EXCHANGE and routing_key == ANALYSE_CAMPAIGN_CONTENT
        for exchange, routing_key, _ in publisher.messages
    )


def test_repository_upserts_audience_segment(
    session_factory: Callable[[], Session],
) -> None:
    with session_factory() as session:
        account = seed_account(session)
        repository = CampaignRepository(session)

        first = repository.upsert_audience_segment(
            account=account,
            provider_segment_id="group-1",
            name="VIP Customers",
            segment_type="mailerlite_group",
            member_count=1200,
        )
        session.flush()
        second = repository.upsert_audience_segment(
            account=account,
            provider_segment_id="group-1",
            name="VIP Guests",
            segment_type="mailerlite_group",
            member_count=1300,
        )
        session.commit()

        assert first.id == second.id
        assert second.name == "VIP Guests"
        assert second.member_count == 1300


def test_repository_links_campaign_to_audience_segment_without_duplicates(
    session_factory: Callable[[], Session],
) -> None:
    with session_factory() as session:
        account = seed_account(session)
        repository = CampaignRepository(session)
        campaign = repository.upsert_campaign(
            account=account,
            external_campaign_id="campaign-1",
            name="Campaign",
            subject=None,
            sent_at_utc=datetime(2026, 1, 1, tzinfo=UTC),
            status="sent",
        )
        segment = repository.upsert_audience_segment(
            account=account,
            provider_segment_id="group-1",
            name="VIP Customers",
            segment_type="mailerlite_group",
            member_count=None,
        )
        session.flush()

        repository.link_campaign_to_audience_segment(
            campaign_id=campaign.campaign_id,
            audience_segment_id=segment.id,
        )
        repository.link_campaign_to_audience_segment(
            campaign_id=campaign.campaign_id,
            audience_segment_id=segment.id,
        )
        session.commit()

        links = list(session.scalars(select(EmailCampaignAudienceSegment)).all())
        assert len(links) == 1


def test_campaign_sync_stores_audience_segment_data(
    session_factory: Callable[[], Session],
) -> None:
    with session_factory() as session:
        seed_account(session)

    client = RecordingClient(
        [
            AudienceSegmentDto(
                provider_segment_id="group-1",
                name="VIP Customers",
                segment_type="mailerlite_group",
                member_count=1200,
            )
        ]
    )
    run_handler(session_factory, client)

    with session_factory() as session:
        segment = session.scalars(select(EmailAudienceSegment)).one()
        links = list(session.scalars(select(EmailCampaignAudienceSegment)).all())
        assert segment.name == "VIP Customers"
        assert segment.segment_type == "mailerlite_group"
        assert segment.member_count == 1200
        assert len(links) == 1


def test_campaign_sync_succeeds_without_audience_segment_data(
    session_factory: Callable[[], Session],
) -> None:
    with session_factory() as session:
        seed_account(session)

    publisher = run_handler(session_factory, RecordingClient())

    assert publisher.messages[0][1] == EMAIL_DATA_SYNC_COMPLETED
    with session_factory() as session:
        assert session.scalars(select(EmailCampaign)).one()
        assert list(session.scalars(select(EmailAudienceSegment)).all()) == []


def test_provider_factory_returns_correct_client() -> None:
    assert isinstance(create_email_platform_client("mailerlite"), MailerLiteClient)
    assert isinstance(create_email_platform_client("mailchimp"), MailchimpClient)
    assert isinstance(create_email_platform_client("transpond"), TranspondClient)


def test_unknown_provider_raises_clear_error() -> None:
    with pytest.raises(ValueError, match="Unsupported email provider"):
        create_email_platform_client("unknown")


def test_handler_publishes_completed_event_on_success(
    session_factory: Callable[[], Session],
) -> None:
    with session_factory() as session:
        seed_account(session)

    publisher = run_handler(session_factory, RecordingClient())

    assert publisher.messages[0][0] == EVENTS_EXCHANGE
    assert publisher.messages[0][1] == EMAIL_DATA_SYNC_COMPLETED
    assert publisher.messages[0][2].payload["accounts_processed"] == 1
    assert publisher.messages[0][2].payload["metric_snapshots_created"] == 1


def test_handler_publishes_failed_event_on_failure(
    session_factory: Callable[[], Session],
) -> None:
    with session_factory() as session:
        seed_account(session)

    publisher = RecordingPublisher()
    handler = EmailSyncHandler(
        publisher,  # type: ignore[arg-type]
        session_factory,
        client_factory=lambda provider: FailingClient(),
    )

    with pytest.raises(AllAccountsFailedError, match="all email campaign account syncs failed"):
        handler.handle(MessageEnvelope.wrap(RunEmailDataSync()))

    assert publisher.messages[0][1] == EMAIL_DATA_SYNC_FAILED
    assert (
        publisher.messages[0][2].payload["error_message"]
        == "all email campaign account syncs failed"
    )
    with session_factory() as session:
        run = session.scalars(select(SyncRun)).one()
        assert run.status == "failed"


def test_api_key_is_loaded_from_email_account_record(
    session_factory: Callable[[], Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MAILERLITE_API_KEY", "env-secret")
    with session_factory() as session:
        seed_account(session, api_key="db-secret")

    client = RecordingClient()
    run_handler(session_factory, client)

    assert client.accounts[0].api_key == "db-secret"
    assert client.accounts[0].api_key != "env-secret"


def test_repository_upsert_returns_same_campaign_for_same_external_id(
    session_factory: Callable[[], Session],
) -> None:
    with session_factory() as session:
        account = seed_account(session)
        repository = CampaignRepository(session)
        first = repository.upsert_campaign(
            account=account,
            external_campaign_id="same",
            name="First",
            subject=None,
            sent_at_utc=datetime(2026, 1, 1, tzinfo=UTC),
            status="sent",
        )
        session.flush()
        second = repository.upsert_campaign(
            account=account,
            external_campaign_id="same",
            name="Second",
            subject=None,
            sent_at_utc=datetime(2026, 1, 1, tzinfo=UTC),
            status="sent",
        )
        session.commit()

        assert first.campaign_id == second.campaign_id
        assert second.name == "Second"


def test_repository_upserts_campaign_content(session_factory: Callable[[], Session]) -> None:
    with session_factory() as session:
        account = seed_account(session)
        repository = CampaignRepository(session)
        campaign = repository.upsert_campaign(
            account=account,
            external_campaign_id="campaign-content",
            name="Campaign",
            subject="Subject",
            sent_at_utc=datetime(2026, 1, 1, tzinfo=UTC),
            status="sent",
        )
        session.flush()
        first = repository.upsert_email_campaign_content(
            campaign_id=campaign.campaign_id,
            subject="Subject",
            preheader=None,
            from_name=None,
            from_email=None,
            reply_to_email=None,
            html_body=None,
            text_body="Text",
            content_source="unknown",
            content_fetched_at_utc=datetime(2026, 1, 1, tzinfo=UTC),
            provider_content_id=None,
            raw_content_metadata=None,
        )
        second = repository.upsert_email_campaign_content(
            campaign_id=campaign.campaign_id,
            subject="Subject 2",
            preheader=None,
            from_name=None,
            from_email=None,
            reply_to_email=None,
            html_body="<p>x</p>",
            text_body="Text 2",
            content_source="mailchimp_campaign_content_endpoint",
            content_fetched_at_utc=datetime(2026, 1, 2, tzinfo=UTC),
            provider_content_id=None,
            raw_content_metadata={"a": 1},
        )
        session.commit()
        assert first.id == second.id


def test_campaign_sync_saves_campaign_content(session_factory: Callable[[], Session]) -> None:
    with session_factory() as session:
        seed_account(session)
    client = RecordingClient()
    run_handler(session_factory, client)
    with session_factory() as session:
        rows = list(session.scalars(select(EmailCampaignContent)).all())
        assert len(rows) == 1
        assert rows[0].text_body == "Hello"


class MixedOutcomeClient(RecordingClient):
    def __init__(self, failing_account_names: set[str]) -> None:
        super().__init__()
        self.failing_account_names = failing_account_names

    def get_sent_campaigns(
        self,
        account: EmailPlatformAccount,
        sent_since: datetime,
    ) -> list[NormalisedCampaign]:
        self.accounts.append(account)
        self.sent_since_values.append(sent_since)
        if account.account_name in self.failing_account_names:
            raise EmailPlatformApiError(
                "Email platform API returned HTTP 403 api_key=provider-secret"
            )
        return [
            NormalisedCampaign(
                provider=account.provider,
                external_id=f"campaign-{account.account_id}",
                name=f"Campaign {account.account_name}",
                subject="Hello",
                sent_at_utc=sent_since,
                status="sent",
                audience_segments=[],
            )
        ]


class CountingSession(Session):
    rollback_calls = 0

    def rollback(self) -> None:
        CountingSession.rollback_calls += 1
        super().rollback()


def test_one_failed_account_does_not_stop_remaining_accounts(
    session_factory: Callable[[], Session],
) -> None:
    with session_factory() as session:
        seed_account(session, provider="mailchimp", name="Bad Mailchimp")
        seed_account(session, provider="mailerlite", name="Good MailerLite")

    client = MixedOutcomeClient({"Bad Mailchimp"})
    publisher = run_handler(session_factory, client)

    assert [account.account_name for account in client.accounts] == [
        "Bad Mailchimp",
        "Good MailerLite",
    ]
    assert any(routing_key == EMAIL_DATA_SYNC_COMPLETED for _, routing_key, _ in publisher.messages)
    assert not any(
        routing_key == EMAIL_DATA_SYNC_FAILED for _, routing_key, _ in publisher.messages
    )
    with session_factory() as session:
        campaigns = list(session.scalars(select(EmailCampaign)).all())
        assert len(campaigns) == 1
        assert campaigns[0].name == "Campaign Good MailerLite"


def test_account_results_capture_success_and_failure(
    session_factory: Callable[[], Session],
) -> None:
    with session_factory() as session:
        seed_account(session, provider="mailchimp", name="Bad Mailchimp")
        seed_account(session, provider="mailerlite", name="Good MailerLite")

    client = MixedOutcomeClient({"Bad Mailchimp"})
    publisher = RecordingPublisher()
    handler = EmailSyncHandler(
        publisher,  # type: ignore[arg-type]
        session_factory,
        client_factory=lambda provider: client,
    )

    with session_factory() as session:
        summary = handler._run_sync(
            session,
            CampaignRepository(session),
            RunEmailDataSync(tenant_key="bite-demo"),
            "correlation-1",
        )

    assert summary.accounts_total == 2
    assert summary.accounts_succeeded == 1
    assert summary.accounts_failed == 1
    assert summary.campaigns_found == 1
    assert summary.campaigns_created == 1
    assert summary.campaigns_updated == 0
    assert [result.status for result in summary.account_results] == [
        AccountSyncStatus.FAILED,
        AccountSyncStatus.SUCCEEDED,
    ]
    failed = summary.account_results[0]
    assert failed.error_type == "EmailPlatformApiError"
    assert failed.error_message == "Email platform API returned HTTP 403 api_key=<redacted>"


def test_all_accounts_failed_raises_and_publishes_failed_event(
    session_factory: Callable[[], Session],
) -> None:
    with session_factory() as session:
        seed_account(session, provider="mailchimp", name="Bad Mailchimp")
        seed_account(session, provider="mailerlite", name="Bad MailerLite")

    publisher = RecordingPublisher()
    handler = EmailSyncHandler(
        publisher,  # type: ignore[arg-type]
        session_factory,
        client_factory=lambda provider: MixedOutcomeClient({"Bad Mailchimp", "Bad MailerLite"}),
    )

    with pytest.raises(AllAccountsFailedError):
        handler.handle(MessageEnvelope.wrap(RunEmailDataSync()))

    assert publisher.messages[0][1] == EMAIL_DATA_SYNC_FAILED
    assert not any(
        routing_key == EMAIL_DATA_SYNC_COMPLETED for _, routing_key, _ in publisher.messages
    )


def test_no_accounts_is_acked_as_completed_no_op(session_factory: Callable[[], Session]) -> None:
    publisher = run_handler(session_factory, RecordingClient())

    assert publisher.messages[0][1] == EMAIL_DATA_SYNC_COMPLETED
    assert publisher.messages[0][2].payload["accounts_processed"] == 0
    assert publisher.messages[0][2].payload["campaigns_found"] == 0


def test_session_rollback_is_called_after_account_failure() -> None:
    CountingSession.rollback_calls = 0
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
        class_=CountingSession,
    )
    with factory() as session:
        seed_account(session, provider="mailchimp", name="Bad Mailchimp")
        seed_account(session, provider="mailerlite", name="Good MailerLite")

    run_handler(factory, MixedOutcomeClient({"Bad Mailchimp"}))

    assert CountingSession.rollback_calls >= 1


def test_provider_api_secrets_are_not_logged_for_account_failure(
    session_factory: Callable[[], Session],
    caplog: pytest.LogCaptureFixture,
) -> None:
    with session_factory() as session:
        seed_account(session, provider="mailchimp", name="Bad Mailchimp")
        seed_account(session, provider="mailerlite", name="Good MailerLite")

    run_handler(session_factory, MixedOutcomeClient({"Bad Mailchimp"}))

    assert "provider-secret" not in caplog.text
    assert "api_key=<redacted>" in caplog.text
