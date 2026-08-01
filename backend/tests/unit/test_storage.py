import pytest

from app.services.storage import calculate_retry_delay, should_use_object_storage


@pytest.mark.unit
def test_should_use_object_storage_small_body():
    small_body = "x" * 1000
    assert not should_use_object_storage(len(small_body.encode()))


@pytest.mark.unit
def test_should_use_object_storage_large_body():
    large_body = "x" * 11000000
    assert should_use_object_storage(len(large_body.encode()))


@pytest.mark.unit
def test_retry_delay_exponential_backoff():
    assert calculate_retry_delay(1) == 2
    assert calculate_retry_delay(2) == 4
    assert calculate_retry_delay(3) == 8
    assert calculate_retry_delay(4) == 16
    assert calculate_retry_delay(5) == 32
    assert calculate_retry_delay(6) == 0


@pytest.mark.unit
def test_retry_delay_attempt_0():
    assert calculate_retry_delay(0) == 1
