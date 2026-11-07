import os
from urllib.parse import urlparse
from dotenv import load_dotenv
import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError

# boto3's standard names for this app's own credentials, region, and
# endpoint. They are not part of the interface contract.
ACCESS_KEY_ID_ENV = "AWS_ACCESS_KEY_ID"
SECRET_ACCESS_KEY_ENV = "AWS_SECRET_ACCESS_KEY"
REGION_ENV = "AWS_DEFAULT_REGION"
ENDPOINT_ENV = "AWS_ENDPOINT_URL_S3"
CONNECTION_ENV_VARS = (
    ACCESS_KEY_ID_ENV,
    SECRET_ACCESS_KEY_ENV,
    REGION_ENV,
    ENDPOINT_ENV,
)


class S3ConfigurationError(ValueError):
    """
    The S3 connection settings in the environment are missing or invalid.
    The message names environment variables only, never their values, so
    it is safe to log.
    """


def read_connection_settings():
    """
    Read the S3 connection settings from the environment.

    Every value is read explicitly and must be set, so boto3 never falls
    back to other credentials (such as `~/.aws` or a profile) or to AWS's
    own endpoint.

    Returns
    -------
    dict[str, str]
        Environment variable name -> value (surrounding whitespace removed),
        for every name in CONNECTION_ENV_VARS.

    Raises
    ------
    S3ConfigurationError
        If any of them is unset, empty, or only whitespace. The message
        lists every missing name.
    """
    settings = {name: os.getenv(name, "").strip() for name in CONNECTION_ENV_VARS}
    missing = [name for name, value in settings.items() if not value]
    if missing:
        raise S3ConfigurationError(
            f"Missing S3 connection settings: {', '.join(missing)}"
        )
    return settings


def check_endpoint(endpoint_url, bucket_name=None):
    """
    Check that the endpoint is a region-only URL, such as
    `https://nyc3.digitaloceanspaces.com`.

    The bucket-specific endpoint (`https://<bucket>.<region>...`) makes
    listings fail with `NoSuchKey` (see "Connecting" in the interface
    contract), so it is refused with a clear message instead.

    Parameters
    ----------
    endpoint_url : str
        Value of the endpoint environment variable.

    bucket_name : str | None
        The bucket (Space) name. If None or empty, only the URL form is
        checked.

    Raises
    ------
    S3ConfigurationError
        If the endpoint is not an http(s) URL with a host, or its host
        starts with the bucket name. The message does not include either
        value.
    """
    parsed = urlparse(endpoint_url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https") or not host:
        raise S3ConfigurationError(
            f"{ENDPOINT_ENV} must be a URL such as "
            "https://<region>.digitaloceanspaces.com."
        )
    bucket = (bucket_name or "").strip().lower()
    if bucket and host.startswith(f"{bucket}."):
        raise S3ConfigurationError(
            f"{ENDPOINT_ENV} names the bucket in its host. Use the region-only "
            "endpoint, such as https://<region>.digitaloceanspaces.com, and "
            "set the bucket name separately."
        )


class S3Downloader:
    def __init__(self, client=None, bucket_name=None):
        """
        Initialize the S3 downloading class and its client.

        The connection settings are read from the environment variables
        in CONNECTION_ENV_VARS (boto3's standard names), after loading a
        local `.env` file if there is one. Values in `.env` override
        variables already set in the environment, so a local `.env` wins
        over AWS variables exported in the shell. Every value is passed to
        boto3 explicitly.

        Parameters
        ----------
        client : botocore client | None
            S3 client to use instead of creating one. Intended for tests.

        bucket_name : str | None
            The bucket (Space) name, used only to check that the endpoint
            does not name the bucket.

        Raises
        ------
        S3ConfigurationError
            If a connection setting is missing or the endpoint is invalid.
            No client is created in that case.
        """
        if client is not None:
            self.client = client
            return
        load_dotenv(override=True)
        settings = read_connection_settings()
        check_endpoint(settings[ENDPOINT_ENV], bucket_name)
        session = boto3.session.Session()
        self.client = session.client(
            "s3",
            region_name=settings[REGION_ENV],
            endpoint_url=settings[ENDPOINT_ENV],
            aws_access_key_id=settings[ACCESS_KEY_ID_ENV],
            aws_secret_access_key=settings[SECRET_ACCESS_KEY_ENV],
            config=Config(signature_version="s3v4"),
        )

    def list_keys(self, bucket_name, folder):
        """
        List every object key under a top-level folder of a bucket,
        following pagination (a single listing returns at most 1,000 keys).
        Prints a message if listing fails. Errors are reported by exception
        type only, so no connection details are printed.

        Parameters
        ----------
        bucket_name : str | None
            The bucket (Space) name. None or empty means it is not
            configured.

        folder : str | None
            Top-level folder name, without slashes. None or empty means it
            is not configured.

        Returns
        -------
        dict[str, str] | None
            Key relative to the folder (the `<folder>/` prefix removed) to
            ETag, for every object in the folder, or None if the folder
            could not be listed.
        """
        if not bucket_name or not folder:
            print("Could not list a folder: bucket or folder name is not configured.")
            return None
        prefix = f"{folder}/"
        keys = {}
        try:
            paginator = self.client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=bucket_name, Prefix=prefix):
                for obj in page.get("Contents", []):
                    if obj["Key"].startswith(prefix):
                        keys[obj["Key"][len(prefix) :]] = obj.get("ETag", "")
        except (BotoCoreError, ClientError) as error:
            print(f"Could not list folder {folder}: {type(error).__name__}")
            return None
        return keys

    def download_file(self, bucket_name, object_name, local_filename):
        """
        Downloads a file from S3 into local storage. Prints a message
        saying whether the download succeeded. Errors are reported by
        exception type only, so no connection details are printed.

        Parameters
        ----------
        bucket_name : str | None
            The bucket (Space) name. None or empty means it is not
            configured.

        object_name : str
            Full object key, including the top-level folder

        local_filename : str
            Path to the local filename

        Returns
        -------
        bool
            True if the file was downloaded, False otherwise.
        """
        if not bucket_name:
            print(f"Could not download {object_name}: bucket name is not configured.")
            return False
        try:
            self.client.download_file(bucket_name, object_name, local_filename)
        except (BotoCoreError, ClientError, OSError) as error:
            print(f"Could not download {object_name}: {type(error).__name__}")
            return False
        print(f"Downloaded {local_filename}!")
        return True
