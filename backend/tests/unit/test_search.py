import uuid

import pytest

from app.schemas.search import (
    NotificationAggregation,
    NotificationSearchFilters,
    NotificationSearchResponse,
)


@pytest.mark.unit
def test_notification_search_filters_minimal():
    filters = NotificationSearchFilters()

    assert filters.query is None
    assert filters.severity is None
    assert filters.status is None
    assert filters.skip == 0
    assert filters.limit == 20
    assert filters.sort_order == "desc"


@pytest.mark.unit
def test_notification_search_filters_with_query():
    filters = NotificationSearchFilters(
        query="error in database",
        severity=["error", "critical"],
    )

    assert filters.query == "error in database"
    assert len(filters.severity) == 2


@pytest.mark.unit
def test_notification_search_filters_sort_by():
    filters_asc = NotificationSearchFilters(sort_order="asc")
    assert filters_asc.sort_order == "asc"

    filters_desc = NotificationSearchFilters(sort_order="desc")
    assert filters_desc.sort_order == "desc"


@pytest.mark.unit
def test_notification_search_filters_pagination():
    filters = NotificationSearchFilters(skip=40, limit=50)

    assert filters.skip == 40
    assert filters.limit == 50


@pytest.mark.unit
def test_notification_search_response():
    response = NotificationSearchResponse(
        results=[],
        total=0,
        took_ms=10,
    )

    assert response.total == 0
    assert response.took_ms == 10


@pytest.mark.unit
def test_notification_aggregation():
    agg = NotificationAggregation(
        severity={"info": 10, "error": 5},
        status={"unread": 12, "read": 3},
        by_receiver={str(uuid.uuid4()): 5},
    )

    assert agg.severity["info"] == 10
    assert agg.status["unread"] == 12
    assert len(agg.by_receiver) == 1


@pytest.mark.unit
def test_notification_aggregation_no_receiver():
    agg = NotificationAggregation(
        severity={"warning": 8},
        status={"unread": 8},
    )

    assert agg.by_receiver is None
