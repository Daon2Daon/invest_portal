# 추천 자산군 목록(프론트와 공유 개념). 자유 입력도 허용한다.
ASSET_CLASSES = ["주식", "채권", "현금성", "원자재", "가상자산", "대체투자", "기타"]

_DEFAULT_BY_TYPE = {
    "stock": "주식", "etf": "주식", "fund": "주식", "index": "주식",
    "bond": "채권", "crypto": "가상자산", "commodity": "원자재", "etn": "기타",
}


def default_asset_class(asset_type: str | None) -> str:
    """asset_type에서 기본 자산군을 추정한다. 미지/None은 '기타'."""
    return _DEFAULT_BY_TYPE.get((asset_type or "").lower(), "기타")
