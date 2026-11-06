# Binance BTC 전수 거래량 수집기

기존 매매일지와 독립된 프로그램. Binance API 키 없이 공개 시장 데이터만 사용합니다.

## 먼저 실제 검증

Actions의 `BTC market validation and collection`을 수동 실행하거나 프로그램 커밋으로 실행합니다. `data/latest.json`에서 expected_count, ticker_count, history_count, short_term_count, complete 및 failures를 확인합니다. 공식 exchangeInfo가 실패하면 전체 수는 null(미확인)이며 절대 0개 또는 전수 성공으로 표시하지 않습니다. 종목 목록을 수집 전후 비교하며 달라지면 전수 성공을 보류합니다.

검증 성공 시에만 data/validation.json이 생깁니다. 그 다음 저장소 Settings → Secrets and variables → Actions → Variables에서 AUTO_COLLECT=true로 설정하면 매시간 UTC 20분(한국시간도 20분) 수집합니다. 검증이 통과하지 않으면 예약 수집이 실행되지 않습니다. GitHub 호스팅 러너의 지역에 따라 Binance가 HTTP 451로 차단될 수 있습니다. 공식 시장 데이터 전용 도메인도 실패하면 성공으로 표시하지 않습니다.

GitHub Actions는 정시 실행 SLA가 없습니다. 07:20 KST는 전날 22:20 UTC이며 예약이 지연되면 실제 조회 시각을 표시합니다. 07시대 실제 시작된 수집만 해당 날짜 daily 파일로 남기므로 08시 이후 지연 또는 실패 시 당일 보고서가 없을 수 있습니다. 07:30 보고에서 날짜와 조회 시각을 반드시 확인해야 합니다. 정확한 07:20 스냅샷이 필수라면 별도 상시/예약 실행 환경이 필요합니다.

## 분석

- quoteAsset=BTC, status=TRADING, isSpotTradingAllowed=true 종목 전수.
- ticker/24hr quoteVolume은 BTC 거래대금, priceChangePercent는 별개 가격 지표.
- 24h 급증 = 현재 이동식 24시간 BTC 거래대금 / 직전 완결 UTC 7일 일평균. 비교 구간은 다르고 일부 겹칠 수 있습니다.
- 1h 급증 = 직전 완결 1시간 / 그 이전 168시간 시간평균.
- 4h 급증 = 직전 완결 4시간 합 / 그 이전 168시간의 4시간당 평균.
- 일봉 7개가 없는 신규 종목 등은 기준값 없음으로 표시합니다. 누락·중복 캔들은 실패 처리하며 임의로 0을 넣지 않습니다.
- 기본 저유동성 경고는 24h 1 BTC 미만이며 MIN_BTC 환경변수로 조정합니다. 평균 0이면 배수를 계산하지 않습니다.

## 보관 및 접근

매회 data/runs/<조회시각>/report.json, volume.csv, surge.csv를 Git에 보존합니다. CSV는 실패 종목도 마지막에 순위 없이 포함합니다. report.json에는 상위 20개, 단기 급증, 요청 출처·시각·실패 기록이 있습니다. data/latest.json 및 data/daily/YYYY-MM-DD.json은 읽기 전용 공개 조회용입니다. Actions artifact는 7일 보조 보관이며 영구 저장 수단은 Git 이력입니다. 삭제 전까지 보존되며 데이터가 커지면 객체 저장소로 옮기는 것이 좋습니다.

공개 URL(첫 실행·저장 성공 후 사용 가능):
https://raw.githubusercontent.com/leeireum/binance-btc-volume/main/data/latest.json
https://raw.githubusercontent.com/leeireum/binance-btc-volume/main/data/daily/YYYY-MM-DD.json

기존 ChatGPT 07:30 보고에 추가할 지시: "한국시간 오늘 날짜 daily JSON을 읽고 started_at, finished_at, complete, expected_count, ticker_count, history_count를 확인한다. 없거나 실패·누락이면 이를 명시한다. 오래된 자료를 오늘 자료로 대체하지 않는다. 전체 및 급증 상위 20개와 단기 급증, 저유동성 경고, 실패와 출처를 보고한다. 거래량 증가를 가격 상승으로 해석하지 않는다."

비밀값이나 환경변수 덤프는 저장하지 않습니다. workflow는 공개 데이터 경로만 커밋합니다. 공개 저장소 표준 GitHub 호스팅 러너는 통상 무료지만 정책·사용량 및 저장 용량은 계정에서 확인해야 합니다. 공개 저장소 예약은 장기간 활동이 없으면 비활성화될 수 있습니다.

## 대체 자료의 한계

공식 API 다음으로 공식 ZIP 저장소, CoinGecko 첫 페이지, CoinMarketCap HTML을 순차 확인하고 결과를 기록합니다. ZIP은 ETHBTC 표본 파싱, CoinGecko는 첫 페이지 표본만 검증합니다. CMC는 HTML 접근만 확인하며 거래쌍 파서가 구현되지 않았습니다. 이들은 현재 활성 종목 전수와 동일 시간대 거래대금을 보장하지 않으므로 공식 경로 실패를 복구한 전수 데이터로 사용하지 않습니다. 대체 자료 전수 수집 기능은 아직 구현되지 않았습니다.

로컬 실행: Python 3.12에서 `python -m unittest -v test_collector`, `python collector.py`. 외부 라이브러리는 필요 없습니다. 실패 종료 코드 2라도 보고서는 저장됩니다.
