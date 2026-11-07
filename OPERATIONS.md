# Binance BTC 전수 거래량 수집기

기존 매매일지와 독립된 프로그램. Binance API 키 없이 공개 시장 데이터만 사용합니다.

## 먼저 실제 검증

Actions의 `BTC market validation and collection`을 수동 실행하거나 프로그램 커밋으로 실행합니다. `data/latest.json`에서 expected_count, ticker_count, history_count, short_term_count, complete 및 failures를 확인합니다. 공식 exchangeInfo가 실패하면 전체 수는 null(미확인)이며 절대 0개 또는 전수 성공으로 표시하지 않습니다. 종목 목록을 수집 전후 비교하며 달라지면 전수 성공을 보류합니다.

검증 성공 시에만 data/validation.json이 생깁니다. 매일 UTC 22:20(다음 날 한국시간 07:20)에 1회 예약합니다. workflow_dispatch 수동 실행도 지원합니다. 변경 커밋만으로 시장 수집을 실행하지 않습니다. GitHub 호스팅 러너의 지역에 따라 Binance가 HTTP 451로 차단될 수 있습니다. 공식 시장 데이터 전용 도메인도 실패하면 성공으로 표시하지 않습니다.

GitHub Actions는 정시 실행 SLA가 없습니다. 07:20 KST는 전날 22:20 UTC이며 예약이 지연되면 실제 조회 시각을 표시합니다. 모든 실행은 실제 수집 시작 시각의 한국 날짜로 daily 파일을 남깁니다. 07:40 보고에서 collection_date_kst, started_at, finished_at, complete, execution.event와 execution.actual_started_at_kst를 확인해야 합니다. 수동 실행 자료를 07:20 자동 수집 자료로 표시하지 마세요. 정확한 07:20 스냅샷이 필수라면 별도 상시/예약 실행 환경이 필요합니다.

## 분석

- quoteAsset=BTC, status=TRADING, isSpotTradingAllowed=true 종목 전수.
- ticker/24hr quoteVolume은 BTC 거래대금, priceChangePercent는 별개 가격 지표.
- 24h 급증 = 현재 이동식 24시간 BTC 거래대금 / 직전 완결 UTC 7일 일평균. 비교 구간은 다르고 일부 겹칠 수 있습니다.
- 1h 급증 = 직전 완결 1시간 / 그 이전 168시간 시간평균.
- 4h 급증 = 직전 완결 4시간 합 / 그 이전 168시간의 4시간당 평균.
- 일봉 7개가 없는 신규 종목 등은 기준값 없음으로 표시합니다. 누락·중복 캔들은 실패 처리하며 임의로 0을 넣지 않습니다.
- 기본 저유동성 경고는 24h 1 BTC 미만이며 MIN_BTC 환경변수로 조정합니다. 평균 0이면 배수를 계산하지 않습니다.

## 보관 및 접근

매회 data/runs/<조회시각>/report.json, volume.csv, surge.csv를 Git에 보존합니다. CSV는 실패 종목도 마지막에 순위 없이 포함합니다. report.json에는 상위 20개, 단기 급증, 요청 출처·시각·실패 기록이 있습니다. data/latest.json 및 data/daily/YYYY-MM-DD.json은 읽기 전용 공개 조회용입니다. Actions artifact는 30일 보조 보관이며 영구 저장 수단은 Git 이력입니다. 삭제 전까지 보존되며 데이터가 커지면 객체 저장소로 옮기는 것이 좋습니다.

공개 URL(첫 실행·저장 성공 후 사용 가능):
https://raw.githubusercontent.com/leeireum/binance-btc-volume/main/data/latest.json
https://raw.githubusercontent.com/leeireum/binance-btc-volume/main/data/daily/YYYY-MM-DD.json

기존 ChatGPT 07:40 보고에 추가할 지시: "한국시간 오늘 날짜 daily JSON을 읽고 started_at, finished_at, complete, expected_count, ticker_count, history_count를 확인한다. 없거나 실패·누락이면 이를 명시한다. 오래된 자료를 오늘 자료로 대체하지 않는다. 전체 및 급증 상위 20개와 단기 급증, 저유동성 경고, 실패와 출처를 보고한다. 거래량 증가를 가격 상승으로 해석하지 않는다."

비밀값이나 환경변수 덤프는 저장하지 않습니다. workflow는 공개 데이터 경로만 커밋합니다. 공개 저장소 표준 GitHub 호스팅 러너는 통상 무료지만 정책·사용량 및 저장 용량은 계정에서 확인해야 합니다. 공개 저장소 예약은 장기간 활동이 없으면 비활성화될 수 있습니다.

## 대체 자료의 한계

공식 API 다음으로 공식 ZIP 저장소, CoinGecko 첫 페이지, CoinMarketCap HTML을 순차 확인하고 결과를 기록합니다. ZIP은 ETHBTC 표본 파싱, CoinGecko는 첫 페이지 표본만 검증합니다. CMC는 HTML 접근만 확인하며 거래쌍 파서가 구현되지 않았습니다. 이들은 현재 활성 종목 전수와 동일 시간대 거래대금을 보장하지 않으므로 공식 경로 실패를 복구한 전수 데이터로 사용하지 않습니다. 대체 자료 전수 수집 기능은 아직 구현되지 않았습니다.

로컬 실행: Python 3.12에서 `python -m unittest -v test_collector`, `python collector.py`. 외부 라이브러리는 필요 없습니다. 실패 종료 코드 2라도 보고서는 저장됩니다.

## 최초 실데이터 검증 결과

2026-11-06 12:54:35~12:55:12 KST, GitHub Actions 실행 42159323881: 전체 26개, ticker 26개, 7일 일봉 26개, 단기 이력 26개, 누락 0개, 수집 전후 종목 목록 동일. api.binance.com은 HTTP 451, data-api.binance.vision 공식 API 성공. 과거 저장소 ETHBTC 표본 ZIP 파싱 성공, CoinGecko 첫 페이지 BTC 페어 2개 확인, CMC HTML 접근 성공(데이터 파싱 미검증). 대체 자료는 전수 수집 성공으로 표시하지 않았습니다.



## 2026-11-07 저장 및 예약 점검

#4는 이전 커밋에서 checkout한 상태로 공통 latest/validation/CSV를 갱신한 뒤, 먼저 저장된 #3 결과에 rebase하여 충돌했습니다. concurrency는 실행을 직렬화해도 이미 선택된 오래된 checkout 커밋까지 갱신하지 않습니다.

수집은 Git에 저장하지 않는 collection-output 독립 출력 폴더를 사용하고, 먼저 artifact에 원본을 보관합니다. persist_results.py는 매번 최신 origin/main에서 임시 worktree를 만들고 새 결과만 반영합니다. push 거절 시 최신 head에서 최대 5회 다시 작성합니다. 원격 force-push/rebase나 기존 이력 삭제는 하지 않습니다. runs는 불변이며 최신 포인터는 조회 시각을 비교합니다. daily와 validation은 완전한 수집을 불완전한 수집보다 우선하고, 같은 조건에서는 늦은 수집을 선택합니다. 실패 결과도 runs에 모두 남습니다. 네트워크/권한 문제로 5회 저장이 실패하면 Actions는 실패하며 artifact에서 복구해야 합니다.

JSON 기존 키는 유지하고 execution, collection_date_kst만 추가합니다. execution에는 event, manual, run_id, run_attempt, run_url, workflow_created_at, actual_started_at_kst, nominal_schedule_at_kst, schedule_delay_seconds가 있습니다. 예약 예정 시각은 수집 이전 가장 최근 07:20으로 추정하며 하루 이상 지연되면 정확한 원래 예정일을 알 수 없습니다. 실제 시작 시각을 수정하지 않습니다.

API 조사에서 #5는 11월 7일 08:16 KST workflow_dispatch 성공, #6은 11:01 KST schedule 성공이 확인됐습니다. #6의 run_attempt=1이며 예약 생성이 약 3시간 42분 지연된 기록입니다. 예약 문법/기본 브랜치 오류 증거는 없고 GitHub 내부 지연 원인은 공개 로그만으로 확정할 수 없습니다. cron은 20 22 * * * 그대로 유지합니다. 수정 이후 다음 예약(11월 8일 07:20 KST)은 검증 대기입니다.

### 다음 예약 확인

인증된 gh가 있는 저장소에서 `python check_schedule.py` 실행: workflow 활성 여부, 오늘 07:20 이후 schedule 실행의 event/시각/결론/링크를 조회합니다. 07:40까지 실행이 없으면 missing_or_delayed로 종료 코드 2를 반환합니다. 검증 도구 자체는 새 수집을 시작하거나 별도 예약하지 않습니다. Actions 화면에서 필터 `event:schedule`로 확인해도 됩니다.

수집 이후에는 data/last_schedule.json에 마지막 예약 수집의 실행 ID와 시각이 저장됩니다. data/daily/YYYY-MM-DD.json은 수동 자료일 수 있으므로 이것만으로 예약 성공을 판단하지 마세요. GitHub run의 conclusion=success와 last_schedule.json의 complete=true 및 run_id 일치가 모두 필요합니다. 지연이 20분을 넘으면 07:40 보고가 늦거나 누락될 수 있습니다. 이 수집기의 예약만으로는 자신이 아예 실행되지 않은 것을 즉시 감지할 수 없으므로 07:40 보고 주체에서 검증 도구/API와 데이터 날짜를 확인해야 합니다.
