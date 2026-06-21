"""포트폴리오 데이터 → LLM 종합 리포트(마크다운). 설정: 연결=ai_gateway, 모델/프롬프트/토글=ai_report."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.settings.settings_manager import get_setting
from app.services.ai import llm_client
from app.services.ai_report import report_data, report_store

CONN = "ai_gateway"      # base_url/api_key 공유
REPORT = "ai_report"     # model/prompt/enabled 전용
_TEMPERATURE = 0.5
_MAX_OUTPUT_TOKENS = 4000
_KST = ZoneInfo("Asia/Seoul")


class ReportNotConfigured(Exception):
    pass


class ReportDisabled(Exception):
    pass


DEFAULT_PROMPT = """# 역할
- 당신은 개인 투자자의 자산운용을 돕는 포트폴리오 애널리스트입니다.
- 아래에 제공되는 포트폴리오 데이터(요약·자산군 비중·보유 종목·일별 추세)만을 근거로 한국어 종합 리포트를 작성합니다.
- 매크로/뉴스/외부 지식은 사용하지 말고, 주어진 데이터에서 읽히는 사실만 인용합니다.

# 출력 구조 (이 순서·헤더 유지, 마크다운)
1. **종합 진단** — 총자산·손익 현황, 포트폴리오의 전반적 성격 한두 줄.
2. **자산군 배분 진단** — 편중/집중 위험. 특정 자산군·단일 종목 비중이 큰지, 현금성 비중이 적정한지 사실 환기.
3. **추세·성과 리뷰** — 제공된 일별 스냅샷이 2개 이상이면 총자산·손익의 최근 변화를 서술. 1개 이하이면 "추세 데이터 부족"이라고 명시.
4. **종목별 관찰** — 비중이 크거나 손익/최근 수익률이 두드러진 종목 위주로. (이력 없음) 종목은 수익률 언급을 생략.
5. **방향 제안** — 관찰에 근거한 점검 방향(예: 비중 편중 점검, 현금 비중 재고). 구체적 매매 지시(무엇을 몇 % 사라/팔라)는 하지 않습니다.

# 작성 원칙
- 개조식(불릿) 위주, 숫자는 데이터에 제시된 값을 인용.
- 단정적 예측 대신 조건/관찰형으로 서술.
- 분량: 한글 1,200~2,000자 권장."""

_DISCLAIMER = "\n\n---\n*본 리포트는 보유 데이터에 기반한 참고용 분석이며 투자 권유가 아닙니다.*"


async def load_config(db: AsyncSession) -> dict:
    enabled = (await get_setting(db, REPORT, "enabled")) or "false"
    if enabled.lower() != "true":
        raise ReportDisabled("AI 리포트가 비활성화되어 있습니다.")
    base_url = await get_setting(db, CONN, "base_url")
    api_key = await get_setting(db, CONN, "api_key")
    model = await get_setting(db, REPORT, "model")
    if not base_url or not api_key or not model:
        raise ReportNotConfigured("AI 게이트웨이 연결(base_url/api_key)·리포트 모델 설정이 필요합니다.")
    prompt = (await get_setting(db, REPORT, "prompt")) or DEFAULT_PROMPT
    return {"base_url": base_url, "api_key": api_key, "model": model, "prompt": prompt}


async def generate_markdown(db: AsyncSession) -> tuple[str, str]:
    """(마크다운 본문, 사용 모델). 미설정/비활성/LLM 실패는 예외 전파."""
    cfg = await load_config(db)
    block = await report_data.collect_input_block(db)
    full_prompt = f"{cfg['prompt']}\n\n# 입력 데이터\n{block}"
    md = await llm_client.generate_text(
        base_url=cfg["base_url"], api_key=cfg["api_key"], model=cfg["model"],
        prompt=full_prompt, temperature=_TEMPERATURE, max_output_tokens=_MAX_OUTPUT_TOKENS)
    return md, cfg["model"]


async def create_report(db: AsyncSession, trigger: str):
    """생성 + 저장. AIReport 반환."""
    md, model = await generate_markdown(db)
    title = f"{datetime.now(_KST).date().isoformat()} 포트폴리오 종합 리포트"
    return await report_store.create(db, title, md + _DISCLAIMER, model, trigger)
