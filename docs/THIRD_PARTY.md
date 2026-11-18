# 모델·외부 API·오픈소스 명세

## 모델과 외부 API

| 구성 | 사용 범위·상태 | 공식 출처 |
|---|---|---|
| OpenAI API | Gemini와 같은 기능. 기본 모델 ID `gpt-5.4-mini`, 환경 변수로 변경. 2026-11-18 실키로 5가지 기능 호출 성공(검색 Agent 4.8~9.4초, 비교 해설 3.9초, 문의 질문 2.5초, 견적 추출 2.6초), 실제 데이터 12개 질의 모두 성공·429 없음 | https://platform.openai.com/docs |
| Gemini API | 검색 Agent(분류 확인·검색·지역 집계 도구)·비교 해설·문의 질문·견적 추출. OpenAI 호환 엔드포인트 사용. 기본 ID `gemini-3.5-flash-lite`, 환경 변수로 변경. 2026-11-17 실키로 5가지 기능 호출 성공(호출당 1.8~6.2초). 같은 날 `gemini-3.8-flash`는 503 수요 과다·35초 시간 초과 반복 | https://ai.google.dev/gemini-api/docs/openai |
| 국세청 상태조회 | `/api/nts-businessman/v1/status`, 사업자번호로 상태·폐업일 조회. 2026-11-18 실키로 공개된 법인 사업자번호를 조회해 0.56초에 '계속사업자', 24시간 캐시 재사용, 미등록 번호 '확인 불가'를 확인. 상가 데이터에는 사업자번호가 없어 그 업소에는 쓰이지 않는다 | https://www.data.go.kr/data/15081808/openapi.do |
| Pretendard GOV (글꼴) | 화면 글꼴. `.streamlit/config.toml`에서 jsDelivr CDN(v1.3.9, `pretendardvariable-gov-dynamic-subset.min.css`)으로 불러오고, 인터넷이 없으면 맑은 고딕·sans-serif로 대체. SIL Open Font License 1.1 | https://github.com/orioncactus/pretendard |
| KRDS 디자인 기준 | 범정부 UI/UX 디자인 시스템 표준형 색상(primary-50 `#256ef4` 등)·단계 표시기·신청서 작성 패턴을 참고해 화면 색과 구성을 정함. 코드·이미지는 가져오지 않음 | https://www.krds.go.kr |
| multilingual-e5-small | 선택 설치 CPU 로컬 임베딩, query/passages prefix와 코사인 검색. 모델 파일 미탑재·실모델 미검증 | https://huggingface.co/intfloat/multilingual-e5-small |

OpenAI `gpt-5.4-mini` 표준 요금은 입력 100만 토큰당 0.75달러, 출력 4.50달러다(2026-11-18 https://developers.openai.com/api/docs/pricing). 실제 호출 토큰으로 계산한 비용은 [결과 설명](RESULTS.md)에 있다. LLM 공급자·모델 ID는 화면에 표시한다. API 응답 품질·이용 가능 모델·요금은 계정별로 실제 확인해야 한다. 외부 API 전송은 `ALLOW_EXTERNAL_DATA`로 차단하며 기본값 false다. 이 설정은 원천 이용 허가를 대체하지 않는다.

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
