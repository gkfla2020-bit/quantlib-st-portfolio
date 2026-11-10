"""노트북을 처음부터 끝까지 실제로 실행해 결과를 담아 저장하고 점검한다.

- 완성본: 오류 출력이 하나도 없어야 한다. 검증 표에 '실패'가 있으면 안 된다.
- 학습본: 원본 셀(role=orig)의 오류가 D 변환 실행 기록(work/chNN/run/d.json)과 같아야 한다.
- 완성본 버전 1 셀의 출력은 work/chNN/run/v1.json 과 같아야 한다(실행마다 다른 셀은 제외).

사용법: python tools/verify_notebooks.py <장번호> | --all
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import nbformat
from nbclient import NotebookClient

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_cells  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
NB_DIR = ROOT / "notebooks"


def execute(path: Path, allow_errors: bool, timeout: int = 1200):
    nb = nbformat.read(str(path), as_version=4)
    client = NotebookClient(nb, kernel_name="ql-study", timeout=timeout, allow_errors=allow_errors,
                            resources={"metadata": {"path": str(NB_DIR)}})
    client.execute()
    nbformat.write(nb, str(path))
    return nb


def cell_result(cell) -> dict:
    rec = {"stdout": "", "stderr": "", "result": "", "error": None}
    for o in cell.get("outputs", []):
        if o.output_type == "stream":
            rec[o.name] += run_cells._clean(o.text)
        elif o.output_type == "execute_result":
            rec["result"] = run_cells._clean(o.data.get("text/plain", ""))
        elif o.output_type == "display_data" and "text/plain" in o.data and "image/png" not in o.data:
            rec["stdout"] += run_cells._clean(o.data["text/plain"]) + "\n"
        elif o.output_type == "error":
            rec["error"] = {"ename": o.ename, "evalue": run_cells._clean(o.evalue)}
    return rec


def errors(nb) -> list[tuple]:
    out = []
    for i, c in enumerate(nb.cells):
        if c.cell_type != "code":
            continue
        for o in c.get("outputs", []):
            if o.output_type == "error":
                out.append((i, c.metadata.get("ql", {}), o.ename, run_cells._clean(o.evalue).split("\n")[0]))
    return out


def failed_checks(nb) -> list[str]:
    out = []
    for c in nb.cells:
        if c.cell_type != "code":
            continue
        for o in c.get("outputs", []):
            txt = o.get("data", {}).get("text/markdown", "") if o.output_type == "display_data" else ""
            if "**실패**" in txt:
                out.append(txt.split("\n")[0])
    return out


def verify(ch: int, nondeterministic=()) -> dict:
    import specs as S
    spec = S.load(ch)
    from make_notebooks import nb_paths
    lp, cp = nb_paths(spec)
    run_dir = ROOT / "work" / f"ch{ch:02d}" / "run"
    report = {"chapter": ch, "problems": []}

    lnb = execute(lp, allow_errors=True)
    d_res = {r["n"]: r for r in json.loads((run_dir / "d.json").read_text()) if "n" in r}
    for c in lnb.cells:
        meta = c.get("metadata", {}).get("ql", {})
        if c.cell_type == "code" and meta.get("role") == "orig":
            got = cell_result(c)["error"]
            want = d_res[meta["n"]]["error"]
            g = got and got["ename"]
            w = want and want["ename"]
            if g != w:
                report["problems"].append(f"학습본 In [{meta['n']}] 오류가 기록과 다름: 노트북 {g}, 기록 {w}")
    report["learning_errors"] = len(errors(lnb))

    cnb = execute(cp, allow_errors=True)
    errs = errors(cnb)
    for i, meta, en, ev in errs:
        report["problems"].append(f"완성본 셀 {i} ({meta}) 오류: {en}: {ev}")
    for f in failed_checks(cnb):
        report["problems"].append(f"완성본 검증 실패 항목: {f}")
    v1 = {r["n"]: r for r in json.loads((run_dir / "v1.json").read_text()) if "n" in r}
    for c in cnb.cells:
        meta = c.get("metadata", {}).get("ql", {})
        if c.cell_type == "code" and meta.get("role") == "v1" and meta["n"] not in nondeterministic:
            got = run_cells.output_text(cell_result(c))
            want = run_cells.output_text(v1[meta["n"]])
            if got != want:
                report["problems"].append(f"완성본 In [{meta['n']}] 출력이 v1 실행 기록과 다름")
    report["complete_errors"] = len(errs)
    report["ok"] = not report["problems"]
    (run_dir / "verify.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return report


def main() -> None:
    import specs as S
    targets = range(1, 27) if sys.argv[1] == "--all" else [int(a) for a in sys.argv[1:]]
    for ch in targets:
        spec = S.load(ch)
        nd = [n for n, e in spec.get("EXCEPTIONS", {}).items() if e["reason"] in ("nondeterministic", "plot_only")]
        r = verify(ch, nd)
        print(f"{ch}장: {'통과' if r['ok'] else '문제 있음'} (완성본 오류 {r['complete_errors']}, 학습본 오류 {r['learning_errors']})")
        for p in r["problems"]:
            print("   -", p)


if __name__ == "__main__":
    main()
