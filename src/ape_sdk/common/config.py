from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

TELEGRAM_CHAT_WORKFLOW = "telegram_chat"
DAILY_CAMPAIGN_REPORT_WORKFLOW = "daily_campaign_report"
WEEKLY_EMAIL_REPORT_WORKFLOW = "weekly_email_report"
MONTHLY_EMAIL_REPORT_WORKFLOW = "monthly_email_report"
CLIENT_PERFORMANCE_REVIEW_WORKFLOW = "client_performance_review"

WORKFLOW_MODEL_SETTINGS = {
    TELEGRAM_CHAT_WORKFLOW: "bite_ai_model_telegram_chat",
    DAILY_CAMPAIGN_REPORT_WORKFLOW: "bite_ai_model_daily_campaign_report",
    WEEKLY_EMAIL_REPORT_WORKFLOW: "bite_ai_model_weekly_email_report",
    MONTHLY_EMAIL_REPORT_WORKFLOW: "bite_ai_model_monthly_email_report",
    CLIENT_PERFORMANCE_REVIEW_WORKFLOW: "bite_ai_model_client_performance_review",
}


def _find_repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "scripts" / "dev").is_dir() and (parent / "packages").is_dir():
            return parent
    return Path.cwd()


def _settings_env_file() -> tuple[Path, ...]:
    repo_root = _find_repo_root()
    env_local = repo_root / ".env.local"
    env = repo_root / ".env"
    if env_local.exists():
        return (env_local,)
    if env.exists():
        return (env,)
    return (env_local, env)


class Settings(BaseSettings):
    app_env: str = "development"
    log_level: str = "INFO"

    rabbitmq_host: str = "rabbitmq"
    rabbitmq_port: int = 5672
    rabbitmq_username: str = "guest"
    rabbitmq_password: str = "guest"
    rabbitmq_vhost: str = "/"

    mysql_host: str = "mysql"
    mysql_port: int = 3306
    mysql_database: str = "bite"
    mysql_user: str = "bite"
    mysql_password: str = "bite"

    openai_api_key: str = ""
    openai_model: str = "gpt-5.5"
    bite_ai_model_telegram_chat: str = ""
    bite_ai_model_daily_campaign_report: str = ""
    bite_ai_model_weekly_email_report: str = ""
    bite_ai_model_monthly_email_report: str = ""
    bite_ai_model_client_performance_review: str = ""
    bite_data_mcp_server_url: str = "http://localhost:8000/mcp"
    bite_data_mcp_server_label: str = "bite_data"
    bite_mcp_require_approval: str = "never"
    mcp_transport: str = "streamable-http"
    mcp_host: str = "0.0.0.0"
    mcp_port: int = 8000
    mcp_path: str = "/mcp"
    mcp_allowed_hosts: str = (
        "127.0.0.1:*,localhost:*,[::1]:*,"
        "bite-data-mcp-server:8000,bite-mcp.artrue.co.uk,bite-mcp.artrue.co.uk:*"
    )
    mcp_allowed_origins: str = (
        "http://127.0.0.1:*,http://localhost:*,http://[::1]:*,"
        "http://bite-mcp.artrue.co.uk,https://bite-mcp.artrue.co.uk"
    )
    ai_report_use_dummy_response: bool = False
    telegram_bot_token: str = ""
    telegram_parse_mode: str = ""
    telegram_polling_enabled: bool = True
    telegram_poll_interval_seconds: int = 2
    timezone: str = "Europe/London"
    enable_mcp_debug_endpoints: bool = True

    scheduler_timezone: str = "Europe/London"
    email_sync_cron_hour: int = 3
    email_sync_cron_minute: int = 0
    run_email_sync_on_startup: bool = False
    email_sync_startup_delay_seconds: int = 5
    run_daily_report_on_startup: bool = True
    daily_report_startup_delay_seconds: int = 10
    daily_report_cron_hour: int = 9
    daily_report_cron_minute: int = 0
    daily_report_cron_days: str = "mon,tue,wed,thu,fri,sat"
    weekly_email_report_enabled: bool = True
    weekly_email_report_cron_day: str = "mon"
    weekly_email_report_cron_hour: int = 7
    weekly_email_report_cron_minute: int = 30
    run_weekly_email_report_on_startup: bool = False
    weekly_email_report_startup_delay_seconds: int = 20

    resend_api_key: str = ""
    email_from: str = ""
    email_reply_to: str = ""
    email_provider: str = "resend"

    model_config = SettingsConfigDict(
        env_file=_settings_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def openai_model_for_workflow(self, workflow_key: str) -> str:
        return resolve_openai_model(self, workflow_key)


def resolve_openai_model(settings: object, workflow_key: str) -> str:
    setting_name = WORKFLOW_MODEL_SETTINGS.get(workflow_key)
    if setting_name is not None:
        workflow_model = str(getattr(settings, setting_name, "") or "").strip()
        if workflow_model:
            return workflow_model
    configured_model = str(getattr(settings, "openai_model", "") or "").strip()
    if configured_model:
        return configured_model
    return str(Settings.model_fields["openai_model"].default)


@lru_cache
def get_settings() -> Settings:
    return Settings()
