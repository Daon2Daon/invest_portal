"""마크다운 → 텔레그램 HTML 변환 + 길이 분할. 차트 분석·AI 리포트가 공유."""
import re


def md_to_telegram_html(text: str) -> str:
    text = re.sub(r"```[a-zA-Z]*\n?([\s\S]*?)```", r"<pre>\1</pre>", text)
    text = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"\*([^*\n]+)\*", r"<i>\1</i>", text)
    text = re.sub(r"^#{1,3}\s+(.+)$", r"<b>\1</b>", text, flags=re.MULTILINE)
    text = re.sub(r"<(h[1-6]|ul|ol|li|hr|br|div|span|p)\b[^>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"</(h[1-6]|ul|ol|li|hr|br|div|span|p)\b>", "", text, flags=re.IGNORECASE)
    return text.strip()


def split_message(text: str, limit: int = 4000) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts, current, current_len = [], [], 0
    for line in text.splitlines(keepends=True):
        if current_len + len(line) > limit and current:
            parts.append("".join(current))
            current, current_len = [], 0
        current.append(line)
        current_len += len(line)
    if current:
        parts.append("".join(current))
    return parts
