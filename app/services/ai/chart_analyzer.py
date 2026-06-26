"""차트 이미지 → AI 기술분석 텍스트(텔레그램 HTML). 설정은 ai_gateway 카테고리."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.settings.settings_manager import get_setting
from app.services.ai import llm_client
from app.services.ai import telegram_md

CATEGORY = "ai_gateway"
_TEMPERATURE = 0.4
_MAX_OUTPUT_TOKENS = 2000


class AnalysisNotConfigured(Exception):
    pass


class AnalysisDisabled(Exception):
    pass


DEFAULT_PROMPT = """# 역할
- 당신은 자산운용사 트레이딩 데스크에서 10년 이상 차트 분석을 담당한 시니어 차티스트입니다.
- 매일 아침 운용역에게 텔레그램으로 자산의 기술적 관점을 보고합니다.

# 입력 차트 구성 (매우 중요 — 정확한 해석을 위해 숙지)
제공되는 각 차트는 4개 패널로 구성됩니다.

[Panel 1 - 가격 차트]
- 캔들스틱 (녹색=상승, 적색=하락)
- 이동평균선 4종: EMA 12(빨강), EMA 26(파랑), SMA 20(진녹), SMA 50(주황)
- 볼린저밴드 (회색 점선 ±2σ, 음영 영역)
- 매물대 / Volume Profile: 좌측 가격축을 따라 그려진 옅은 주황색 가로막대. 막대가 두꺼울수록 해당 가격대의 누적 거래량이 큼(지지/저항 강도 지표).

[Panel 2 - RSI(14)]
- 보라색 선, 70 이상 과매수, 30 이하 과매도
- (배경의 옅은 노란색은 30-70 중립구간 표시일 뿐)

[Panel 3 - MACD]
- 파랑 = MACD (EMA12 - EMA26), 빨강 = Signal(9-period EMA), 막대 = Histogram

[Panel 4 - 거래량]
- 막대 = 거래량(상승 녹색/하락 적색), 파랑선 = 거래량 20기간 이동평균

# 분석 원칙
- 매크로/펀더멘털/밸류에이션은 일체 고려하지 않습니다. 오직 차트의 가격 행동과 위 지표만으로 판단합니다.
- 일봉(단기)과 주봉(중장기)이 함께 제공되면 반드시 교차 분석하여 신호의 일치/괴리를 명시합니다.
- 일반론을 피하고 차트에서 읽히는 구체적 근거(가격대, 지표값, 패턴)를 인용합니다.

# 출력 구조 (이 순서·헤더 유지)
1. **종합 의견 한 줄** — 추세 단계 + 모멘텀 + 단기 편향
2. **주봉 관점 (중장기)** — 큰 흐름, 핵심 매물대, 이평선 배열, 보조지표
3. **일봉 관점 (단기)** — 최근 캔들 패턴, 이평선 정/역배열, 볼린저 위치, RSI/MACD
4. **시간프레임 통합 진단** — 일봉·주봉 신호 일치/괴리, 우세한 방향
5. **시나리오** — 상승/하락 시나리오 각각의 트리거 가격과 1차 목표/이탈 대응
6. **트레이딩 관점** — 매수/매도/관망 판단, 핵심 관찰 가격대, 주요 리스크

# 출력 형식
- 개조식(불릿 위주), 가격은 차트에서 읽히는 수준으로 표기
- 단정적 예측 대신 조건부 시나리오로 작성(예: "X 돌파 시 → Y 시도")
- 전체 분량: 한글 1,500~2,500자 권장"""

_FORMAT_INSTRUCTION = """

[출력 형식]
- 마크다운으로 작성합니다. 일반 텍스트/HTML 태그를 직접 쓰지 마세요.
- 섹션 헤더는 `## 섹션명`, 강조는 `**굵게**`, 약한 강조는 `*기울임*`, 코드/수치는 `` `값` ``.
- 항목은 `- ` 불릿으로, 개조식으로 작성합니다.
- 전체 분량: 한글 1,500~2,500자 권장"""



def _build_prompt(user_prompt: str, ticker: str, name: str, market: str,
                  chart_labels: list[str]) -> str:
    now_kst = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M KST")
    image_order = "\n".join(f"  - 이미지 {i+1}: {label}" for i, label in enumerate(chart_labels))
    multi_tf = ("\n- 일봉과 주봉이 함께 제공되었으므로 단기/중장기 흐름을 교차 분석해 방향성의 일치/괴리를 반드시 언급하세요."
                if len(chart_labels) >= 2 else "")
    meta = (
        f"[종목 정보]\n- 종목명: {name}\n- 티커: {ticker}\n- 시장: {market}\n- 분석 시점: {now_kst}\n\n"
        f"[제공된 차트 이미지 순서]\n{image_order}{multi_tf}\n\n[분석 지시]\n"
    )
    return meta + user_prompt + _FORMAT_INSTRUCTION


async def load_config(db: AsyncSession) -> dict:
    """ai_gateway 설정 로드. 비활성→AnalysisDisabled, 필수키 누락→AnalysisNotConfigured."""
    enabled = (await get_setting(db, CATEGORY, "enabled")) or "false"
    if enabled.lower() != "true":
        raise AnalysisDisabled("AI 분석이 비활성화되어 있습니다.")
    base_url = await get_setting(db, CATEGORY, "base_url")
    api_key = await get_setting(db, CATEGORY, "api_key")
    model = await get_setting(db, CATEGORY, "model")
    if not base_url or not api_key or not model:
        raise AnalysisNotConfigured("AI 게이트웨이 설정(base_url/api_key/model)이 비어 있습니다.")
    prompt = (await get_setting(db, CATEGORY, "prompt")) or DEFAULT_PROMPT
    return {"base_url": base_url, "api_key": api_key, "model": model, "prompt": prompt}


async def analyze_raw(db: AsyncSession, images: list[tuple[bytes, str]],
                      ticker: str, name: str, market: str) -> tuple[str, str]:
    """이미지(일봉,주봉 순) → (LLM 마크다운 원문, 모델명). 미설정/비활성/실패는 예외 전파."""
    cfg = await load_config(db)
    chart_labels = ["일봉 (1년)", "주봉 (5년)"][:len(images)]
    prompt = _build_prompt(cfg["prompt"], ticker, name, market, chart_labels)
    text = await llm_client.analyze_images(
        base_url=cfg["base_url"], api_key=cfg["api_key"], model=cfg["model"],
        images=images, prompt=prompt,
        temperature=_TEMPERATURE, max_output_tokens=_MAX_OUTPUT_TOKENS)
    return text, cfg["model"]


async def analyze(db: AsyncSession, images: list[tuple[bytes, str]],
                  ticker: str, name: str, market: str) -> list[str]:
    """이미지(일봉,주봉 순) → 텔레그램 HTML 메시지 조각 리스트. 미설정/비활성/실패는 예외 전파."""
    raw, _model = await analyze_raw(db, images, ticker, name, market)
    return telegram_md.split_message(telegram_md.md_to_telegram_html(raw))
