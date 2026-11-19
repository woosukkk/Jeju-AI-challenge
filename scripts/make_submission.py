r"""제출 ZIP을 만든다: 커밋된 파일만(git archive) 담고, 키·DB·가상환경이 섞이지 않았는지 검사한다.

사용: .venv\Scripts\python.exe scripts\make_submission.py [--data "제주특별자치도 상가(상권) 정보.csv"] [--env 평가용.env]
--data를 주면 원본 CSV를 data_source/jeju_store.csv로 함께 넣는다(평가 PC에서 import_data.bat으로 반입).
"""
import argparse
import hashlib
import io
import re
import subprocess
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
FOLDER = 'trade-itsuda'  # 압축 프로그램마다 한글 이름 처리가 달라 영문으로 둔다.
DATA_NAME = 'data_source/jeju_store.csv'
# 담기면 안 되는 경로: 실제 키 설정, 로컬 DB·사용자 견적, 가상환경, 모델, 내려받은 원본 표.
FORBIDDEN = re.compile(r'(^|/)(\.env(\..*)?|\.venv/.*|\.git/.*|models/.*|data/.*|outputs/.*)$|\.(sqlite3?|db|xlsx|xls)$')
ALLOWED_ENV = {'.env.example'}
# 개발 과정 메모(다음 개발자·AI용 인수인계, 할 일 목록, 날짜별 작업 기록)는 저장소에만 두고 제출 ZIP에는 넣지 않는다.
# 제출물에 필요한 검증 기록은 docs/RESULTS.md에 있다.
DEV_NOTES = {'docs/TODO.md', 'docs/HANDOFF.md', 'docs/IMPLEMENTATION.md', 'docs/PROPOSAL_OUTLINE.md', 'docs/PROGRESS.md'}
# 공급자 키 형태(Google AIza…, OpenAI sk-…)가 본문에 들어갔는지 검사한다.
SECRET = re.compile(rb'AIza[0-9A-Za-z_\-]{30,}|sk-[A-Za-z0-9_\-]{20,}')


def git(*args: str) -> bytes:
    return subprocess.run(['git', *args], cwd=ROOT, check=True, capture_output=True).stdout


def problems(name: str, content: bytes) -> list[str]:
    found = []
    if FORBIDDEN.search(name) and Path(name).name not in ALLOWED_ENV:
        found.append(f'담으면 안 되는 파일: {name}')
    if SECRET.search(content):
        found.append(f'키로 보이는 문자열: {name}')
    return found


ENV_NAME = '.env'


def evaluation_env(text: str) -> str:
    """평가용 .env를 새로 쓴다: OpenAI만, 외부 전송 허용, 상대 경로 DB, 세션당 AI 한도.

    대회 규칙상 데이터 API 키(공공데이터포털 국세청 키)는 넣지 않고, Gemini 키도 넣지 않는다(평가는 OpenAI만).
    키가 없거나 공급자가 openai가 아니면 ValueError.
    """
    values = {}
    for line in text.splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            key, value = line.split('=', 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    if values.get('LLM_PROVIDER', 'openai').lower() != 'openai':
        raise ValueError('평가용 .env는 LLM_PROVIDER=openai여야 합니다.')
    key = values.get('OPENAI_API_KEY', '')
    if not key:
        raise ValueError('평가용 .env에 OPENAI_API_KEY가 없습니다.')
    model = values.get('LLM_MODEL', '')
    if model.lower() in {'openai', 'gemini'} or ' ' in model:
        raise ValueError(f'LLM_MODEL에는 모델 이름(예: gpt-5.4-mini)을 적거나 비워 두세요. 지금 값: {model}')
    limit = values.get('AI_SESSION_LIMIT', '30') or '30'
    if not limit.isdigit():
        raise ValueError('AI_SESSION_LIMIT는 0 이상의 정수여야 합니다.')
    return '\n'.join([
        '# 평가용 설정: 사용 한도를 건 OpenAI 키(평가 후 폐기). 국세청 키는 공공데이터포털에서 직접 발급해 넣는다(매뉴얼 참고).',
        'LLM_PROVIDER=openai', f'LLM_MODEL={model}', f'OPENAI_API_KEY={key}',
        'GEMINI_API_KEY=', 'NTS_API_KEY=', 'ALLOW_EXTERNAL_DATA=true',
        'DATABASE_PATH=data/trade_itsuda.sqlite3', f'AI_SESSION_LIMIT={limit}', ''])


def build(output: Path, data: Path | None, env: Path | None = None) -> list[str]:
    """ZIP을 만들고 담은 파일 목록을 돌려준다. 문제가 있으면 ZIP을 남기지 않고 ValueError."""
    if git('status', '--porcelain', '--untracked-files=no').strip():
        raise ValueError('커밋하지 않은 변경이 있습니다. 커밋한 상태에서 다시 실행하세요.')
    archive = ZipFile(io.BytesIO(git('archive', '--format=zip', 'HEAD')))
    entries = [(info.filename, archive.read(info)) for info in archive.infolist()
               if not info.is_dir() and info.filename not in DEV_NOTES]
    if data:
        entries.append((DATA_NAME, data.read_bytes()))
    errors = [issue for name, content in entries if name != DATA_NAME for issue in problems(name, content)]
    if env:
        # 검사를 마친 뒤에 넣는다: 평가용 키는 이 파일 하나에만 의도적으로 들어간다.
        entries.append((ENV_NAME, evaluation_env(env.read_text(encoding='utf-8')).encode('utf-8')))
    if errors:
        raise ValueError('\n'.join(errors))
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, 'w', ZIP_DEFLATED) as zipped:
        for name, content in entries:
            zipped.writestr(f'{FOLDER}/{name}', content)
    return [name for name, _ in entries]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='제출 ZIP 만들기')
    parser.add_argument('--data', type=Path, help='함께 넣을 상가(상권) 정보 CSV (선택)')
    parser.add_argument('--output', type=Path, help='기본: dist/trade-itsuda_<커밋>.zip')
    parser.add_argument('--env', type=Path, help='평가용 .env (OpenAI 키). OpenAI 키만 담아 ZIP의 .env로 넣는다')
    args = parser.parse_args(argv)
    commit = git('rev-parse', '--short', 'HEAD').decode().strip()
    output = args.output or ROOT / 'dist' / f'{FOLDER}_{commit}.zip'
    try:
        names = build(output, args.data, args.env)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f'ZIP을 만들지 않았습니다: {error}')
        return 1
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    print(f'{output} ({output.stat().st_size / 1024 / 1024:.1f}MB, 파일 {len(names)}개, 커밋 {commit})')
    print(f'SHA-256 {digest}')
    if args.data:
        print(f'데이터 {DATA_NAME} SHA-256 {hashlib.sha256(args.data.read_bytes()).hexdigest()}')
    print('평가용 .env 포함 (OpenAI 키 있음, 국세청·Gemini 키 제외)' if args.env else '평가용 .env 없음: 심사 PC에서는 AI가 꺼진 채 실행됩니다.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
