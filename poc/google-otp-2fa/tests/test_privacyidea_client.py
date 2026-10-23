"""Unit checks for privacyIDEA REST client (no live server required)."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mfa-adapter"))
from privacyidea_client import PrivacyIDEAClient


@patch.object(PrivacyIDEAClient, "_authenticate_admin")
def test_user_has_totp_uses_user_query_param(mock_auth):
    client = PrivacyIDEAClient("http://pi", "admin", "secret", realm="poc")
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "result": {"value": {"tokens": [{"username": "alice", "serial": "T1"}]}}
    }
    with patch.object(client, "_admin_request", return_value=mock_resp) as req:
        assert client.user_has_totp("alice") is True
        mock_resp.json.return_value = {"result": {"value": {"tokens": []}}}
        assert client.user_has_totp("bob") is False
        first = req.call_args_list[0]
        params = first.kwargs.get("params") or first[1].get("params")
        assert params.get("user") == "alice"
        assert "username" not in params
