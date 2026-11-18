# 거래잇수다

제주 도민인 예비 창업자·소상공인·소규모 기업 담당자가 거래처를 찾고 기존 업체와 비교하며 견적 문의를 준비하는 로컬 AI Agent입니다.

다음 AI/개발자는 **[인수인계](docs/HANDOFF.md) → [남은 작업과 완료 기준](docs/TODO.md)** 순서로 읽고 이어갑니다. 제주 상가 데이터 반입, Gemini 실호출, 제출 ZIP·새 폴더 설치 확인까지 했고, 최종 기획서와 평가 PC 성능 측정이 남아 있습니다. 구현된 기능과 실검증 여부는 [진행 기록](docs/PROGRESS.md)에서 구분합니다.

## 시작

Windows / Python 3.11에서 `setup.bat`으로 설치하고, 제주 상가 CSV를 `data_source\jeju_store.csv`에 둔 뒤 `import_data.bat`으로 가져오고, `run.bat`으로 실행합니다. 화면은 6단계 진행형이며 범정부 디자인 시스템(KRDS) 색·글꼴과 제주 배경을 썼습니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m streamlit run app.py
```

키는 `.env`에만 설정합니다. `LLM_PROVIDER=openai`(기본, 권장) 또는 `gemini`를 선택하고 해당 공급자의 키를 넣습니다. AI를 켜려면 `ALLOW_EXTERNAL_DATA=true`도 설정합니다. 국세청 상태조회에는 별도의 `NTS_API_KEY`가 필요합니다. 기업·견적 자료의 외부 LLM 전송은 기본적으로 꺼져 있습니다. 승인된 자료일 때만 `ALLOW_EXTERNAL_DATA=true`로 설정합니다. 상세한 실행·데이터 반입 절차는 [사용자 매뉴얼](docs/MANUAL.md)을 참고하세요.

필수 제주 데이터는 제주데이터허브 「제주특별자치도 상가(상권) 정보」(2025-09-18 수집, 57,347곳)입니다. 원천 공공데이터포털의 이용허락범위는 "제한 없음"이지만 저장소에는 CSV·DB를 넣지 않습니다. 이용조건과 열 대응은 [데이터 활용 명세](docs/DATA_USAGE.md)에 있습니다. 데모 업체 4곳은 전부 가상입니다.

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

테스트는 합성 데이터와 모의 API 응답을 사용합니다. 실제 데이터 검색 측정은 `scripts\measure_search.py`, 제출 ZIP은 `scripts\make_submission.py`로 만듭니다. 실제 외부 API와 원본 데이터 검증 결과는 [결과 설명](docs/RESULTS.md)과 [진행 기록](docs/PROGRESS.md)에 별도로 적습니다.

테스트 실행 전 `requirements-dev.txt`도 설치합니다. 검증한 전체 패키지는 `requirements-lock.txt`에 고정했습니다. 로컬 의미 검색은 별도 설치 옵션이며 기본 실행에 필요하지 않습니다.

## 개발 방식

실제 기능 단위로 커밋합니다. 새 커밋 10개마다 한 번 푸시합니다. 재배포가 승인되지 않은 원본·명세 파일, 키, 로컬 DB와 사용자 견적은 Git에 올리지 않습니다.

- [제품 기획](docs/PRODUCT.md)
- [다음 AI/개발자 인수인계](docs/HANDOFF.md)
- [남은 작업과 완료 기준](docs/TODO.md)
- [구현 계획](docs/IMPLEMENTATION.md)
- [데이터 활용·이용조건](docs/DATA_USAGE.md)
- [결과 설명과 검증 범위](docs/RESULTS.md)
- [15쪽 기획서 목차](docs/PROPOSAL_OUTLINE.md)
- [모델·API·오픈소스 명세](docs/THIRD_PARTY.md)
