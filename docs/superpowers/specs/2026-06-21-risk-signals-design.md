# 3단계 C: 위험신호·매수매도 도움 — 설계 (spec)

작성일: 2026-06-21
선행: 3단계 A(스냅샷), B(AI 리포트) 완료. C는 규칙기반 위험신호 알림.

## 1. 목적

보유 포트폴리오를 **결정론적 규칙**으로 주기 스캔해 위험신호(기술적 + 비중 편향)를 찾아
**일별 다이제스트 1건**으로 텔레그램 발송한다. LLM 미사용(조언은 B 리포트·2c 차트분석이 담당).
기존 alert/scheduler가 다루는 실시간 가격 임계값과 달리, 매일 한 번 포트폴리오 전반의 위험을 종합한다.

## 2. 핵심 결정 요약

| 항목 | 결정 |
|------|------|
| 성격 | 규칙기반 자동 위험신호 알림(결정론적, LLM 없음) |
| 기술 신호 | RSI 과매수/과매도, MACD 교차, 볼린저 이탈, SMA50 돌파 — 각 on/off |
| 비중 신호 | 단일 종목 과중, 단일 자산군 과중 — 각 on/off + 임계값(%) |
| 전달 모델 | 일별 다이제스트(활성 신호 종합 1메시지), market_summary 패턴 |
| 대상 종목 | 보유 종목 전체 자동(manual·무이력은 기술 신호 스킵, 비중은 전체) |
| 프론트 | 설정 섹션 + 텔레그램 푸시 + 미리보기/지금보내기 (전용 페이지 없음) |
| 저장 | 신규 테이블 없음(설정=settings_manager, 스케줄=기존 schedules 재사용) |

## 3. 전체 구조 & 데이터 흐름

```
[스캔]                                    [판정·구성]              [전달]
get_portfolio() ─→ positions/allocation ─┐
held assets ──→ history_service.get_history ─→ calculate_indicators ─┤
                                          ↓                          │
                              risk_evaluator (순수 규칙)            │
                              · 기술: RSI/MACD/BB/MA (종목별)        │
                              · 비중: 단일종목/단일자산군 (전체)     │
                                          ↓                          │
                              message 빌더(다이제스트 1건) ──────────┴─→ 텔레그램
                                                                     └─→ 미리보기(화면)
```

신규 `app/services/risk_signal/`:
- **`evaluator.py`** — 순수 함수(DB·네트워크 없음). 지표 DataFrame + 설정 → 종목 기술 신호 리스트;
  포트폴리오 dict + 설정 → 비중 신호 리스트. 테스트 핵심.
- **`scanner.py`** — 수집·오케스트레이션. `get_portfolio` + 보유 종목별 `get_history`→`calculate_indicators`→`evaluator`,
  비중 신호 병합 → 신호 목록(dict). manual·무이력·봉부족은 기술 신호 스킵.
- **`message.py`** — 신호 목록 → 다이제스트 텍스트(텔레그램 HTML). 0건이면 "현재 위험신호 없음".
- **`risk_service.py`** — `build_digest(db) -> str`(미리보기 텍스트), `build_and_send(db) -> dict`(스캔→발송, market_summary `build_and_send` 패턴).

기존 재사용: `chart_service.calculate_indicators`, `history_service.get_history`,
`portfolio_service.get_portfolio`, `notification.telegram_service`, `scheduler`(핸들러),
`schedules` 테이블, `settings.settings_manager`. **신규 테이블 없음.**

## 4. 신호 정의 & 규칙 (evaluator, 결정론적)

일봉 최신 봉 기준, 교차/돌파는 직전 봉과 비교. `calculate_indicators`가 제공하는 컬럼
(RSI, MACD, Signal, SMA20/50, BB_upper/BB_lower 등) 사용.

### 4.1 기술적 신호 (종목별, 각 on/off)

| 신호 | 발동 조건 |
|------|----------|
| RSI | 최신 `RSI` ≥ 70(과매수) 또는 ≤ 30(과매도) |
| MACD 교차 | 직전봉 `MACD≤Signal` & 최신봉 `MACD>Signal`(골든) / 반대(데드) |
| 볼린저 이탈 | 최신 `Close` > `BB_upper`(상단) 또는 < `BB_lower`(하단) |
| MA 돌파 | 직전봉 `Close≤SMA50` & 최신봉 `Close>SMA50`(상향) / 반대(하향) |

각 신호 결과: `{ticker, name, category:"technical", type, direction, detail}`
(예: type="RSI", direction="과매수", detail="73.2"). 한 종목이 여러 신호 가능.

**기술 임계값(RSI 70/30, BB 2σ, SMA50, MACD signal 9)은 고정**(표준값, 설정 단순화).

### 4.2 비중 편향 신호 (포트폴리오 전체, 각 on/off + 임계값%)

| 신호 | 발동 조건 | 기본 임계값 |
|------|----------|------------|
| 단일 종목 과중 | 어떤 종목 `weight_pct` ≥ `threshold_asset_pct` | 30% |
| 단일 자산군 과중 | 어떤 자산군 `weight_pct` ≥ `threshold_class_pct` | 60% |

결과: `{category:"concentration", type, name, detail}` (예: "삼성전자 62.2%").

### 4.3 데이터 요건

SMA50 + MACD(26) 위해 종목당 일봉 약 **120일** 조회(`get_history(asset, 120)`).
봉 부족(신규상장/짧은 이력)으로 지표가 NaN이면 해당 신호 스킵. manual·무이력 종목은 기술 신호 전체 스킵.

## 5. 설정 · 스케줄 · API

### 5.1 설정 — 신규 `risk_signal` 카테고리 (settings_manager, 신규 마이그레이션 없음)

| 키 | 의미 | 기본값 |
|----|------|--------|
| `enabled` | 기능 전체 on/off | false |
| `sig_rsi` / `sig_macd` / `sig_bollinger` / `sig_ma` | 기술 신호 각 on/off | true |
| `sig_concentration_asset` / `sig_concentration_class` | 비중 신호 각 on/off | true |
| `threshold_asset_pct` / `threshold_class_pct` | 비중 임계값(%) | 30 / 60 |

(불리언은 "true"/"false" 문자열, 임계값은 숫자 문자열 — 기존 settings 관례.)

### 5.2 스케줄 — 기존 `schedules` 재사용

`feature_type="risk_signal"`, `target_id=0`(증시요약·리포트 패턴). 디스패처에 `handle_risk_signal`
등록(best-effort, `TelegramNotConfigured` swallow). **휴장일 스킵 없음** — 포트폴리오 전역(혼합 시장)이라
단일 캘린더에 매이지 않음. 사용자가 days_of_week로 요일 제어(B 리포트와 동일).

### 5.3 API — 신규 `app/routers/risk_signal.py` (`/api/risk-signal`)

| 메서드 | 경로 | 동작 |
|--------|------|------|
| GET | `/settings` | 설정 반환 |
| PUT | `/settings` | 설정 저장 |
| GET | `/schedule` | 스케줄 조회 |
| PUT | `/schedule` | 스케줄 저장 |
| DELETE | `/schedule` | 스케줄 삭제 |
| POST | `/preview` | 지금 스캔 → 다이제스트 텍스트만 반환(발송 안 함) |
| POST | `/send` | 지금 스캔 → 텔레그램 발송(미설정 409) |

`/schedule` 라우트는 동적 세그먼트가 없어 충돌 없음. main.py에 라우터 등록.

## 6. 프론트엔드

전용 페이지 없음. **설정 페이지에 "위험신호" 섹션 추가**(AI 리포트 섹션 패턴):
- 전체 활성화 토글(`enabled`).
- 기술 신호 체크박스 4개(RSI/MACD/볼린저/SMA50 돌파).
- 비중 편향 체크박스 2개 + 임계값 입력(%) 각 1개(단일 종목 30 / 단일 자산군 60).
- 자동 발송 스케줄(시각 + 요일 + 사용) — 리포트 스케줄 UI 재사용.
- 버튼: "설정 저장", "스케줄 저장", "지금 미리보기"(→ /preview, 텍스트를 패널에 `whitespace-pre-wrap`),
  "지금 보내기"(→ /send, 미설정 안내).

`api.ts`: `getRiskSignal/saveRiskSignal`, `getRiskSchedule/saveRiskSchedule`,
`previewRiskSignal`(텍스트), `sendRiskSignal` 추가.

## 7. 에러 처리

- **비활성**(`enabled=false`): preview/send/핸들러 조기 종료(핸들러 조용히 스킵, preview는 빈/안내 다이제스트).
- **종목 시세·이력 실패**(history 에러·manual·무이력·봉부족): 해당 종목 기술 신호만 스킵, 스캔 계속. 비중 무관.
- **신호 0건**: "현재 위험신호가 없습니다" 다이제스트 — preview/send 정상.
- **스케줄 자동 발송**: best-effort, 한 종목 실패가 전체를 막지 않고 로깅, `TelegramNotConfigured` swallow.
- **텔레그램 미설정**: `/send` 409.

## 8. 테스트 (invest_test 격리 / 순수함수는 DB 불필요)

- `evaluator`: 순수 단위테스트 — 합성 DataFrame으로 RSI 과매수/과매도, MACD 골든/데드, BB 상/하단 이탈,
  MA 상/하향 돌파 각 경계 + off 토글 미발동; 비중 단일종목/자산군 임계 경계 + off.
- `scanner`: get_portfolio/get_history/calculate_indicators mock → 신호 수집 + manual/무이력 스킵 + 비중 병합.
- `message`: 신호 목록 → 다이제스트(0건 메시지 포함).
- `risk_service`: `build_and_send` 게이팅(enabled) + telegram mock.
- 라우터: settings GET/PUT, schedule GET/PUT/DELETE, preview(텍스트), send(미설정 409).
- 스케줄 디스패처: `risk_signal` 핸들러 `_is_due` 분기 + best-effort.
- **실 텔레그램 스모크는 사용자 확인(프로덕션).**

## 9. 비목표 (YAGNI)

- 기술 임계값(RSI 등) 사용자 설정(표준값 고정).
- 종목별 opt-in 선택(보유 전체 자동).
- 엣지트리거 실시간 푸시·재무장(가격알림이 담당; 일별 다이제스트 채택).
- 신호 이력 DB 저장, 전용 조회 페이지, 현금 과소 신호, 주봉 신호, LLM 조언.
- 휴장일/시장 캘린더 스킵(요일 설정으로 대체).

## 10. 단계 내 위치

3단계(AI 리포트 + 투자저널 + 위험신호) 중 **C(위험신호·매수매도 도움)**. A(스냅샷)·B(리포트) 위에 구축.
남은 후속: D(투자저널).
