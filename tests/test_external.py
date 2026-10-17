"""Rate-limit key: which caller an MCP/UCP request is counted against."""

from backend.external import client_key


def test_uses_the_entry_cloud_run_appends():
    # Cloud Run appends the real caller IP; anything before it came from the caller.
    assert client_key({"x-forwarded-for": "203.0.113.7"}, "169.254.1.1") == "203.0.113.7"


def test_spoofed_leading_entries_are_ignored():
    headers = {"x-forwarded-for": "1.2.3.4, 5.6.7.8, 203.0.113.7"}
    assert client_key(headers, "169.254.1.1") == "203.0.113.7"


def test_rotating_a_spoofed_value_does_not_change_the_key():
    keys = {client_key({"x-forwarded-for": f"10.0.0.{i}, 203.0.113.7"}, None) for i in range(20)}
    assert keys == {"203.0.113.7"}


def test_falls_back_to_the_socket_peer_without_the_header():
    assert client_key({}, "127.0.0.1") == "127.0.0.1"
    assert client_key({"x-forwarded-for": " , "}, "127.0.0.1") == "127.0.0.1"
    assert client_key(None, None) == "unknown"
