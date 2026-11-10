"""장 밖의 추가 노트북(시장노트, ELS 헤지 프로젝트)을 만든다.

extras/<이름>.py 를 '#%% md' / '#%% code' 표시로 셀을 나눠 notebooks/<이름>.ipynb 로 만들고,
처음부터 끝까지 실제로 실행해 결과를 담아 저장한다. 오류 출력이나 검증 '실패'가 있으면 0이 아닌 값으로 끝난다.

사용법: python tools/make_extras.py <이름> [...] | --all
"""
from __future__ import annotations

import sys
from pathlib import Path

import nbformat

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_notebooks import errors, execute, failed_checks  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SRC, NB_DIR = ROOT / "extras", ROOT / "notebooks"


def cells_from(text: str) -> list:
    cells, kind, buf = [], None, []

    def flush():
        body = "\n".join(buf).strip("\n")
        if kind and body:
            cells.append(nbformat.v4.new_markdown_cell(body) if kind == "md" else nbformat.v4.new_code_cell(body))

    for line in text.splitlines():
        if line.strip() in ("#%% md", "#%% code"):
            flush()
            kind, buf = line.strip()[4:], []
        else:
            buf.append(line)
    flush()
    return cells


def build(name: str) -> bool:
    nb = nbformat.v4.new_notebook()
    nb.metadata["kernelspec"] = {"name": "ql-study", "display_name": "QuantLib 1.44 (study)", "language": "python"}
    nb.cells = cells_from((SRC / f"{name}.py").read_text(encoding="utf-8"))
    path = NB_DIR / f"{name}.ipynb"
    nbformat.write(nb, str(path))
    done = execute(path, allow_errors=True)
    errs, fails = errors(done), failed_checks(done)
    for i, _, en, ev in errs:
        print(f"   - 셀 {i} 오류: {en}: {ev}")
    for f in fails:
        print(f"   - 검증 실패: {f}")
    ok = not errs and not fails
    print(f"{name}: {'통과' if ok else '문제 있음'} (셀 {len(done.cells)}개)")
    return ok


def main() -> None:
    names = [p.stem for p in sorted(SRC.glob("*.py"))] if sys.argv[1:] == ["--all"] else sys.argv[1:]
    results = [build(n) for n in names]
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
