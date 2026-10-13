"""Single, predeclared A2 character-context experiment; writes only beside this file."""

from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import re


HERE = Path(__file__).resolve().parent
A1 = HERE.parent
ROOT = HERE.parents[4]
INVENTORY = ROOT / ".local/pilot-20261010/inventory.jsonl"
HAN = r"[\u3400-\u9fff]"
PREFIX = r"(?:同意核准|不予核准|核准|批准|同意|核定|确认|注销)?"
# Lazy subject capture ensures an optional final 的 is consumed as the grammar linker.
SHORT_SUBJECT = re.compile(
    r"^关于" + PREFIX + r"(?P<subject>" + HAN + r"{2,4}?)(?P<linker>的)?任职资格的批复$"
)
# Same eligibility-only rejection vocabulary as A1. A surviving string is still weak material.
NON_PERSON = re.compile(
    r"银行|农行|农商行|农合行|分行|支行|公司|联社|信用|保险|金融|财务|董事|理事|监事|行长|经理|主任|高管|管理|"
    r"负责|总裁|秘书|代表|部门|营业|中心|机构|资格|核准|关于|审批|许可|"
    r"开业|设立|注销|终止|事项|申请|同志|先生|女士|^对|[等和及与]|[0-9０-９]"
)
FEATURE_NAMES = ("left", "right", "pair", "left_triple", "right_triple")


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def save_json(name, value):
    (HERE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def save_jsonl(name, values):
    path = HERE / name
    with path.open("w", encoding="utf-8") as stream:
        for value in values:
            stream.write(json.dumps(value, ensure_ascii=False) + "\n")


def parse_short_subject(title):
    match = SHORT_SUBJECT.fullmatch(title)
    if not match:
        return None
    subject = match.group("subject")
    if not re.fullmatch(HAN + r"{2,4}", subject):
        raise AssertionError("parser returned a non-Han or out-of-range subject")
    return subject


def load_a1():
    samples = read_jsonl(A1 / "sources.jsonl")
    groups = json.loads((A1 / "groups.json").read_text(encoding="utf-8"))
    frozen = json.loads((A1 / "frozen-parameters.json").read_text(encoding="utf-8"))
    summary = json.loads((A1 / "stage-a-summary.json").read_text(encoding="utf-8"))
    assert len(samples) == 430, f"A1 structure sample count changed: {len(samples)}"
    assert frozen.get("selected") is None, "A1 frozen result no longer has selected=null"
    assert summary.get("holdout_scored") is False, "A1 holdout was already scored or its record changed"
    group_map = {group["group_id"]: group for group in groups}
    assert len(group_map) == len(groups)
    for sample in samples:
        group = group_map[sample["group_id"]]
        assert sample["split"] == group["split"]
        assert sample["row"] in group["rows"]
        assert sample["text"] == "".join(sample["parts"])
    return samples, groups, frozen, summary


def load_target_masks():
    # Read only the A1 target_exclusions output, never its answer-bearing source records.
    exclusions = json.loads((A1 / "exclusions.json").read_text(encoding="utf-8"))
    targets = [{key: record[key] for key in ("row", "title", "whole_candidate")}
               for record in exclusions["targets"]]
    titles = {record["title"] for record in targets}
    rows = {record["row"] for record in targets}
    substrings = {
        candidate[start:end]
        for record in targets
        for candidate in (record["whole_candidate"],)
        for start in range(len(candidate))
        for end in range(start + 2, len(candidate) + 1)
    }
    # The A1 exclusion artifact is the predeclared mask; this check compares masks only.
    assert substrings == set(exclusions["possible_contiguous_target_spans"])
    return titles, rows, substrings, dict(
        target_records=len(targets), target_titles=len(titles), target_representative_rows=len(rows),
        candidate_substrings=len(substrings),
    )


def classify(case):
    if case["boundaries"]:
        return "multi"
    if len(case["text"]) >= 5:
        return "long_whole"
    if len(case["text"]) == 4:
        return "whole4"
    return "short_whole"


def scan_weak_sources(samples):
    target_titles, target_rows, target_substrings, mask_stats = load_target_masks()
    holdout_calibration_values = {
        value
        for case in samples
        if case["split"] in {"calibration", "holdout"}
        for value in [*case["parts"], case["text"]]
    }
    raw = []
    for line in INVENTORY.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        # This is the complete source-field whitelist for inventory access.
        raw.append({key: record[key] for key in ("row", "rows", "title")})

    accepted, excluded = [], []
    reason_counts = Counter()
    for record in raw:
        row_set = set(record["rows"])
        reasons = []
        is_target_title = record["title"] in target_titles
        is_target_row = bool(row_set & target_rows) or record["row"] in target_rows
        if is_target_title:
            reasons.append("a1_target_complete_title")
        if is_target_row:
            reasons.append("a1_target_repeated_rows")

        # Never parse or derive a subject from a title/row that is itself a target.
        subject = None
        if not (is_target_title or is_target_row):
            subject = parse_short_subject(record["title"])
            if subject is None:
                reasons.append("outside_exact_short_subject_grammar")
            else:
                if NON_PERSON.search(subject):
                    reasons.append("a1_non_person_or_residual_rule")
                if subject in target_substrings:
                    reasons.append("a1_target_candidate_substring")
                if subject in holdout_calibration_values:
                    reasons.append("a1_calibration_or_holdout_part_or_text")

        decision = dict(row=record["row"], rows=record["rows"],
                        status="excluded" if reasons else "accepted", exclusion_reasons=reasons)
        if not (is_target_title or is_target_row):
            decision["title"] = record["title"]
        if subject is not None and not (is_target_title or is_target_row):
            decision["candidate_subject"] = subject
        if reasons:
            excluded.append(decision)
            reason_counts.update(reasons)
        else:
            decision["subject"] = subject
            accepted.append(decision)

    save_jsonl("weak-sources.jsonl", accepted)
    save_jsonl("weak-exclusions.jsonl", excluded)
    return accepted, dict(
        inventory_records=len(raw), accepted_source_records=len(accepted),
        excluded_source_records=len(excluded), exclusion_reason_record_counts=dict(reason_counts),
        unique_weak_subjects=len({record["subject"] for record in accepted}),
        weak_source_rows=sum(len(record["rows"]) for record in accepted),
        source_field_whitelist=["row", "rows", "title"], target_exclusion_mask=mask_stats,
    )


def build_fit_atoms(samples, weak_sources):
    origins = defaultdict(lambda: {"weak_source_rows": set(), "a1_fit_rows": set()})
    for record in weak_sources:
        origins[record["subject"]]["weak_source_rows"].update(record["rows"])
    for case in samples:
        if case["split"] == "fit":
            for part in case["parts"]:
                origins[part]["a1_fit_rows"].update(case["rows"])
    atoms = []
    for atom in sorted(origins):
        sources = origins[atom]
        atoms.append(dict(
            atom=atom,
            source_kinds=(["weak_short_subject"] if sources["weak_source_rows"] else []) +
                         (["a1_fit_part"] if sources["a1_fit_rows"] else []),
            weak_source_rows=sorted(sources["weak_source_rows"]),
            a1_fit_rows=sorted(sources["a1_fit_rows"]),
        ))
    save_jsonl("fit-atoms.jsonl", atoms)
    return atoms


def unique_fit_rosters(samples):
    unique = {}
    for case in samples:
        if case["split"] != "fit" or case["source_kind"] != "marked_roster":
            continue
        key = (case["text"], tuple(case["boundaries"]))
        if key not in unique:
            unique[key] = dict(text=case["text"], parts=case["parts"],
                               boundaries=case["boundaries"], rows=set())
        unique[key]["rows"].update(case["rows"])
    rosters = []
    for key in sorted(unique):
        record = unique[key]
        assert record["text"] == "".join(record["parts"])
        expected = []
        cursor = 0
        for part in record["parts"][:-1]:
            cursor += len(part)
            expected.append(cursor)
        assert record["boundaries"] == expected
        rosters.append(dict(text=record["text"], parts=record["parts"],
                            boundaries=record["boundaries"], rows=sorted(record["rows"])))
    save_jsonl("fit-boundary-expressions.jsonl", rosters)
    return rosters


def increment(counter, key):
    counter[key] += 1


def fit(atoms, rosters):
    counts = {name: {"boundary": Counter(), "inside": Counter()} for name in FEATURE_NAMES}
    starts, ends = Counter(), Counter()
    for record in atoms:
        text = record["atom"]
        starts[text[0]] += 1
        ends[text[-1]] += 1
        counts["right"]["boundary"][text[0]] += 1
        counts["left"]["boundary"][text[-1]] += 1
        counts["left"]["inside"].update(text[:-1])
        counts["right"]["inside"].update(text[1:])
        for index in range(len(text) - 1):
            increment(counts["pair"]["inside"], text[index:index + 2])
        for index in range(len(text) - 2):
            trigram = text[index:index + 3]
            increment(counts["left_triple"]["inside"], trigram)
            increment(counts["right_triple"]["inside"], trigram)

    boundary_events = Counter()
    for roster in rosters:
        parts = roster["parts"]
        for index, (left_part, right_part) in enumerate(zip(parts, parts[1:])):
            increment(counts["pair"]["boundary"], left_part[-1] + right_part[0])
            if len(left_part) >= 2:
                increment(counts["left_triple"]["boundary"], left_part[-2:] + right_part[0])
            if len(right_part) >= 2:
                increment(counts["right_triple"]["boundary"], left_part[-1] + right_part[:2])
            boundary_events["explicit_roster_boundaries"] += 1

    feature_counts = {
        name: {kind: dict(sorted(counter.items())) for kind, counter in classes.items()}
        for name, classes in counts.items()
    }
    model = dict(
        feature_counts=feature_counts,
        start_characters=dict(sorted(starts.items())),
        end_characters=dict(sorted(ends.items())),
        unique_fit_atoms=len(atoms), unique_fit_boundary_expressions=len(rosters),
        explicit_roster_boundary_events=boundary_events["explicit_roster_boundaries"],
        smoothing=1, equal_feature_weights=1,
        training_labels="A1 fit explicit list boundaries only; weak subjects supply positions and internal contexts only",
    )
    feature_summary = {
        name: {
            "boundary_events": sum(counts[name]["boundary"].values()),
            "inside_events": sum(counts[name]["inside"].values()),
            "boundary_vocabulary": len(counts[name]["boundary"]),
            "inside_vocabulary": len(counts[name]["inside"]),
        }
        for name in FEATURE_NAMES
    }
    return model, feature_summary


def features(text, index):
    result = [("left", text[index - 1]), ("right", text[index]),
              ("pair", text[index - 1:index + 1])]
    if index > 1:
        result.append(("left_triple", text[index - 2:index + 1]))
    if index + 1 < len(text):
        result.append(("right_triple", text[index - 1:index + 2]))
    return result


def gap_score(model, text, index):
    score = 0.0
    for feature, value in features(text, index):
        observed = model["feature_counts"][feature]
        vocabulary = set(observed["boundary"]) | set(observed["inside"])
        if value not in vocabulary:
            if feature in {"left", "right"}:
                return None
            continue
        size = len(vocabulary)
        positive = (observed["boundary"].get(value, 0) + 1) / (sum(observed["boundary"].values()) + size)
        negative = (observed["inside"].get(value, 0) + 1) / (sum(observed["inside"].values()) + size)
        score += math.log(positive / negative)
    return score


def decode(model, text, bias):
    if len(text) < 4:
        return dict(status="not_testable", reason="no_alternative_partition_with_two_character_minimum")
    gaps = {index: gap_score(model, text, index) for index in range(2, len(text) - 1)}
    if any(score is None for score in gaps.values()):
        return dict(status="abstain", reason="unseen_single_character_role")
    dynamic = {0: [(0.0, ())]}
    for end in range(2, len(text) + 1):
        choices = []
        for start in range(end - 1):
            for previous, cuts in dynamic.get(start, []):
                score = previous + (gaps[start] - bias if start else 0.0)
                choices.append((score, cuts + ((start,) if start else ())))
        dynamic[end] = sorted(choices, key=lambda choice: (-choice[0], choice[1]))[:2]
    first, second = dynamic[len(text)]
    if any(not model["end_characters"].get(text[index - 1]) or
           not model["start_characters"].get(text[index]) for index in first[1]):
        return dict(status="abstain", reason="chosen_boundary_lacks_start_or_end_support")
    return dict(status="scored", boundaries=list(first[1]), alternative=list(second[1]),
                score=first[0], margin=first[0] - second[0])


def calibrate(model, cases):
    if not any(classify(case) == "multi" for case in cases) or not any(
            classify(case) == "long_whole" for case in cases):
        return None, dict(reason="missing_multi_or_long_whole_calibration_material", candidates=[])
    scores = sorted({score for case in cases for index in range(2, len(case["text"]) - 1)
                     if (score := gap_score(model, case["text"], index)) is not None})
    if not scores:
        return None, dict(reason="no_supported_calibration_gaps", candidates=[])
    biases = sorted({0.0, scores[0] - 1, scores[-1] + 1} |
                    {(left + right) / 2 for left, right in zip(scores, scores[1:])})
    candidates = []
    best = None
    denominators = Counter(classify(case) for case in cases)
    for bias in biases:
        predictions = [(case, decode(model, case["text"], bias)) for case in cases]
        wrong = [prediction["margin"] for case, prediction in predictions
                 if prediction["status"] == "scored" and prediction["boundaries"] != case["boundaries"]]
        margin = max([0.0] + wrong)
        accepted = Counter(classify(case) for case, prediction in predictions
                           if prediction["status"] == "scored" and
                           prediction["margin"] > margin and prediction["boundaries"] == case["boundaries"])
        objective = min(accepted["multi"] / denominators["multi"],
                        accepted["long_whole"] / denominators["long_whole"])
        candidate = dict(bias=bias, margin_strictly_above=margin,
                         accepted_correct=dict(accepted), balanced_coverage=objective)
        candidates.append(candidate)
        if not accepted["multi"] or not accepted["long_whole"]:
            continue
        key = (objective, sum(accepted.values()), -abs(bias), -bias)
        if best is None or key > best[0]:
            best = (key, candidate)
    return (best[1] if best else None), dict(
        reason="selected" if best else "no_candidate_protects_long_whole_and_restores_multi",
        candidates=candidates,
    )


def coverage_summary(model, cases):
    counts = defaultdict(Counter)
    for case in cases:
        if len(case["text"]) < 4:
            status = "not_testable"
        elif any(gap_score(model, case["text"], index) is None
                 for index in range(2, len(case["text"]) - 1)):
            status = "unknown_gap"
        else:
            status = "covered"
        counts[classify(case)][status] += 1
    return {kind: dict(counter) for kind, counter in counts.items()}


def evaluate(model, cases, bias, margin):
    records, totals = [], Counter()
    by_class = defaultdict(Counter)
    for case in cases:
        prediction = decode(model, case["text"], bias)
        reliable = (prediction["status"] == "scored" and prediction["margin"] > margin and
                    prediction["margin"] > 0)
        correct = prediction.get("boundaries") == case["boundaries"] if reliable else None
        if correct is True:
            state = "reliable_correct"
        elif correct is False:
            state = "reliable_error"
        elif prediction["status"] != "scored":
            state = prediction["status"]
        else:
            state = "abstain_margin"
        totals[state] += 1
        by_class[classify(case)][state] += 1
        records.append(dict(row=case["row"], title=case["title"], source_kind=case["source_kind"],
                            group_id=case["group_id"], text=case["text"],
                            expected_boundaries=case["boundaries"], prediction=prediction,
                            evaluation=state))
    return dict(totals=dict(totals), by_class={kind: dict(counter) for kind, counter in by_class.items()},
                records=records)


def split_stats(samples, groups):
    result = {}
    for split in ("fit", "calibration", "holdout"):
        cases = [case for case in samples if case["split"] == split]
        result[split] = dict(
            titles=len(cases), groups=len({case["group_id"] for case in cases}),
            source_kinds=dict(Counter(case["source_kind"] for case in cases)),
            comparison_classes=dict(Counter(classify(case) for case in cases)),
        )
    result["group_manifest_entries"] = len(groups)
    return result


def write_report(summary):
    lines = [
        "# 字符语境实验 A2：阶段结果",
        "",
        "本报告记录 A2 的一次预先约定拟合与校准。A1 的 `selected=null` 和未评分 holdout90 状态继续保留；A2 是材料和起止位置特征来源修订，不覆盖 A1 失败。所有结果是结构代理或弱监督字符证据，不是真实原表准确率。",
        "",
        "## 弱字符材料与拟合计数",
        "",
        f"- inventory 唯一标题记录：{summary['weak_source']['inventory_records']}；合格来源记录：{summary['weak_source']['accepted_source_records']}；拒收记录：{summary['weak_source']['excluded_source_records']}。",
        f"- 合格裸主体去重后：{summary['weak_source']['unique_weak_subjects']}；弱来源覆盖原行：{summary['weak_source']['weak_source_rows']}。",
        f"- A1 结构样本：{summary['a1']['sample_titles']} 条/原分组组数 {summary['a1']['group_manifest_entries']}；fit/calibration/holdout 分组原样沿用。",
        f"- 去重后拟合片段：{summary['fit']['unique_atoms']}；唯一 A1 fit 原标点名单表达：{summary['fit']['unique_boundary_expressions']}；这些表达的显式边界数：{summary['fit']['explicit_roster_boundary_events']}。",
        "- 弱主体只提供起止位置和片段内部二/三字语境；只有 A1 fit 原标点名单提供边界跨隙 n-gram。",
        "",
        "## 校准与留出",
        "",
        f"- 校准候选数：{summary['calibration']['candidate_count']}；选择结果：`{json.dumps(summary['selected'], ensure_ascii=False)}`。",
        f"- 校准原因：`{summary['calibration']['reason']}`；覆盖摘要：`{json.dumps(summary['calibration']['coverage'], ensure_ascii=False)}`。",
    ]
    if summary["holdout_scored"]:
        lines.append(f"- holdout90 仅评分一次；汇总：`{json.dumps(summary['evaluations']['holdout'], ensure_ascii=False)}`。")
        lines.append(f"- 阶段停止状态：`{summary['outcome']}`。")
    else:
        lines.append("- `selected=null`，按协议停止；holdout90、39个目标、11008及额外四字风险题均未评分。")
        lines.append(f"- 阶段停止状态：`{summary['outcome']}`。")
    lines += [
        "",
        "## 限制",
        "",
        "短主体不是人工单人真值，不能用于校准或声称姓名准确率。A1 的结构样本来自原标点与语言形式代理，A2 的 holdout 结果即使通过，也只代表这组结构题。目标题候选仅参与事前防泄漏排除，没有生成预测或用于调参；进入目标 B 需要主 Agent 单独批准。",
        "",
    ]
    (HERE / "stage-a2-report.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    samples, groups, a1_frozen, a1_summary = load_a1()
    weak_sources, weak_summary = scan_weak_sources(samples)
    atoms = build_fit_atoms(samples, weak_sources)
    rosters = unique_fit_rosters(samples)
    partitions = {split: [case for case in samples if case["split"] == split]
                  for split in ("fit", "calibration", "holdout")}
    model, feature_summary = fit(atoms, rosters)
    save_json("aggregate-model.json", model)
    save_json("feature-counts.json", feature_summary)

    # Exactly one calibration search; no target or holdout title is passed to it.
    selected, search = calibrate(model, partitions["calibration"])
    save_json("calibration-search.json", search)
    coverage = coverage_summary(model, partitions["calibration"])
    save_json("calibration-coverage.json", coverage)

    frozen = dict(
        stage="A2", protocol="protocol-a2.md", code_entrypoint="experiment_a2.py",
        source_path=str(INVENTORY.relative_to(ROOT)), source_fields=["row", "rows", "title"],
        a1_sources="../sources.jsonl", a1_groups="../groups.json",
        a1_frozen_status=a1_frozen["status"], a1_selected=a1_frozen["selected"],
        a1_holdout_scored=a1_summary["holdout_scored"],
        status="frozen_for_holdout" if selected else "stopped_insufficient_calibration_evidence",
        selected=selected, target_predictions_computed=False, independent_human_labels=0,
        title_truth_claimed=False, weak_subjects_are_labels=False,
        minimum_piece_length=2, no_maximum_piece_length=True,
        no_surname_table=True, no_full_name_lookup=True,
        model_features=list(FEATURE_NAMES), equal_feature_weights=1, laplace_smoothing=1,
        weak_subjects_used_for="fit position and internal context only",
        boundary_ngram_sources="A1 fit marked_roster explicit punctuation boundaries only",
        coverage_rule="all feasible gaps have observed left and right single-character roles",
        boundary_support_rule="chosen cut left character observed at atom end and right character at atom start",
    )
    # Freeze before chosen-calibration and the one permitted holdout evaluation.
    save_json("frozen-parameters.json", frozen)

    evaluations = {}
    if selected:
        calibration = evaluate(model, partitions["calibration"],
                               selected["bias"], selected["margin_strictly_above"])
        save_jsonl("calibration-evaluation.jsonl", calibration.pop("records"))
        evaluations["calibration"] = calibration
        holdout = evaluate(model, partitions["holdout"],
                           selected["bias"], selected["margin_strictly_above"])
        save_jsonl("holdout90-evaluation.jsonl", holdout.pop("records"))
        evaluations["holdout"] = holdout
        if holdout["totals"].get("reliable_error", 0):
            outcome = "stopped_reliable_holdout_error"
        elif not holdout["by_class"].get("long_whole", {}).get("reliable_correct", 0):
            outcome = "stopped_no_reliable_long_whole_holdout_coverage"
        elif not holdout["by_class"].get("multi", {}).get("reliable_correct", 0):
            outcome = "stopped_no_reliable_multi_holdout_coverage"
        else:
            outcome = "awaiting_main_agent_review_before_B"
    else:
        outcome = "stopped_insufficient_calibration_evidence"

    summary = dict(
        stage="A2", outcome=outcome, weak_source=weak_summary,
        a1=dict(sample_titles=len(samples), sample_rows=sum(len(case["rows"]) for case in samples),
                group_manifest_entries=len(groups), split_stats=split_stats(samples, groups),
                selected=a1_frozen["selected"], holdout_scored=a1_summary["holdout_scored"]),
        fit=dict(unique_atoms=len(atoms), unique_boundary_expressions=len(rosters),
                 explicit_roster_boundary_events=model["explicit_roster_boundary_events"],
                 feature_counts=feature_summary),
        calibration=dict(candidate_count=len(search["candidates"]), reason=search["reason"],
                         coverage=coverage),
        selected=selected, evaluations=evaluations, holdout_scored=selected is not None,
        target_predictions_computed=False, production_changed=False,
        true_accuracy=None,
        limitation="Weak short subjects are positional context only; structural controls do not establish human name truth.",
    )
    save_json("a2-summary.json", summary)
    write_report(summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
