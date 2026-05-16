from sqlalchemy import select
from sqlalchemy.orm import Session

from ape_sdk.common.ids import new_id
from ape_sdk.common.time import utc_now
from ape_sdk.database.models import SyncRun


class SyncRunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def start(
        self, provider: str | None = None, *, triggered_by_message_id: str | None = None
    ) -> SyncRun:
        now = utc_now()
        run = SyncRun(
            sync_run_id=new_id(),
            provider=provider,
            started_at_utc=now,
            completed_at_utc=None,
            status="running",
            triggered_by_message_id=triggered_by_message_id,
            accounts_processed=0,
            campaigns_found=0,
            campaigns_upserted=0,
            metric_snapshots_created=0,
            error_message=None,
            created_at_utc=now,
        )
        self.session.add(run)
        return run

    def get(self, sync_run_id: str) -> SyncRun | None:
        return self.session.scalars(
            select(SyncRun).where(SyncRun.sync_run_id == sync_run_id)
        ).first()

    def complete(
        self,
        run: SyncRun,
        *,
        accounts_processed: int = 0,
        campaigns_found: int = 0,
        campaigns_upserted: int = 0,
        metric_snapshots_created: int = 0,
    ) -> None:
        run.completed_at_utc = utc_now()
        run.status = "completed"
        run.accounts_processed = accounts_processed
        run.campaigns_found = campaigns_found
        run.campaigns_upserted = campaigns_upserted
        run.metric_snapshots_created = metric_snapshots_created

    def fail(self, run: SyncRun, error_message: str) -> None:
        run.completed_at_utc = utc_now()
        run.status = "failed"
        run.error_message = error_message
