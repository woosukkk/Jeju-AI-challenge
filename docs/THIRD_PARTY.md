# 모델·외부 API·오픈소스 명세

## 모델과 외부 API

| 구성 | 사용 범위·상태 | 공식 출처 |
|---|---|---|
| OpenAI API | 검색 도구 호출·후보 선택·견적 추출. 기본 모델 ID `gpt-5.4-mini`, 환경 변수로 변경. 실키 미검증 | https://platform.openai.com/docs |
| Gemini API | 동일 기능, OpenAI 호환 엔드포인트 사용. 기본 ID `gemini-3.8-flash`, 환경 변수로 변경. 실키 미검증 | https://ai.google.dev/gemini-api/docs/openai |
| 국세청 상태조회 | `/api/nts-businessman/v1/status`, 사업자번호로 상태·폐업일 조회. 실키 미검증 | https://www.data.go.kr/data/15081808/openapi.do |
| multilingual-e5-small | 선택 설치 CPU 로컬 임베딩, query/passages prefix와 코사인 검색. 모델 파일 미탑재·실모델 미검증 | https://huggingface.co/intfloat/multilingual-e5-small |

LLM 공급자·모델 ID는 화면에 표시한다. API 응답 품질·이용 가능 모델·요금은 계정별로 실제 확인해야 한다. 외부 API 전송은 `ALLOW_EXTERNAL_DATA`로 차단하며 기본값 false다. 이 설정은 원천 이용 허가를 대체하지 않는다.

## 직접 사용하는 라이브러리

설치된 패키지 메타데이터 기준이다. 전체 전이 의존성 버전은 `requirements-lock.txt`, 라이선스 원문은 각 설치 패키지의 dist-info/LICENSE 또는 공식 소스에 있다. 외부 패키지 바이너리를 ZIP에 동봉하지 않고 설치 명세로 제공한다.

| 라이브러리 | 검증 버전 | 역할 | 라이선스 |
|---|---|---|---|
| Streamlit | 1.67.0 | 기본 UI·로컬 실행·AppTest | Apache-2.0 |
| pandas | 2.3.3 | CSV/XLSX 입력 | BSD-3-Clause |
| NumPy | 2.4.6 | 선택 임베딩의 벡터 연산 | BSD-3-Clause 및 동봉 구성별 0BSD/MIT/Zlib/CC0-1.0 |
| Pydantic | 2.14.3 | 신뢰 경계의 입력·LLM 결과 검증 | MIT |
| OpenAI Python SDK | 2.54.0 | OpenAI/Gemini 호환 호출 | Apache-2.0 |
| httpx | 0.28.1 | 국세청 HTTP 요청 | BSD-3-Clause |
| openpyxl | 3.1.5 | XLSX 읽기 | MIT |
| pypdf | 6.21.4 | 텍스트 PDF 읽기 | BSD-3-Clause |
| python-dotenv | 1.2.4 | 로컬 환경 설정 | BSD-3-Clause |
| pytest | 9.2.0 | 개발 테스트 | MIT |
| ty | 0.0.104 | 개발 타입 검사 | MIT (설치된 dist-info/licenses/LICENSE 확인) |

선택 패키지 `sentence-transformers`는 아직 설치하지 않았다. 선택 기능을 탑재할 때 실제 버전·전이 의존성·모델 카드의 이용조건을 함께 확정한다. 본 프로젝트 자체의 오픈소스 공개 라이선스는 아직 지정하지 않았다.
