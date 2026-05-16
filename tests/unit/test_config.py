from ape_sdk.common.config import (
    CLIENT_PERFORMANCE_REVIEW_WORKFLOW,
    DAILY_CAMPAIGN_REPORT_WORKFLOW,
    MONTHLY_EMAIL_REPORT_WORKFLOW,
    TELEGRAM_CHAT_WORKFLOW,
    WEEKLY_EMAIL_REPORT_WORKFLOW,
    Settings,
)


def _settings(monkeypatch, **env: str) -> Settings:
    names = [
        "OPENAI_MODEL",
        "BITE_AI_MODEL_TELEGRAM_CHAT",
        "BITE_AI_MODEL_DAILY_CAMPAIGN_REPORT",
        "BITE_AI_MODEL_WEEKLY_EMAIL_REPORT",
        "BITE_AI_MODEL_MONTHLY_EMAIL_REPORT",
        "BITE_AI_MODEL_CLIENT_PERFORMANCE_REVIEW",
    ]
    for name in names:
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return Settings(_env_file=None)


def test_openai_model_for_workflow_uses_telegram_chat_override(monkeypatch) -> None:
    settings = _settings(
        monkeypatch,
        OPENAI_MODEL="gpt-fallback",
        BITE_AI_MODEL_TELEGRAM_CHAT="gpt-telegram",
    )

    assert settings.openai_model_for_workflow(TELEGRAM_CHAT_WORKFLOW) == "gpt-telegram"


def test_openai_model_for_workflow_uses_daily_campaign_report_override(monkeypatch) -> None:
    settings = _settings(
        monkeypatch,
        OPENAI_MODEL="gpt-fallback",
        BITE_AI_MODEL_DAILY_CAMPAIGN_REPORT="gpt-daily",
    )

    assert settings.openai_model_for_workflow(DAILY_CAMPAIGN_REPORT_WORKFLOW) == "gpt-daily"


def test_openai_model_for_workflow_uses_future_workflow_overrides(monkeypatch) -> None:
    settings = _settings(
        monkeypatch,
        OPENAI_MODEL="gpt-fallback",
        BITE_AI_MODEL_WEEKLY_EMAIL_REPORT="gpt-weekly",
        BITE_AI_MODEL_MONTHLY_EMAIL_REPORT="gpt-monthly",
        BITE_AI_MODEL_CLIENT_PERFORMANCE_REVIEW="gpt-client-review",
    )

    assert settings.openai_model_for_workflow(WEEKLY_EMAIL_REPORT_WORKFLOW) == "gpt-weekly"
    assert settings.openai_model_for_workflow(MONTHLY_EMAIL_REPORT_WORKFLOW) == "gpt-monthly"
    assert (
        settings.openai_model_for_workflow(CLIENT_PERFORMANCE_REVIEW_WORKFLOW)
        == "gpt-client-review"
    )


def test_openai_model_for_workflow_unknown_workflow_falls_back_to_openai_model(
    monkeypatch,
) -> None:
    settings = _settings(monkeypatch, OPENAI_MODEL="gpt-fallback")

    assert settings.openai_model_for_workflow("new_workflow") == "gpt-fallback"


def test_openai_model_for_workflow_blank_override_falls_back_to_openai_model(
    monkeypatch,
) -> None:
    settings = _settings(
        monkeypatch,
        OPENAI_MODEL="gpt-fallback",
        BITE_AI_MODEL_TELEGRAM_CHAT=" ",
    )

    assert settings.openai_model_for_workflow(TELEGRAM_CHAT_WORKFLOW) == "gpt-fallback"


def test_openai_model_for_workflow_preserves_existing_openai_model_behaviour(
    monkeypatch,
) -> None:
    settings = _settings(monkeypatch, OPENAI_MODEL="gpt-existing")

    assert settings.openai_model_for_workflow(TELEGRAM_CHAT_WORKFLOW) == "gpt-existing"


def test_openai_model_for_workflow_uses_application_default_when_unset(
    monkeypatch,
) -> None:
    settings = _settings(monkeypatch)

    assert settings.openai_model_for_workflow(TELEGRAM_CHAT_WORKFLOW) == "gpt-5.5"
