"""
Tests for S3Downloader with a fake S3 client and a fake boto3 session. No
network access and no real credentials are used, and the local `.env` file
is never read.
"""

import pytest
from botocore.exceptions import ClientError

import s3_downloader
from s3_downloader import (
    CONNECTION_ENV_VARS,
    S3ConfigurationError,
    S3Downloader,
    check_endpoint,
)

ENDPOINT = "https://nyc3.digitaloceanspaces.com"
FAKE_SETTINGS = {
    "AWS_ACCESS_KEY_ID": "test-key-id",
    "AWS_SECRET_ACCESS_KEY": "test-secret",
    "AWS_DEFAULT_REGION": "nyc3",
    "AWS_ENDPOINT_URL_S3": ENDPOINT,
}


class FakeSession:
    """
    Stand-in for boto3.session.Session that records the client() call.
    """

    calls = []

    def client(self, service_name, **kwargs):
        FakeSession.calls.append((service_name, kwargs))
        return "fake-client"


@pytest.fixture
def fake_boto3(monkeypatch):
    """
    Replace load_dotenv (recording its keyword arguments) and the boto3
    session, and clear the connection variables from the environment.
    """
    dotenv_calls = []
    monkeypatch.setattr(
        s3_downloader, "load_dotenv", lambda **kwargs: dotenv_calls.append(kwargs)
    )
    FakeSession.calls = []
    monkeypatch.setattr(s3_downloader.boto3.session, "Session", FakeSession)
    for name in CONNECTION_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    return dotenv_calls


def set_settings(monkeypatch, settings):
    for name, value in settings.items():
        monkeypatch.setenv(name, value)


def test_downloader_passes_every_setting_to_boto3(fake_boto3, monkeypatch):
    set_settings(monkeypatch, FAKE_SETTINGS)
    downloader = S3Downloader(bucket_name="space")
    assert downloader.client == "fake-client"
    assert fake_boto3 == [{"override": True}]
    [(service_name, kwargs)] = FakeSession.calls
    assert service_name == "s3"
    assert kwargs["aws_access_key_id"] == "test-key-id"
    assert kwargs["aws_secret_access_key"] == "test-secret"
    assert kwargs["region_name"] == "nyc3"
    assert kwargs["endpoint_url"] == ENDPOINT


def test_downloader_names_every_missing_setting(fake_boto3, monkeypatch):
    set_settings(
        monkeypatch,
        {
            "AWS_ACCESS_KEY_ID": "test-key-id",
            "AWS_SECRET_ACCESS_KEY": "",
            "AWS_DEFAULT_REGION": "   ",
        },
    )
    with pytest.raises(S3ConfigurationError) as raised:
        S3Downloader(bucket_name="space")
    message = str(raised.value)
    for name in ("AWS_SECRET_ACCESS_KEY", "AWS_DEFAULT_REGION", "AWS_ENDPOINT_URL_S3"):
        assert name in message
    assert "AWS_ACCESS_KEY_ID" not in message
    assert "test-key-id" not in message
    assert FakeSession.calls == []


def test_downloader_refuses_bucket_specific_endpoint(fake_boto3, monkeypatch):
    set_settings(
        monkeypatch,
        {**FAKE_SETTINGS, "AWS_ENDPOINT_URL_S3": "https://space.nyc3.digitaloceanspaces.com"},
    )
    with pytest.raises(S3ConfigurationError, match="region-only") as raised:
        S3Downloader(bucket_name="space")
    assert "space." not in str(raised.value)
    assert FakeSession.calls == []


@pytest.mark.parametrize(
    "endpoint, bucket_name",
    [
        (ENDPOINT, "space"),
        (ENDPOINT, None),
        ("https://NYC3.digitaloceanspaces.com/", "nyc3x"),
        # A bucket whose name only starts like the region is not a match.
        ("https://nyc3.digitaloceanspaces.com", "nyc"),
    ],
)
def test_check_endpoint_accepts_region_only_endpoints(endpoint, bucket_name):
    check_endpoint(endpoint, bucket_name)


@pytest.mark.parametrize(
    "endpoint, bucket_name",
    [
        ("https://space.nyc3.digitaloceanspaces.com", "space"),
        ("https://SPACE.nyc3.digitaloceanspaces.com", "space"),
        ("nyc3.digitaloceanspaces.com", "space"),
        ("ftp://nyc3.digitaloceanspaces.com", None),
        ("https://", None),
    ],
)
def test_check_endpoint_refuses_invalid_endpoints(endpoint, bucket_name):
    with pytest.raises(S3ConfigurationError):
        check_endpoint(endpoint, bucket_name)


class FakePaginator:
    """
    Stand-in for a boto3 list_objects_v2 paginator that yields fixed pages.
    """

    def __init__(self, pages, error=None):
        self.pages = pages
        self.error = error
        self.calls = []

    def paginate(self, **kwargs):
        self.calls.append(kwargs)
        for page in self.pages:
            yield page
        if self.error is not None:
            raise self.error


class FakeClient:
    """
    Stand-in for a boto3 S3 client that only supports get_paginator().
    """

    def __init__(self, paginator):
        self.paginator = paginator

    def get_paginator(self, operation_name):
        assert operation_name == "list_objects_v2"
        return self.paginator


def test_list_keys_follows_all_pages_and_strips_folder():
    pages = [
        {
            "Contents": [
                {"Key": "time-series/2026-10-08/all_forecasts.csv", "ETag": '"a"'},
                {"Key": "time-series/all_forecasts.csv", "ETag": '"b"'},
            ]
        },
        {"Contents": [{"Key": "time-series/2026-10-09/all_forecasts.csv", "ETag": '"c"'}]},
    ]
    paginator = FakePaginator(pages)
    downloader = S3Downloader(client=FakeClient(paginator))
    keys = downloader.list_keys("space", "time-series")
    assert keys == {
        "2026-10-08/all_forecasts.csv": '"a"',
        "all_forecasts.csv": '"b"',
        "2026-10-09/all_forecasts.csv": '"c"',
    }
    assert paginator.calls == [{"Bucket": "space", "Prefix": "time-series/"}]


def test_list_keys_ignores_keys_outside_folder():
    # S3 applies the prefix itself; this guards against keys such as
    # "time-series-old/..." or keys from a client that ignores Prefix.
    pages = [
        {
            "Contents": [
                {"Key": "time-series-old/2026-10-09/all_forecasts.csv", "ETag": '"a"'},
                {"Key": "portfolio-optimization/2026-10-09/optimization_metadata.yml"},
                {"Key": "time-series/2026-10-09/all_forecasts.csv", "ETag": '"c"'},
            ]
        }
    ]
    downloader = S3Downloader(client=FakeClient(FakePaginator(pages)))
    assert downloader.list_keys("space", "time-series") == {
        "2026-10-09/all_forecasts.csv": '"c"'
    }


def test_list_keys_empty_folder():
    downloader = S3Downloader(client=FakeClient(FakePaginator([{"KeyCount": 0}])))
    assert downloader.list_keys("space", "time-series") == {}


def test_list_keys_error_returns_none():
    error = ClientError(
        {"Error": {"Code": "NoSuchKey", "Message": "missing"}}, "ListObjectsV2"
    )
    downloader = S3Downloader(client=FakeClient(FakePaginator([], error=error)))
    assert downloader.list_keys("space", "time-series") is None


def test_list_keys_unconfigured_bucket_or_folder():
    downloader = S3Downloader(client=FakeClient(FakePaginator([])))
    assert downloader.list_keys(None, "time-series") is None
    assert downloader.list_keys("space", None) is None
    assert downloader.list_keys("space", "") is None
