# invest_portal 2단계(2a+2b) 설계: 차트 생성 + 텔레그램 발송

작성 기준일: 2026-06-14
대상 코드베이스: `/Users/mukymook/Library/CloudStorage/SynologyDrive-mookmuky/04.Coding/invest_portal`
참고 출처: `my-assistant`의 `app/services/bots/chart_bot.py`(검증된 4패널 TA 차트), `app/services/notification/telegram_sender.py`(텔레그램), `ytdb`의 `app/services/notify_service.py`·`scheduler.py` 패턴
선행: 1단계·1.5단계·자산군 분류 등 모두 main 병합 완료

## 1. 목적과 범위

보유/지정 자산의 **기술적 분석 차트(4패널 TA)** 를 생성해 화면에서 조회하고, **텔레그램으로 발송**한다.
my-assistant chartbot의 검증된 차트·발송 흐름을 invest_portal 스택(FastAPI + async + PostgreSQL)으로
재구성한다. AI 차트 분석과 스케줄 자동 발송은 다음 하위 프로젝트로 미룬다.

### 이번 범위 (2a + 2b)
1. **OHLCV history**: provider에 `history()` 추가 + data_source 디스패치(`history_service`).
2. **차트 생성**: matplotlib 4패널 TA 차트(일봉·주봉) PNG bytes(온더플라이, 파일 저장 없음).
3. **차트 조회 API/UI**: `GET /api/charts/{asset_id}` + "차트" 메뉴.
4. **텔레그램 발송**: 설정(봇 토큰/chat_id, Fernet) + `telegram_service` + `POST /api/charts/{asset_id}/send-telegram` + 설정 UI.

### 비범위 (다음 하위 프로젝트)
- **2c**: AI 차트 분석(litellm 비전 → 코멘트, 텔레그램 발송).
- **2d**: 스케줄 자동 발송(APScheduler, 종목별 발송시각·요일).
- 관심종목(watchlist), 다중 텔레그램 채팅·다중 봇.

## 2. 핵심 결정

| 항목 | 결정 | 근거 |
|------|------|------|
| 차트 라이브러리 | matplotlib(Agg) — my-assistant 로직 선별 참조 | 사용자가 만족하는 검증된 차트. 완전 제어 |
| 차트 종류 | 일봉 + 주봉 2종 | my-assistant와 동일 |
| 차트 전달 | 온더플라이 PNG bytes(저장 안 함) | Docker 친화·정리 불필요. 텔레그램도 bytes 발송 |
| history 소스 | data_source 디스패치(yfinance/pykrx). KR ETF는 yfinance(.KS) | quote와 동일 원칙. pykrx ETF 깨짐 회피 |
| 텔레그램 | 단일 봇 토큰 + 단일 chat_id, `app_settings.notification`(토큰 Fernet) | 단일 운영자 |
| 한글 폰트 | 로컬 AppleSDGothicNeo, Docker `fonts-nanum` 설치 + matplotlib 설정 | 종목명 한글 렌더 |
| 코드 이식 | 복사 아님 — 검증 로직·개념만 선별 참조해 새로 작성 | 기존 원칙 계승 |

## 3. OHLCV history (2a)

### 3.1 provider.history
`PriceProvider`에 `history(fetch_symbol, market, period)` 추가.
- `YFinanceProvider.history`: `yf.Ticker(fetch_symbol).history(period=...)` → OHLCV DataFrame(Open/High/Low/Close/Volume). US/JP/crypto 및 **KR ETF(.KS)** 포함.
- `PykrxProvider.history`: KR 주식은 `get_market_ohlcv_by_date(start, end, fetch_symbol)`. (ETF는 data_source가 yfinance라 여기로 오지 않음.)
- `ManualProvider`: history 없음(None 반환) — 차트 불가.

기간: 일봉은 충분한 봉 수(예: yfinance `period="2y"`, pykrx 약 2년 윈도우), 주봉은 더 긴 범위(예: 5년)에서 리샘플 또는 더 긴 일봉을 주봉으로 변환. 구체 봉 수는 구현에서 확정(차트가 지표를 그릴 충분한 길이 확보).

### 3.2 history_service
`get_history(asset, period) -> DataFrame | None` — asset.data_source/fetch_symbol/market로 provider.history 호출(블로킹 → `asyncio.to_thread`). OHLCV 컬럼 정규화(yfinance 멀티레벨·pykrx 한글 컬럼 → Open/High/Low/Close/Volume). NaN 정제.

## 4. 차트 생성 (chart_service, 2a)

`generate_ta_chart(df, title, timeframe) -> bytes`(PNG). my-assistant `chart_bot._calculate_indicators` + `_create_ta_chart`의 검증 로직을 선별 참조해 새로 작성.
- 지표: EMA12/26, SMA20/50, Bollinger(20,2σ), RSI(14), MACD(12,26,9), 거래량.
- 4패널: ① 가격(캔들 + MA/EMA/볼린저) ② RSI ③ MACD ④ 거래량.
- 일봉·주봉 각각 1장. 주봉은 일봉 DataFrame을 주 단위로 리샘플(OHLCV 집계).
- matplotlib `Agg` 백엔드, 한글 폰트 설정(로컬/Docker 분기), `savefig`를 `BytesIO`로 받아 PNG bytes 반환.
- 입력 데이터 부족·실패 시 명확한 예외(상위에서 502/422 처리).

## 5. 차트 조회 API/UI (2a)

- `GET /api/charts/{asset_id}?period=daily|weekly` → `StreamingResponse(media_type="image/png")`. 자산 조회→history→차트 생성→PNG 스트림. manual/이력 없음 자산은 422.
- **프론트 "차트" 메뉴**(신규): 자산 드롭다운(보유 자산 목록) 선택 → 일봉/주봉 `<img src="/api/charts/{id}?period=...">` 표시 → "텔레그램 발송" 버튼.
- 메뉴: 대시보드 · 보유 · **차트**.

## 6. 텔레그램 (2b)

### 6.1 설정
`app_settings`의 `notification` 카테고리:
- `telegram_bot_token`(is_secret=true, Fernet), `telegram_chat_id`.
설정 조회/저장은 기존 `settings_manager.get_setting/set_setting` 사용. 설정 UI(설정 화면 또는 차트 화면 내 설정 섹션)에서 입력.

### 6.2 telegram_service
`send_photo(png: bytes, caption: str) -> bool`, `send_message(text: str) -> bool`.
- Telegram Bot API(`https://api.telegram.org/bot<token>/sendPhoto|sendMessage`), httpx 비동기, `parse_mode=HTML`.
- 봇 토큰/chat_id를 settings_manager에서 로드. 미설정 시 명확한 오류(409/422).
- 429 `retry_after` 처리(my-assistant 패턴). caption 길이 제한(1024) 처리.

### 6.3 발송 엔드포인트
`POST /api/charts/{asset_id}/send-telegram` → 일봉+주봉 PNG 생성 + 캡션(종목명·티커·현재가·기준시각)과 함께 `send_photo` 2회 발송. 결과(성공/실패) 반환.

## 7. 영향/신규 컴포넌트
- `requirements.txt`: matplotlib 추가.
- `Dockerfile`: `fonts-nanum`(또는 nanum 폰트) 설치 단계 추가.
- `app/services/market/{yfinance_provider,pykrx_provider,manual_provider}.py`: `history()` 추가.
- `app/services/market/base.py`: `PriceProvider` 프로토콜에 `history(fetch_symbol, market, period)` 시그니처 추가(현재는 resolve/quote만 있음).
- 신규: `app/services/market/history_service.py`, `app/services/chart/chart_service.py`, `app/services/notification/telegram_service.py`.
- 신규 라우터: `app/routers/charts.py`(GET 차트, POST send-telegram). `app/routers/settings.py`는 기존 활용(텔레그램 설정 저장/조회).
- `app/main.py`: charts 라우터 등록.
- 프론트: `api.ts`(차트 URL 헬퍼, sendTelegram, 텔레그램 설정 get/set), `pages/Charts.tsx`(신규), `App.tsx`(차트 라우트·네비), 텔레그램 설정 입력 UI.

## 8. 테스트
- 단위: 지표 계산값(RSI/MACD/Bollinger; 알려진 입력→기대값), history 디스패치(provider 모킹: yfinance/pykrx/manual), 차트 생성이 비어있지 않은 PNG(매직바이트 `\x89PNG`) 반환(Agg, 모킹 OHLCV), 주봉 리샘플 정확성, 텔레그램 페이로드·URL 구성(httpx 모킹), 토큰 미설정 시 오류.
- 통합/스모크(실DB/실API): 보유 자산(예: 005930 .KS via yfinance, 또는 pykrx) 일봉 차트 생성·`GET /api/charts` 200 image/png, 텔레그램 발송(토큰 설정된 경우만, 아니면 skip).
- 외부(yfinance/pykrx/telegram)는 단위테스트에서 모킹.

## 9. 오류 처리
- 이력 없음/manual 자산 차트 요청 → 422(명확 메시지).
- 차트 생성 실패(데이터 부족) → 502/422.
- 텔레그램 토큰·chat_id 미설정 → 409/422. 텔레그램 API 오류 → 실패 결과 반환(앱은 죽지 않음), 429 retry_after 처리.
- 외부 시세/HTTP 실패는 graceful(차트 조회 실패만 해당 요청에 반영).
