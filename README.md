# 거래잇수다

제주 도민(예비 창업자·소상공인·소규모 기업 담당자)이 필요한 품목의 공급처를 찾고, 기존 거래처와 같은 조건으로 견적을 비교하고, 업체별 문의를 준비하도록 돕는 AI Agent입니다. 제주데이터허브 「제주특별자치도 상가(상권) 정보」 57,347곳을 검색하며, 제주빅데이터센터 PC(Windows)에서 GPU 없이 실행됩니다.

## 설치와 실행 (Windows, Python 3.11)

1. `setup.bat` 실행: 가상환경을 만들고 패키지를 설치합니다(첫 설치 약 3~4분, 인터넷 필요).
2. `import_data.bat` 실행: 제출 ZIP에 든 `data_source\jeju_store.csv`(상가 데이터)를 로컬 DB로 가져옵니다(약 10초).
3. `run.bat` 실행 후 브라우저에서 <http://localhost:8501>을 엽니다. 서버를 처음 켠 뒤 첫 화면은 데이터를 읽느라 몇 초~십여 초 걸립니다.

AI 설정은 `.env`에 있습니다. 제출 ZIP에는 사용 한도를 건 **평가용 OpenAI 키가 든 `.env`** 가 들어 있어 위 3단계만으로 AI가 켜집니다(평가 후 키 폐기). 직접 설정할 때는 `.env.example`을 `.env`로 복사하고 `OPENAI_API_KEY`와 `ALLOW_EXTERNAL_DATA=true`를 넣습니다. 키가 없으면 키워드 검색·직접 입력으로 모든 단계를 쓸 수 있습니다. 자세한 사용법과 오류 대처는 [사용자 매뉴얼](docs/MANUAL.md)에 있습니다.

## 무엇을 하나요

1. **필요 품목**: "가게 간판을 새로 달고 싶어요"처럼 일상어로 적습니다. 기존 거래처가 있으면 이름도 적습니다.
2. **지역**: 시 → 읍·면·동을 고릅니다.
3. **후보 고르기**: AI Agent가 업종 분류 확인·조건 검색·지역별 집계 도구를 스스로 써서 후보를 찾고, 그 과정을 실시간으로 보여 줍니다. 요청이 모호하면 질문하고, 답하면 다시 찾습니다.
4. **문의 준비**: 조건을 한 번 적으면 업체별 문의 초안을 만들고, AI가 업체 업종에 맞춘 확인 질문을 덧붙입니다(발송은 사용자가 직접).
5. **견적 입력**: 견적서 텍스트·PDF를 붙여 넣으면 AI가 칸을 채우고, 못 찾은 값은 주황으로 표시합니다. 국세청 사업자 상태도 확인할 수 있습니다.
6. **비교 결과**: 같은 조건일 때만 차액을 계산해 결론과 업체별 총액을 보여 주고, AI가 비교표를 해설합니다. HTML 보고서(검색 과정·데이터 해시 포함)와 CSV로 내려받습니다.

금액 계산은 AI가 아니라 코드(Decimal)가 하고, AI 요약의 숫자는 도구 결과나 비교표에 있는 값만 허용합니다.

## 제출물 안내

| 요구 항목 | 파일 |
|---|---|
| AI Agent 기획서 | `docs/proposal.pdf` |
| 실행 소스 코드 | `app.py`(화면), `trade_itsuda/`(Agent·프롬프트 `agent.py`, 검색 `retrieval.py`, 비교 `comparison.py`, 반입 `ingest.py`, 국세청 `business.py`, 보고서 `exporting.py`), `tests/` |
| 실행환경·매뉴얼 | 이 README, [사용자 매뉴얼](docs/MANUAL.md), `requirements.txt`(의존성), `requirements-lock.txt`(검증 버전), `.env.example`(환경변수 예시), `setup.bat`·`import_data.bat`·`run.bat` |
| 데이터 활용 명세 | [데이터 활용 명세](docs/DATA_USAGE.md): 사용 데이터·출처·이용조건·열 대응·전처리 |
| 모델·API·오픈소스·AI 도구 | [모델·API·오픈소스 명세](docs/THIRD_PARTY.md): 사용 모델, 외부 API, 라이브러리, 개발에 쓴 AI 도구 |
| 결과 설명자료 | [결과 설명과 검증](docs/RESULTS.md): Agent 구조, 실제 데이터 검색 측정, 비용, 검증 방법·한계 / [제품 기획](docs/PRODUCT.md): 문제 정의 / 기획서 8장: 센터 활용 방안 |

개발 과정 기록(`docs/PROGRESS.md`, `docs/TODO.md`, `docs/HANDOFF.md`, `docs/IMPLEMENTATION.md`)은 참고용입니다.

## 검증

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

자동 테스트는 합성 데이터와 모의 AI 응답을 씁니다. 실제 데이터 검색 품질·시간 측정은 `scripts\measure_search.py`로 다시 잴 수 있고, 결과는 [결과 설명](docs/RESULTS.md)에 있습니다.

## 데이터와 보안

- 상가 데이터 원천(공공데이터포털)의 이용허락범위는 "제한 없음"입니다. 공개 GitHub 저장소에는 CSV·DB를 올리지 않고 제출 ZIP에만 넣습니다.
- AI에는 요청 문장과 후보의 상호·업종·지역 등 공개 정보만 보냅니다. 견적은 이 PC의 로컬 DB에만 저장됩니다.
- 앱은 이 PC(localhost)에서만 열립니다. 공용 PC에서는 사용 후 5단계에서 견적을 지우세요.
