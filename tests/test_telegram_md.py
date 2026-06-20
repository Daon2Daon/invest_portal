from app.services.ai import telegram_md as tm


def test_md_to_html_converts_headings_and_bold():
    out = tm.md_to_telegram_html("# 제목\n**굵게** *기울임*")
    assert "<b>제목</b>" in out
    assert "<b>굵게</b>" in out
    assert "<i>기울임</i>" in out


def test_md_to_html_strips_unsupported_tags():
    out = tm.md_to_telegram_html("<div>x</div>")
    assert "<div>" not in out and "x" in out


def test_split_message_short_returns_single():
    assert tm.split_message("abc", limit=10) == ["abc"]


def test_split_message_splits_on_lines():
    text = "a\n" * 10
    parts = tm.split_message(text, limit=5)
    assert len(parts) > 1
    assert "".join(parts) == text
