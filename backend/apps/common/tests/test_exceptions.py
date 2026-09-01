import pytest
from rest_framework import status
from rest_framework.exceptions import NotAuthenticated, ValidationError

from apps.common.exceptions import (
    InventoryUnavailable,
    OfferExpired,
    problem_detail_handler,
)


def handle(exc):
    response = problem_detail_handler(exc, {"request": None})
    assert response is not None
    return response


def test_domain_error_maps_to_its_status_and_code():
    response = handle(InventoryUnavailable("Only 1 seat remains."))
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.data["code"] == "inventory_unavailable"
    assert response.data["detail"] == "Only 1 seat remains."
    assert response.data["type"].endswith("inventory-unavailable")


def test_offer_expired_maps_to_409():
    response = handle(OfferExpired())
    assert response.status_code == 409
    assert response.data["code"] == "offer_expired"


def test_validation_error_is_remapped_from_400_to_422():
    """DRF calls field problems 400; the published contract calls them 422."""
    response = handle(ValidationError({"passengers": ["Exceeds available seats"]}))
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert response.data["code"] == "validation_error"
    assert {"field": "passengers", "message": "Exceeds available seats"} in response.data["errors"]


def test_nested_validation_errors_are_flattened():
    response = handle(ValidationError({"slices": {"0": {"date": ["Cannot search a past date."]}}}))
    fields = [error["field"] for error in response.data["errors"]]
    assert "slices.0.date" in fields


def test_authentication_error_maps_to_401():
    response = handle(NotAuthenticated())
    assert response.status_code == 401
    assert response.data["code"] == "authentication_required"


def test_problem_body_always_carries_the_contract_keys():
    response = handle(InventoryUnavailable("gone"))
    for key in ("type", "title", "status", "detail", "code"):
        assert key in response.data


def test_unknown_exception_is_not_swallowed():
    assert problem_detail_handler(RuntimeError("boom"), {"request": None}) is None
