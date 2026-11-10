"""셀 목록을 Jupyter 커널("QuantLib 1.44 (study)")에서 순서대로 실행하고 출력을 그대로 기록한다.

- 책이 IPython 노트북이었으므로, 원본도 같은 종류의 실행 환경(Jupyter 커널)에서 돌린다.
- 오류가 나도 다음 셀로 계속 진행한다.
- 표준출력, 표준오류(경고 포함), 마지막 식의 값(execute_result), 그림 여부, 오류 원문을 남긴다.
- 경고가 한 번만 보이고 숨지 않도록 첫 셀 전에 warnings.simplefilter("always")를 실행한다.
  이 설정 셀은 기록에서 n=0 으로 표시한다(코드 변경이 아니라 실행 환경 설정).

사용법(모듈): run(cells, workdir, timeout) -> list[dict]
사용법(명령): python tools/run_cells.py <입력.json> <출력.json> [작업폴더]
  입력.json 은 [{"n": 1, "code": "..."}...] 또는 extract.py 의 cells.json
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import nbformat
from nbclient import NotebookClient

KERNEL = "ql-study"
ANSI = re.compile(r"\x1b\[[0-9;]*m")
SETUP = "import warnings\nwarnings.simplefilter('always')"


def _clean(s: str) -> str:
    return ANSI.sub("", s)


def _ts(meta: dict, key: str):
    v = meta.get("execution", {}).get(key)
    return datetime.fromisoformat(v.replace("Z", "+00:00")) if v else None


def run(cells: list[dict], workdir: Path, timeout: int = 600, setup: bool = True,
        paths: list[str] | None = None) -> list[dict]:
    """paths: 셀 실행 전에 sys.path 앞에 넣을 폴더 (예: 자체 구현 utils.py 가 있는 notebooks/)."""
    nb = nbformat.v4.new_notebook()
    if setup:
        extra = "".join(f"\nimport sys; sys.path.insert(0, {str(x)!r})" for x in (paths or []))
        nb.cells.append(nbformat.v4.new_code_cell(SETUP + extra))
    for c in cells:
        nb.cells.append(nbformat.v4.new_code_cell(c["code"]))
    client = NotebookClient(
        nb,
        kernel_name=KERNEL,
        timeout=timeout,
        allow_errors=True,
        record_timing=True,
        resources={"metadata": {"path": str(workdir)}},
    )
    t0 = time.time()
    client.execute()
    results = []
    body = nb.cells[1:] if setup else nb.cells
    for c, cell in zip(cells, body):
        rec = {"n": c["n"], "code": c["code"], "stdout": "", "stderr": "", "result": "",
               "images": 0, "error": None, "status": "ok"}
        for o in cell.get("outputs", []):
            if o.output_type == "stream":
                rec[o.name] += _clean(o.text)
            elif o.output_type == "execute_result":
                rec["result"] = _clean(o.data.get("text/plain", ""))
                if "image/png" in o.data:
                    rec["images"] += 1
            elif o.output_type == "display_data":
                if "image/png" in o.data:
                    rec["images"] += 1
                elif "text/plain" in o.data:
                    rec["stdout"] += _clean(o.data["text/plain"]) + "\n"
            elif o.output_type == "error":
                rec["status"] = "error"
                rec["error"] = {
                    "ename": o.ename,
                    "evalue": _clean(o.evalue),
                    "traceback": _clean("\n".join(o.traceback)),
                }
        a, b = _ts(cell.metadata, "iopub.execute_input"), _ts(cell.metadata, "shell.execute_reply")
        rec["elapsed_s"] = round((b - a).total_seconds(), 3) if a and b else None
        results.append(rec)
    results.append({"_total_elapsed_s": round(time.time() - t0, 2)})
    return results


def output_text(rec: dict) -> str:
    """책의 Out[n] 칸과 비교할 글자: 표준출력 + 마지막 식의 값."""
    parts = [rec.get("stdout", "").rstrip("\n")]
    if rec.get("result"):
        parts.append(rec["result"])
    return "\n".join(p for p in parts if p)


def to_markdown(results: list[dict]) -> str:
    out = []
    for r in results:
        if "n" not in r:
            continue
        out.append(f"### In [{r['n']}]  ({r['status']}, {r.get('elapsed_s')}s)")
        txt = output_text(r)
        if txt:
            out.append("```\n" + txt + "\n```")
        if r["stderr"]:
            out.append("stderr:\n```\n" + r["stderr"].rstrip() + "\n```")
        if r["error"]:
            out.append("오류:\n```\n" + r["error"]["traceback"].rstrip() + "\n```")
        if r["images"]:
            out.append(f"(그림 {r['images']}개)")
    return "\n\n".join(out) + "\n"


def main() -> None:
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    workdir = Path(sys.argv[3]) if len(sys.argv) > 3 else src.parent
    data = json.loads(src.read_text(encoding="utf-8"))
    cells = data["cells"] if isinstance(data, dict) else data
    res = run([{"n": c["n"], "code": c["code"]} for c in cells], workdir)
    dst.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    dst.with_suffix(".md").write_text(to_markdown(res), encoding="utf-8")
    errs = [r["n"] for r in res if r.get("status") == "error"]
    print(f"실행 {len(res) - 1}셀, 오류 셀 {errs}, 전체 {res[-1]['_total_elapsed_s']}s")


if __name__ == "__main__":
    main()
