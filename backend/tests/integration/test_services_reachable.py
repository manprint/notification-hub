import boto3
import psycopg
import pytest
import redis


@pytest.mark.integration
def test_postgres_raggiungibile():
    conn = psycopg.connect("postgresql://notifyhub_owner:dev_owner@127.0.0.1:5433/notifyhub_test")
    cursor = conn.cursor()
    cursor.execute("SELECT 1")
    result = cursor.fetchone()
    assert result is not None
    conn.close()


@pytest.mark.integration
def test_redis_raggiungibile():
    r = redis.Redis(host="127.0.0.1", port=6380, db=0)
    result = r.ping()
    assert result is True


@pytest.mark.integration
def test_bucket_minio_esiste():
    s3 = boto3.client(
        "s3",
        endpoint_url="http://127.0.0.1:9002",
        aws_access_key_id="minioadmin",
        aws_secret_access_key="minioadmin",
        region_name="us-east-1",
    )
    s3.head_bucket(Bucket="notifyhub-payloads")
