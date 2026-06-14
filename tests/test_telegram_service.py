import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from app.services.notification import telegram_service as ts


@pytest.mark.asyncio
async def test_send_photo_missing_token_raises():
    db = MagicMock()
    with patch.object(ts, "_load_config", AsyncMock(return_value=(None, None))):
        with pytest.raises(ts.TelegramNotConfigured):
            await ts.send_photo(db, b"\x89PNG", "cap")


@pytest.mark.asyncio
async def test_send_photo_posts_to_telegram():
    db = MagicMock()
    resp = MagicMock(status_code=200)
    client = AsyncMock(); client.post = AsyncMock(return_value=resp)
    cm = MagicMock(); cm.__aenter__ = AsyncMock(return_value=client); cm.__aexit__ = AsyncMock(return_value=False)
    with patch.object(ts, "_load_config", AsyncMock(return_value=("TOKEN", "CHAT"))), \
         patch("app.services.notification.telegram_service.httpx.AsyncClient", return_value=cm):
        ok = await ts.send_photo(db, b"\x89PNG", "cap")
        assert ok is True
        args, kwargs = client.post.call_args
        assert "/botTOKEN/sendPhoto" in args[0]
        assert kwargs["data"]["chat_id"] == "CHAT"
