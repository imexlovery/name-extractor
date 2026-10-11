"""Prepare title-only pilot inputs and persist reproducible local experiment records."""

import argparse
from collections import Counter
import json
from pathlib import Path
import random
import re
import math
import shutil
import time
import copy
import tempfile
from unittest.mock import patch

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
SEED = 20261010
PILOT = ROOT / ".local" / "pilot-20261010"


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path, values):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(v, ensure_ascii=False) + "\n" for v in values), encoding="utf-8")


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def regression_rows(histories, current, labels):
    """Track every historically matching row, including length and output state."""
    from validate import check, reference_length
    good = set()
    for history in histories:
        for row, result in history.items():
            label = labels.get(row)
            if label and label['status'] != 'uncertain' and result['status'] == label['status']:
                expected = ('；'.join(label['names']), reference_length(label['names']))
                if (result.get('extracted_name'), result.get('length')) == expected and result['names'] == label['names']:
                    good.add(row)
    return sorted(row for row in good if row not in current or
                  current[row]['names'] != labels[row]['names'] or
                  current[row]['status'] != labels[row]['status'] or
                  current[row].get('length') != reference_length(labels[row]['names']) or
                  current[row].get('extracted_name') != '；'.join(labels[row]['names']) or
                  current[row].get('checks', {}).get('failures'))


def stratum(title):
    if re.search(r"[A-Za-z]", title):
        return "英文或中英并列"
    if re.search(r"[·•‧・]", title):
        return "姓名中点线索"
    if re.search(r"等(?:[0-9一二三四五六七八九十百]+)?人", title):
        return "等人省略线索"
    if re.search(r"[、;；]", title):
        return "多人分隔线索"
    if re.search(r"[()（）]", title):
        return "其他括号"
    if "关于核准" in title:
        return "核准结构"
    if "关于" in title and "任职资格" in title:
        return "关于结构"
    return "其他结构"


def prepare(size):
    started = time.perf_counter()
    workbook = load_workbook(ROOT / "任职资格批复汇总测试.xlsx", read_only=True, data_only=True)
    sheet = workbook["Sheet1"]
    headers = [c.value for c in next(sheet.iter_rows(min_row=1, max_row=1, max_col=13))]
    assert headers[0] == "标题" and len(headers) == 13
    titles = {}
    # Actual occupied boundary was independently inspected; max_row is the Excel grid limit.
    for row, (cell,) in enumerate(sheet.iter_rows(min_row=2, max_row=52147, min_col=1, max_col=1), 2):
        assert isinstance(cell.value, str) and cell.value
        titles.setdefault(cell.value, []).append(row)
    workbook.close()
    records = [{"row": rows[0], "title": title, "rows": rows, "stratum": stratum(title)}
               for title, rows in titles.items()]
    rng = random.Random(SEED)
    selected = {}
    mandatory = {2, 50, 133, 1471, 6995, 10391}
    for record in records:
        if mandatory.intersection(record["rows"]):
            selected[record["title"]] = record
    quotas = {"英文或中英并列": 24, "姓名中点线索": 12, "等人省略线索": 16,
              "多人分隔线索": 24, "其他括号": 12, "核准结构": 24,
              "关于结构": 24, "其他结构": 24}
    for group, quota in quotas.items():
        pool = [r for r in records if r["stratum"] == group and r["title"] not in selected]
        for record in rng.sample(pool, min(quota, len(pool), size - len(selected))):
            selected[record["title"]] = record
    if len(selected) < size:
        pool = [r for r in records if r["title"] not in selected]
        for record in rng.sample(pool, min(size - len(selected), len(pool))):
            selected[record["title"]] = record
    sample = sorted(selected.values(), key=lambda r: r["row"])
    write_jsonl(PILOT / "inventory.jsonl", records)
    write_jsonl(PILOT / "sample.jsonl", sample)
    # Blind annotation inputs intentionally omit script outputs, pattern classes and risk flags.
    blind = [{"row": r["row"], "title": r["title"]} for r in sample]
    write_jsonl(PILOT / "blind-a.jsonl", blind)
    for offset in range(0, len(blind), 40):
        write_jsonl(PILOT / f"blind-a-{offset // 40 + 1:02d}.jsonl", blind[offset:offset + 40])
    manifest = {"seed": SEED, "source": "任职资格批复汇总测试.xlsx", "sheet": "Sheet1",
                "source_rows": sum(len(r["rows"]) for r in records), "unique_titles": len(records),
                "sample_unique_titles": len(sample), "mapped_original_rows": sum(len(r["rows"]) for r in sample),
                "strata": dict(Counter(r["stratum"] for r in sample)),
                "read_seconds": round(time.perf_counter() - started, 3),
                "business_contract": "2026-10-10 Q1-Q8", "human_review_performed": False}
    write_json(PILOT / "manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


def run():
    from extract import VERSION, extract, name_length
    from validate import check
    started = time.perf_counter()
    output = []
    for item in read_jsonl(PILOT / "sample.jsonl"):
        result = extract(item["title"])
        result.update(row=item["row"], extracted_name="；".join(result["names"]),
                      length=sum(name_length(name) for name in result["names"]))
        result["checks"] = check(item["title"], result)
        output.append(result)
    write_jsonl(PILOT / f"script-{VERSION}.jsonl", output)
    shutil.copyfile(ROOT / "scripts" / "extract.py", PILOT / f"extract-{VERSION}.py")
    write_json(PILOT / f"run-{VERSION}.json", {"version": VERSION, "titles": len(output),
               "extract_and_check_seconds": round(time.perf_counter() - started, 6)})
    print(json.dumps({"version": VERSION, "titles": len(output),
                      "statuses": dict(Counter(x["status"] for x in output))}, ensure_ascii=False))


def load_a():
    from validate import check
    values = []
    for i in range(1, 5):
        values.extend(read_jsonl(PILOT / f"ai-a-{i:02d}.jsonl"))
    samples = {x["row"]: x for x in read_jsonl(PILOT / "sample.jsonl")}
    assert len(values) == len(samples) and len({x["row"] for x in values}) == len(values)
    assert {x["row"] for x in values} == samples.keys()
    for value in values:
        failures = check(samples[value["row"]]["title"], value)["failures"]
        assert not failures, (value["row"], failures)
    return {x["row"]: x for x in values}


def compare(version, select_review):
    from validate import reference_length
    samples = {x["row"]: x for x in read_jsonl(PILOT / "sample.jsonl")}
    output = {x["row"]: x for x in read_jsonl(PILOT / f"script-{version}.jsonl")}
    assert output.keys() == samples.keys()
    labels = load_a()
    diffs, ordinary, selected = [], {}, {}
    for row, item in samples.items():
        result, label = output[row], labels[row]
        mismatch = result["names"] != label["names"] or result["length"] != reference_length(label["names"])
        if mismatch:
            diffs.append({"row": row, "title": item["title"], "script": result,
                          "ai_a": label, "stratum": item["stratum"]})
        reasons = list(result["checks"]["flags"]) + list(result["checks"]["failures"])
        if mismatch: reasons.append("脚本与AI A分歧")
        if label["status"] == "uncertain": reasons.append("AI A不确定")
        if reasons:
            selected[row] = {"row": row, "reasons": sorted(set(reasons))}
        else:
            ordinary.setdefault(item["stratum"], []).append(row)
    write_jsonl(PILOT / f"differences-{version}.jsonl", diffs)
    if select_review:
        rng = random.Random(SEED)
        total = sum(map(len, ordinary.values()))
        target = math.ceil(total * 0.05)
        groups = sorted(ordinary)
        allocations = {g: int(target * len(ordinary[g]) / total) if total else 0 for g in groups}
        if target >= len(groups):
            allocations = {g: max(1, n) for g, n in allocations.items()}
        while sum(allocations.values()) < target:
            g = max(groups, key=lambda g: target * len(ordinary[g]) / total - allocations[g])
            allocations[g] += 1
        while sum(allocations.values()) > target:
            g = max(groups, key=lambda g: allocations[g] - target * len(ordinary[g]) / total)
            allocations[g] -= 1
        sampled = []
        for group in groups:
            for row in rng.sample(sorted(ordinary[group]), allocations[group]):
                selected[row] = {"row": row, "reasons": ["普通一致标题分层随机5%"]}
                sampled.append(row)
        selections = [selected[row] for row in sorted(selected)]
        write_jsonl(PILOT / "review-selection.jsonl", selections)
        write_jsonl(PILOT / "blind-b.jsonl", [{"row": row, "title": samples[row]["title"]} for row in sorted(selected)])
        write_json(PILOT / "review-sampling.json", {"seed": SEED, "ordinary_population": total,
                   "requested_rate": 0.05, "sampled_count": len(sampled), "sampled_rows": sorted(sampled),
                   "stratum_population": {g: len(v) for g, v in ordinary.items()}, "stratum_sample": allocations,
                   "selected_total": len(selected), "selection_script_version": version})
    summary = {"version": version, "titles": len(samples), "ai_a_covered": len(labels),
               "script_ai_a_difference_count": len(diffs), "script_ai_a_match_count": len(samples) - len(diffs),
               "deterministic_failure_rows": sum(bool(v["checks"]["failures"]) for v in output.values()),
               "script_uncertain": sum(v["status"] == "uncertain" for v in output.values()),
               "ai_a_uncertain": sum(v["status"] == "uncertain" for v in labels.values())}
    write_json(PILOT / f"comparison-{version}.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def finish():
    from extract import VERSION, extract, name_length
    from validate import check, reference_length
    sample = read_jsonl(PILOT / "sample.jsonl")
    holdout = read_jsonl(PILOT / "holdout.jsonl")
    samples = {r["row"]: r for r in sample + holdout}
    labels = load_a()
    labels.update({r["row"]: r for r in read_jsonl(PILOT / "holdout-ai-a.jsonl")})
    reviews = [r for i in range(1, 4) for r in read_jsonl(PILOT / f"ai-b-{i:02d}.jsonl")]
    reviews += read_jsonl(PILOT / "holdout-ai-b.jsonl")
    expected_b = {r["row"] for r in read_jsonl(PILOT / "blind-b.jsonl") + read_jsonl(PILOT / "holdout-blind-b.jsonl")}
    assert len({r["row"] for r in reviews}) == len(reviews)
    assert {r["row"] for r in reviews} == expected_b
    by_b = {r["row"]: r for r in reviews}
    assert labels.keys() == samples.keys()
    for result in list(labels.values()) + reviews:
        assert not check(samples[result["row"]]["title"], result)["failures"]
    output, audit = [], []
    started = time.perf_counter()
    for row, item in samples.items():
        result = extract(item["title"])
        result.update(row=row, length=sum(name_length(n) for n in result["names"]),
                      extracted_name="；".join(result["names"]))
        result["checks"] = check(item["title"], result)
        output.append(result)
        a, b = labels[row], by_b.get(row)
        differs = result["names"] != a["names"] or result["length"] != reference_length(a["names"])
        if result['checks']['failures'] or a["status"] == "uncertain" or (b and (b["status"] == "uncertain" or b["names"] != a["names"] or b['status'] != a['status'])):
            state, source, candidate = "unresolved_semantic", "ai_candidate", a["names"]
        elif result["status"] == "uncertain" or differs:
            state, source, candidate = "needs_ai_route", "ai_supported_candidate" if b else "ai_a_candidate", a["names"]
        else:
            state, source, candidate = "script_ai_consistent", "script", result["names"]
        audit.append({"row": row, "title": item["title"], "mapped_rows": item["rows"],
                      "sample_group": "development" if row in {r["row"] for r in sample} else "new_titles",
                      "script": result, "ai_a": a, "ai_b": b, "state": state,
                      "candidate_source": source,
                      "candidate_output": {"提取姓名": "；".join(candidate), "姓名字数": reference_length(candidate)},
                      "verified_against_independent_truth": False})
    local_seconds = time.perf_counter() - started
    write_jsonl(PILOT / f"combined-script-{VERSION}.jsonl", output)
    write_jsonl(PILOT / "audit.jsonl", audit)
    write_jsonl(PILOT / "unresolved.jsonl", [r for r in audit if r["state"] != "script_ai_consistent"])
    current = {r["row"]: r for r in output}
    histories = [{r['row']: r for r in read_jsonl(path)} for path in sorted(PILOT.glob('script-r*.jsonl'))]
    regressions = regression_rows(histories, current, labels)
    # Reconstruct all results from disk in a separate fresh calculation; no model calls.
    restored = read_jsonl(PILOT / "audit.jsonl")
    persistence_ok = len(restored) == len(audit) and all(
        extract(r["title"])["names"] == r["script"]["names"] and extract(r["title"])["status"] == r["script"]["status"]
        for r in restored)
    fault_length = copy.deepcopy(current[2]); fault_length["length"] += 1
    length_detected = "字数不符" in check(samples[2]["title"], fault_length)["failures"]
    multi_row = next(row for row, label in labels.items() if len(label["names"]) > 1)
    fault_omission = copy.deepcopy(current[multi_row]); fault_omission["names"] = labels[multi_row]["names"][:-1]
    omission_detected = fault_omission["names"] != labels[multi_row]["names"]
    # Actually run the cached-reference loader against a copy with a missing annotation.
    missing_detected = False
    with tempfile.TemporaryDirectory(prefix="pilot-missing-label-") as directory:
        temporary = Path(directory)
        shutil.copyfile(PILOT / "sample.jsonl", temporary / "sample.jsonl")
        for i in range(1, 5):
            rows = read_jsonl(PILOT / f"ai-a-{i:02d}.jsonl")
            write_jsonl(temporary / f"ai-a-{i:02d}.jsonl", rows[1:] if i == 1 else rows)
        with patch.dict(globals(), {"PILOT": temporary}):
            try: load_a()
            except AssertionError: missing_detected = True
    controls = {"wrong_length_detected": length_detected, "omitted_person_detected_by_reference": omission_detected,
                "missing_annotation_rejected": missing_detected, "persist_reload_reproduces_results": persistence_ok}
    assert all(controls.values()), controls
    development = [r for r in audit if r["sample_group"] == "development"]
    new_titles = [r for r in audit if r["sample_group"] == "new_titles"]
    states = dict(Counter(r["state"] for r in audit))
    summary = {"script_version": VERSION, "unique_titles": len(audit),
               "mapped_original_rows": sum(len(r["mapped_rows"]) for r in audit),
               "development_titles": len(development), "development_values_match_ai_a": sum(r["script"]["names"] == r["ai_a"]["names"] for r in development),
               "new_titles": len(new_titles), "new_title_values_match_ai_a": sum(r["script"]["names"] == r["ai_a"]["names"] for r in new_titles),
               "ai_a_coverage": len(labels), "ai_b_coverage": len(by_b),
               "ai_a_b_candidate_matches": sum(labels[row]["names"] == b["names"] for row, b in by_b.items()),
               "ai_b_uncertain": sum(b["status"] == "uncertain" for b in by_b.values()),
               "ai_a_b_definitive_matches": sum(labels[row]["names"] == b["names"] and b["status"] != "uncertain" and labels[row]["status"] != "uncertain" for row, b in by_b.items()),
               "deterministic_failure_rows": sum(bool(r["script"]["checks"]["failures"]) for r in audit),
               "script_uncertain_rows": sum(r["script"]["status"] == "uncertain" for r in audit),
               "states": states, "new_regression_rows": regressions, "controls": controls,
               "combined_local_seconds": round(local_seconds, 6), "human_review_performed": False,
               "true_accuracy": None, "real_rule_modification_rounds": 2,
               "r02_unseen_result": json.loads((PILOT / "holdout-summary.json").read_text()),
               "coverage_limit": "200标题为分层实验样本；40个新标题在r02时未用于修订，发现问题后用于r03诊断，不能再作为r03未见测试集。"}
    summary["word_summary"] = [
        f"实验覆盖{len(audit)}个不同标题，映射原表{summary['mapped_original_rows']}行。AI A标注{len(labels)}个标题，AI B复核{len(by_b)}个；均使用当前Codex同一模型的独立任务上下文。",
        "r01与AI A在150/160条上值一致。r02补充10个实际机构起点词后原160条值一致，但另40条新标题仅29条一致，不能据原样本一致宣称泛化。",
        f"r03修复财务负责人、主要负责人和营业部主任的残片误提，原160条无新增回归；新40条有{summary['new_title_values_match_ai_a']}条值一致，脚本仍有{summary['script_uncertain_rows']}条未确定结果。",
        f"AI A与B候选值在{summary['ai_a_b_candidate_matches']}/{len(by_b)}条上一致，其中{summary['ai_b_uncertain']}条仍有逗号语义歧义，不能计为已确认正确。内部记录保留AI支持候选和未决状态。",
        "结果持久化后重新加载可复现。故障注入实际检出了错误字数、漏掉一人和缺失AI标注；注入不计入真实错误。仅完成两轮真实规则修订，原要求的至少十轮以上修改尚未完成。",
        "后续采用全量本地规则与结构检查，机构和职务等复杂结构重点AI复核，并对普通结构保留分层随机检查。实际AI覆盖单独报告，不把模板检查冒充逐条AI标注。全量真实准确率尚未评估，尚未导出最终Excel。"
    ]
    write_json(PILOT / "summary.json", summary)
    print(json.dumps({k: v for k, v in summary.items() if k != "word_summary"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["prepare", "run", "compare", "finish"])
    parser.add_argument("--size", type=int, default=160)
    parser.add_argument("--version", default="r01")
    parser.add_argument("--select-review", action="store_true")
    args = parser.parse_args()
    if args.action == "prepare": prepare(args.size)
    elif args.action == "run": run()
    elif args.action == "compare": compare(args.version, args.select_review)
    else: finish()
