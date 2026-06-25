import pytest
from types import SimpleNamespace
from fastapi import HTTPException

from app.routers import auth


def _fake_request(session: dict):
    return SimpleNamespace(session=session)


def test_auth_disabled_when_password_empty(monkeypatch):
    monkeypatch.setattr(auth.app_settings, "AUTH_PASSWORD", "")
    assert auth.auth_enabled() is False
    # 비활성이면 빈 세션이어도 통과(예외 없음)
    auth.require_auth(_fake_request({}))


def test_auth_enabled_blocks_anonymous(monkeypatch):
    monkeypatch.setattr(auth.app_settings, "AUTH_PASSWORD", "secret")
    assert auth.auth_enabled() is True
    with pytest.raises(HTTPException) as ei:
        auth.require_auth(_fake_request({}))
    assert ei.value.status_code == 401


def test_auth_enabled_allows_session_user(monkeypatch):
    monkeypatch.setattr(auth.app_settings, "AUTH_PASSWORD", "secret")
    auth.require_auth(_fake_request({"user": "admin"}))  # 예외 없으면 통과
