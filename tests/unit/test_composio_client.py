import pytest

from rag.connectors import ConnectorAuthError, ConnectorError, ConnectorRateLimitError
from rag.connectors.composio_client import unwrap_response


def test_unwrap_returns_data_on_success():
    resp = {"successful": True, "data": {"files": [{"id": "1"}]}}
    assert unwrap_response(resp) == {"files": [{"id": "1"}]}


def test_unwrap_treats_missing_successful_as_success():
    # Some actions omit the flag; presence of data with no error means success.
    assert unwrap_response({"data": {"x": 1}}) == {"x": 1}


def test_unwrap_returns_empty_dict_when_data_missing():
    assert unwrap_response({"successful": True}) == {}


def test_unwrap_raises_auth_on_401():
    with pytest.raises(ConnectorAuthError):
        unwrap_response({"successful": False, "error": "HTTP 401 Unauthorized"})


def test_unwrap_raises_auth_on_expired_token():
    with pytest.raises(ConnectorAuthError):
        unwrap_response({"successful": False, "error": "invalid_grant: token expired"})


def test_unwrap_raises_rate_limit_on_429():
    with pytest.raises(ConnectorRateLimitError):
        unwrap_response({"successful": False, "error": "HTTP 429 too many requests"})


def test_unwrap_raises_generic_error_otherwise():
    with pytest.raises(ConnectorError) as exc:
        unwrap_response({"successful": False, "error": "boom"})
    # Must be the base ConnectorError, not an auth/rate subclass.
    assert not isinstance(exc.value, (ConnectorAuthError, ConnectorRateLimitError))
