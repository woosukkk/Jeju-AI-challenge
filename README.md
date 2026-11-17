# 거래잇수다

제주 도민인 예비 창업자·소상공인·소규모 기업 담당자가 거래처를 찾고 기존 업체와 비교하며 견적 문의를 준비하는 로컬 AI Agent입니다.

## 시작

Windows / Python 3.11에서 `setup.bat`으로 설치하고 `run.bat`으로 실행합니다. 화면은 기본 Streamlit 구성입니다. 디자인 레퍼런스는 추후 반영합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m streamlit run app.py
```

키는 `.env`에만 설정합니다. `LLM_PROVIDER=openai` 또는 `gemini`를 선택하고 해당 공급자의 키를 넣습니다. 국세청 상태조회에는 별도의 `NTS_API_KEY`가 필요합니다. 기업·견적 자료의 외부 LLM 전송은 기본적으로 꺼져 있습니다. 승인된 자료일 때만 `ALLOW_EXTERNAL_DATA=true`로 설정합니다. 상세한 실행·데이터 반입 절차는 [사용자 매뉴얼](docs/MANUAL.md)을 참고하세요.

실제 기업 원본은 포함하지 않습니다. 데모 업체는 전부 가상이며, 데모로 챌린지의 필수 데이터 활용을 충족했다고 주장할 수 없습니다. `데이터명세서_kr.xlsx`는 실제 기업 관측 데이터가 아닙니다.

## 기능과 근거

- 신규 거래처 검색과 기존 업체 직접 등록·견적 비교
- 업종·제품·지역 검색, 출처·원본 기준일·검색 근거
- 동일 규격·단위·수량의 견적 비용 계산, 누락·유효기간 표시
- 견적 문의 초안과 비교 보고서 저장
- 실제 열람·비교 기록을 이용한 최근 인기 목록
- 국세청 상태조회 및 갱신 실패 시 마지막 성공 확인일 보존
- Gemini/OpenAI 요구사항 해석·도구 호출, 선택적인 로컬 의미 검색

정상 사업자 상태는 현재 품목 취급·납기·공급 능력·거래 안전을 보증하지 않습니다. 현재 가격·최소주문량은 사용자가 확인한 견적에 근거합니다.

## 검증

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

테스트는 합성 데이터와 모의 API 응답을 사용합니다. 실제 외부 API와 원본 데이터 검증 결과는 [진행 기록](docs/PROGRESS.md)에 별도로 적습니다.

## 개발 방식

실제 기능 단위로 커밋합니다. 새 커밋 10개마다 한 번 푸시합니다. 재배포가 승인되지 않은 원본·명세 파일, 키, 로컬 DB와 사용자 견적은 Git에 올리지 않습니다.

- [제품 기획](docs/PRODUCT.md)
- [구현 계획](docs/IMPLEMENTATION.md)
- [데이터 활용·이용조건](docs/DATA_USAGE.md)
