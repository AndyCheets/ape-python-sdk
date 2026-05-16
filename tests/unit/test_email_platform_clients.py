from datetime import UTC, datetime
from typing import Any

import pytest
from ape_email_platforms.http import EmailPlatformApiError
from ape_email_platforms.mailchimp_client import MailchimpClient
from ape_email_platforms.mailerlite_client import MailerLiteClient
from ape_email_platforms.models import EmailPlatformAccount
from ape_email_platforms.transpond_client import TranspondClient


class FakeHttpClient:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = responses
        self.requests: list[tuple[str, dict[str, str], dict[str, object] | None]] = []

    def get_json(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, object] | None = None,
        timeout_seconds: int = 30,
    ) -> dict[str, Any]:
        self.requests.append((url, headers or {}, params))
        return self.responses.pop(0)


def test_mailerlite_fetches_sent_campaigns_from_api() -> None:
    http = FakeHttpClient(
        [
            {"data": [], "links": {"next": None}},
            {
                "data": [
                    {
                        "id": "ml-1",
                        "name": "May newsletter",
                        "status": "sent",
                        "emails": [
                            {
                                "subject": "May menu",
                                "sent_at": "2026-05-01 10:00:00",
                            }
                        ],
                    }
                ],
                "links": {"next": None},
            },
            {
                "data": {
                    "id": "ml-1",
                    "name": "May newsletter",
                    "status": "sent",
                    "emails": [
                        {
                            "subject": "May menu",
                            "sent_at": "2026-05-01 10:00:00",
                        }
                    ],
                }
            },
        ]
    )
    client = MailerLiteClient(http)

    campaigns = client.get_sent_campaigns(
        _account("mailerlite", "mailerlite-token"),
        datetime(2026, 4, 30, tzinfo=UTC),
    )

    assert campaigns[0].external_id == "ml-1"
    assert campaigns[0].name == "May newsletter"
    assert campaigns[0].subject == "May menu"
    assert http.requests[0][1]["Authorization"] == "Bearer mailerlite-token"
    assert http.requests[0][0] == "https://connect.mailerlite.com/api/groups"
    assert http.requests[1][2] == {"filter[status]": "sent", "limit": 100, "page": 1}


def test_mailerlite_maps_campaign_group_data() -> None:
    http = FakeHttpClient(
        [
            {"data": [], "links": {"next": None}},
            {
                "data": [
                    {
                        "id": "ml-1",
                        "name": "May newsletter",
                        "status": "sent",
                        "groups": [{"id": "group-1", "name": "VIP Customers", "total": 1200}],
                        "emails": [
                            {
                                "subject": "May menu",
                                "sent_at": "2026-05-01 10:00:00",
                            }
                        ],
                    }
                ],
                "links": {"next": None},
            }
        ]
    )
    client = MailerLiteClient(http)

    campaigns = client.get_sent_campaigns(
        _account("mailerlite", "mailerlite-token"),
        datetime(2026, 4, 30, tzinfo=UTC),
    )

    assert campaigns[0].audience_segments[0].provider_segment_id == "group-1"
    assert campaigns[0].audience_segments[0].name == "VIP Customers"
    assert campaigns[0].audience_segments[0].segment_type == "mailerlite_group"
    assert campaigns[0].audience_segments[0].member_count == 1200


def test_mailerlite_fetches_campaign_detail_and_groups_when_list_has_no_group_data() -> None:
    http = FakeHttpClient(
        [
            {
                "data": [
                    {
                        "id": "42",
                        "name": "VIP Customers",
                        "active_count": 1200,
                    }
                ],
                "links": {"next": None},
            },
            {
                "data": [
                    {
                        "id": "ml-1",
                        "name": "May newsletter",
                        "status": "sent",
                        "emails": [
                            {
                                "subject": "May menu",
                                "sent_at": "2026-05-01 10:00:00",
                            }
                        ],
                    }
                ],
                "links": {"next": None},
            },
            {
                "data": {
                    "id": "ml-1",
                    "name": "May newsletter",
                    "status": "sent",
                    "filter": [
                        [
                            {
                                "operator": "in_any",
                                "args": ["groups", ["42"]],
                            }
                        ]
                    ],
                    "emails": [
                        {
                            "subject": "May menu",
                            "sent_at": "2026-05-01 10:00:00",
                        }
                    ],
                }
            },
        ]
    )
    client = MailerLiteClient(http)

    campaigns = client.get_sent_campaigns(
        _account("mailerlite", "mailerlite-token"),
        datetime(2026, 4, 30, tzinfo=UTC),
    )

    assert campaigns[0].audience_segments[0].provider_segment_id == "42"
    assert campaigns[0].audience_segments[0].name == "VIP Customers"
    assert campaigns[0].audience_segments[0].segment_type == "mailerlite_group"
    assert campaigns[0].audience_segments[0].member_count == 1200
    assert http.requests[0][0] == "https://connect.mailerlite.com/api/groups"
    assert http.requests[2][0] == "https://connect.mailerlite.com/api/campaigns/ml-1"


def test_mailerlite_maps_campaign_stats() -> None:
    http = FakeHttpClient(
        [
            {
                "data": {
                    "id": "ml-1",
                    "emails": [
                        {
                            "stats": {
                                "sent": 100,
                                "opens_count": 80,
                                "unique_opens_count": 60,
                                "open_rate": {"float": 0.6},
                                "clicks_count": 25,
                                "unique_clicks_count": 20,
                                "click_rate": {"float": 0.2},
                                "unsubscribes_count": 1,
                                "hard_bounces_count": 2,
                                "soft_bounces_count": 3,
                                "spam_count": 0,
                                "forwards_count": 4,
                            }
                        }
                    ],
                }
            }
        ]
    )
    client = MailerLiteClient(http)

    stats = client.get_campaign_stats(_account("mailerlite", "token"), "ml-1")

    assert stats.emails_sent == 100
    assert stats.emails_delivered == 95
    assert stats.opens_unique == 60
    assert stats.clicks_unique == 20
    assert stats.bounces_total == 5
    assert stats.forwards == 4


def test_mailchimp_fetches_sent_campaigns_from_datacenter_api() -> None:
    http = FakeHttpClient(
        [
            {"lists": [], "total_items": 0},
            {
                "campaigns": [
                    {
                        "id": "mc-1",
                        "status": "sent",
                        "send_time": "2026-05-01T12:30:00+00:00",
                        "settings": {
                            "title": "Weekly update",
                            "subject_line": "May menu",
                        },
                    }
                ],
                "total_items": 1,
            }
        ]
    )
    client = MailchimpClient(http)

    campaigns = client.get_sent_campaigns(
        _account("mailchimp", "mailchimp-key-us21"),
        datetime(2026, 4, 30, tzinfo=UTC),
    )

    assert campaigns[0].external_id == "mc-1"
    assert campaigns[0].name == "Weekly update"
    assert campaigns[0].subject == "May menu"
    assert http.requests[0][0] == "https://us21.api.mailchimp.com/3.0/lists"
    assert http.requests[1][0] == "https://us21.api.mailchimp.com/3.0/campaigns"
    assert http.requests[1][2]["status"] == "sent"
    assert http.requests[1][2]["since_send_time"] == "2026-04-30T00:00:00+00:00"


def test_mailchimp_maps_list_segment_and_tag_data() -> None:
    http = FakeHttpClient(
        [
            {
                "lists": [
                    {
                        "id": "list-1",
                        "name": "Main Audience",
                        "stats": {"member_count": 2500},
                    }
                ],
                "total_items": 1,
            },
            {
                "segments": [
                    {
                        "id": "segment-1",
                        "name": "Recent Diners",
                        "type": "saved",
                        "member_count": 400,
                    }
                ],
                "total_items": 1,
            },
            {
                "campaigns": [
                    {
                        "id": "mc-1",
                        "status": "sent",
                        "send_time": "2026-05-01T12:30:00+00:00",
                        "settings": {
                            "title": "Weekly update",
                            "subject_line": "May menu",
                        },
                        "recipients": {
                            "list_id": "list-1",
                            "list_name": "Main Audience",
                            "recipient_count": 2500,
                            "segment_opts": {
                                "saved_segment_id": "segment-1",
                                "saved_segment_name": "Recent Diners",
                                "conditions": [
                                    {
                                        "condition_type": "Tags",
                                        "op": "contains",
                                        "field": "VIP",
                                    }
                                ],
                            },
                        },
                    }
                ],
                "total_items": 1,
            }
        ]
    )
    client = MailchimpClient(http)

    campaigns = client.get_sent_campaigns(
        _account("mailchimp", "mailchimp-key-us21"),
        datetime(2026, 4, 30, tzinfo=UTC),
    )

    segments = campaigns[0].audience_segments
    assert [(segment.name, segment.segment_type) for segment in segments] == [
        ("Main Audience", "mailchimp_list"),
        ("Recent Diners", "mailchimp_segment"),
        ("VIP", "mailchimp_tag"),
    ]
    assert segments[0].member_count == 2500
    assert segments[1].member_count == 400
    assert http.requests[0][0] == "https://us21.api.mailchimp.com/3.0/lists"
    assert http.requests[1][0] == "https://us21.api.mailchimp.com/3.0/lists/list-1/segments"
    assert http.requests[2][0] == "https://us21.api.mailchimp.com/3.0/campaigns"


def test_mailchimp_maps_campaign_report_stats() -> None:
    http = FakeHttpClient(
        [
            {
                "emails_sent": 200,
                "unsubscribed": 2,
                "abuse_reports": 1,
                "bounces": {"hard_bounces": 4, "soft_bounces": 6},
                "opens": {
                    "opens_total": 120,
                    "unique_opens": 90,
                    "open_rate": 0.45,
                },
                "clicks": {
                    "clicks_total": 50,
                    "unique_clicks": 35,
                    "click_rate": 0.175,
                },
                "forwards": {"forwards_count": 3},
                "ecommerce": {"total_revenue": 123.45},
            }
        ]
    )
    client = MailchimpClient(http)

    stats = client.get_campaign_stats(_account("mailchimp", "key-us21"), "mc-1")

    assert stats.emails_sent == 200
    assert stats.emails_delivered == 190
    assert stats.opens_unique == 90
    assert stats.click_rate == 0.175
    assert stats.unsubscribe_rate == 0.01
    assert stats.spam_complaints == 1
    assert stats.revenue == 123.45


def test_mailchimp_requires_datacenter_suffix() -> None:
    client = MailchimpClient(FakeHttpClient([]))

    with pytest.raises(EmailPlatformApiError, match="datacenter suffix"):
        client.get_sent_campaigns(
            _account("mailchimp", "missingsuffix"),
            datetime(2026, 4, 30, tzinfo=UTC),
        )


def _account(provider: str, api_key: str) -> EmailPlatformAccount:
    return EmailPlatformAccount(
        account_id="account-1",
        provider=provider,
        account_name="Account",
        account_external_id=None,
        api_key=api_key,
    )


def test_mailchimp_maps_campaign_content_endpoint() -> None:
    http = FakeHttpClient([{"html": "<h1>Hello</h1>", "plain_text": "Hello"}])
    client = MailchimpClient(http)
    campaign = client.get_campaign_content(
        _account("mailchimp", "mailchimp-key-us21"),
        type("C", (), {"external_id": "mc-1", "subject": "Sub"})(),
    )
    assert campaign is not None
    assert campaign.html_body == "<h1>Hello</h1>"
    assert campaign.text_body == "Hello"


def test_mailerlite_maps_campaign_content_when_present() -> None:
    http = FakeHttpClient([
        {"data": {"emails": [{"html": "<p>Hi</p>", "plain_text": "Hi", "preheader": "Preview"}]}}
    ])
    client = MailerLiteClient(http)
    campaign = client.get_campaign_content(
        _account("mailerlite", "token"),
        type("C", (), {"external_id": "ml-1", "subject": "Sub"})(),
    )
    assert campaign is not None
    assert campaign.text_body == "Hi"
    assert campaign.content_source == "mailerlite_campaign_response"
def test_transpond_maps_campaign_and_stats() -> None:
    http = FakeHttpClient([
        {
            "data": [
                {
                    "id": "tp-1",
                    "name": "Spring",
                    "subject": "Hello",
                    "status": "sent",
                    "sent_at": "2026-05-01T10:00:00Z",
                }
            ],
            "pagination": {"total_pages": 1},
        },
        {"data": {"emails_sent": 100, "opens_unique": 40, "clicks_unique": 10}},
    ])
    client = TranspondClient(http)
    campaigns = client.get_sent_campaigns(
        _account("transpond", "token"), datetime(2026, 4, 30, tzinfo=UTC)
    )
    assert campaigns[0].external_id == "tp-1"
    assert campaigns[0].subject == "Hello"
    stats = client.get_campaign_stats(_account("transpond", "token"), "tp-1")
    assert stats.open_rate == 0.4
    assert stats.click_rate == 0.1


def test_transpond_missing_metrics_map_to_none() -> None:
    http = FakeHttpClient([{"data": {}}])
    client = TranspondClient(http)
    stats = client.get_campaign_stats(_account("transpond", "token"), "tp-1")
    assert stats.emails_sent is None
    assert stats.open_rate is None
    assert stats.click_rate is None
