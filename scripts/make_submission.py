r"""제출 ZIP을 만든다: 커밋된 파일만(git archive) 담고, 키·DB·가상환경이 섞이지 않았는지 검사한다.

사용: .venv\Scripts\python.exe scripts\make_submission.py [--data "제주특별자치도 상가(상권) 정보.csv"]
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


def build(output: Path, data: Path | None) -> list[str]:
    """ZIP을 만들고 담은 파일 목록을 돌려준다. 문제가 있으면 ZIP을 남기지 않고 ValueError."""
    if git('status', '--porcelain', '--untracked-files=no').strip():
        raise ValueError('커밋하지 않은 변경이 있습니다. 커밋한 상태에서 다시 실행하세요.')
    archive = ZipFile(io.BytesIO(git('archive', '--format=zip', 'HEAD')))
    entries = [(info.filename, archive.read(info)) for info in archive.infolist() if not info.is_dir()]
    if data:
        entries.append((DATA_NAME, data.read_bytes()))
    errors = [issue for name, content in entries if name != DATA_NAME for issue in problems(name, content)]
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
    args = parser.parse_args(argv)
    commit = git('rev-parse', '--short', 'HEAD').decode().strip()
    output = args.output or ROOT / 'dist' / f'{FOLDER}_{commit}.zip'
    try:
        names = build(output, args.data)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f'ZIP을 만들지 않았습니다: {error}')
        return 1
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    print(f'{output} ({output.stat().st_size / 1024 / 1024:.1f}MB, 파일 {len(names)}개, 커밋 {commit})')
    print(f'SHA-256 {digest}')
    if args.data:
        print(f'데이터 {DATA_NAME} SHA-256 {hashlib.sha256(args.data.read_bytes()).hexdigest()}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
