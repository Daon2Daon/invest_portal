import pytest
from unittest.mock import patch

from app.services.market_summary.indices import index_lines, INDICES


def test_indices_map_has_us_kr():
    assert [s for s, _ in INDICES["US"]] == ["^GSPC", "^IXIC", "^DJI"]
    assert [s for s, _ in INDICES["KR"]] == ["^KS11", "^KQ11"]


@pytest.mark.asyncio
async def test_index_lines_skips_failed():
    def fake_fetch(symbol):
        if symbol == "^IXIC":
            return None  # 실패 지수
        return (100.0, 1.5)
    with patch("app.services.market_summary.indices._fetch", side_effect=fake_fetch):
        rows = await index_lines("US")
    names = [r["name"] for r in rows]
    assert "NASDAQ" not in names          # 실패 지수 제외
    assert rows[0]["price"] == 100.0
    assert rows[0]["change_pct"] == 1.5
