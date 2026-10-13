"""One predeclared, title-only character-boundary experiment. Stage A only."""
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import random
import re

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SEED = 20261013
HAN = r"[\u3400-\u9fff]"
DOT = "·•・‧∙⋅"
SEPARATOR = re.compile(r"[、；;，,]")
PREFIX = re.compile(r"^(?:同意核准|不予核准|核准|批准|同意|核定|确认|注销)")
SUFFIX = re.compile(r"(?P<body>.+?)(?:任职资格|拟任资格)(?:的)?批复")
ROLE = r"(?:高级管理人员|独立董事|独立理事|董事|理事|高管|副行长|行长|副主任|主任|副总经理|总经理)"
# Eligibility exclusions, never evidence that any remaining arbitrary string is a name.
NON_PERSON = re.compile(
    r"银行|农行|农商行|农合行|分行|支行|公司|联社|信用|保险|金融|财务|董事|理事|监事|行长|经理|主任|高管|管理|"
    r"负责|总裁|秘书|代表|部门|营业|中心|机构|资格|核准|关于|审批|许可|"
    r"开业|设立|注销|终止|事项|申请|同志|先生|女士|^对|[等和及与]|[0-9０-９]"
)
KINDS = ["marked_roster", "explicit_one", "honorific_whole", "bilingual_whole", "middle_dot_whole"]


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def save(name, value):
    (HERE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def save_lines(name, values):
    (HERE / name).write_text("".join(json.dumps(v, ensure_ascii=False) + "\n" for v in values))


def target_exclusions(raw):
    # Only whitelist these structural fields. Never consume historical_expected/new_context.
    audit = json.loads((HERE.parent / "long-subject-audit-02.json").read_text())
    targets = [{k: r[k] for k in ("row", "title", "whole_candidate")} for r in audit["records"]]
    for r in raw:
        if r["row"] in {13592, 51022}:
            m = re.fullmatch(r"关于(" + HAN + r"+)任职资格的批复", r["title"])
            targets.append(dict(row=r["row"], title=r["title"], whole_candidate=m[1]))
    substrings = {s[i:j] for t in targets for s in [t["whole_candidate"]]
                  for i in range(len(s)) for j in range(i + 2, len(s) + 1)}
    return targets, substrings


def parse_material(r):
    title = r["title"]
    if not title.startswith("关于"):
        return None, "outside_narrow_title_grammar"
    core = PREFIX.sub("", title[2:].strip(), count=1)
    matched = SUFFIX.fullmatch(core)
    if not matched:
        return None, "outside_narrow_title_grammar"
    body = matched["body"]
    if body.endswith("的"):
        return None, "unconsumed_linker"
    parts, original, evidence, kind = [], [], [], None
    if SEPARATOR.search(body):
        original = SEPARATOR.split(body)
        if all(re.fullmatch(HAN + r"{2,}", p) for p in original):
            parts = original[:]
            kind = "marked_roster"
            start = title.find(body)
            evidence = [dict(text=m[0], start=start + m.start(), end=start + m.end(),
                             role="explicit_roster_boundary") for m in SEPARATOR.finditer(body)]
    if not kind:
        patterns = [
            ("explicit_one", re.compile(r"(?P<person>" + HAN + r"{2,}?)(?P<mark>一人|1人|１人|一位同志|一名同志)(?:" + ROLE + r")?")),
            ("honorific_whole", re.compile(r"(?P<person>" + HAN + r"{2,}?)(?P<mark>同志|先生|女士)(?:" + ROLE + r")?")),
            ("bilingual_whole", re.compile(r"(?P<person>" + HAN + r"{2,})(?P<mark>[（(][A-Za-z][A-Za-z.,，'’ \-]*[）)])(?:" + ROLE + r")?")),
            ("middle_dot_whole", re.compile(r"(?P<person>" + HAN + r"+(?:[" + DOT + r"]" + HAN + r"+)+)(?P<mark>同志|先生|女士)?")),
        ]
        for candidate_kind, pattern in patterns:
            m = pattern.fullmatch(body)
            if not m:
                continue
            kind = candidate_kind
            original = [m["person"]]
            parts = [re.sub("[" + DOT + "]", "", m["person"])]
            start = title.find(body)
            if kind == "middle_dot_whole":
                evidence = [dict(text=d[0], start=start+d.start(), end=start+d.end(),
                                 role="within_name_marker_removed_for_control")
                            for d in re.finditer("[" + DOT + "]", m["person"])]
            else:
                evidence = [dict(text=m["mark"], start=start+m.start("mark"),
                                 end=start+m.end("mark"), role="whole_expression_marker")]
            break
    if not kind:
        return None, "no_accepted_marked_structure"
    if any(NON_PERSON.search(p) or not re.fullmatch(HAN + r"{2,}", p) for p in parts):
        return None, "institution_role_connector_or_residual_in_subject"
    boundaries, cursor = [], 0
    for p in parts[:-1]:
        cursor += len(p)
        boundaries.append(cursor)
    return dict(row=r["row"], rows=r["rows"], title=title, source_kind=kind,
                original_spans=original, parts=parts, text="".join(parts),
                boundaries=boundaries, marker_evidence=evidence,
                evidence_strength=("original_explicit_count" if kind == "explicit_one" else
                                   "original_list_punctuation" if kind == "marked_roster" else
                                   "linguistic_structure_control_not_independent_person_count_truth")), None


def group_split(material):
    parents = list(range(len(material)))
    def find(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i
    def union(a, b):
        parents[find(b)] = find(a)
    owners = {}
    for i, m in enumerate(material):
        for key in [("part", p) for p in m["parts"]] + [("expression", m["text"])]:
            if key in owners:
                union(i, owners[key])
            else:
                owners[key] = i
    groups = defaultdict(list)
    for i in range(len(material)):
        groups[find(i)].append(i)
    strata = defaultdict(list)
    for ids in groups.values():
        cases = [material[i] for i in ids]
        if any(not c["boundaries"] and len(c["text"]) >= 5 for c in cases):
            stratum = "long_whole"
        elif any(c["boundaries"] for c in cases):
            stratum = "multi"
        elif any(len(c["text"]) >= 4 for c in cases):
            stratum = "whole4"
        else:
            stratum = "short_whole"
        strata[stratum].append(ids)
    manifest = []
    rng = random.Random(SEED)
    for stratum in sorted(strata):
        groups = sorted(strata[stratum], key=lambda ids: min(material[i]["row"] for i in ids))
        rng.shuffle(groups)
        n = len(groups)
        a, b = int(n * .6), int(n * .8)
        for k, ids in enumerate(groups):
            split = "fit" if k < a else "calibration" if k < b else "holdout"
            group_id = "group-" + str(min(material[i]["row"] for i in ids))
            for i in ids:
                material[i].update(group_id=group_id, split=split)
            manifest.append(dict(group_id=group_id, split=split, stratum=stratum,
                                 rows=[material[i]["row"] for i in ids],
                                 parts=sorted({p for i in ids for p in material[i]["parts"]})))
    # These checks are about the split, not extraction accuracy.
    part_splits = defaultdict(set)
    expression_splits = defaultdict(set)
    for m in material:
        for p in m["parts"]:
            part_splits[p].add(m["split"])
        expression_splits[m["text"]].add(m["split"])
    assert all(len(s) == 1 for s in part_splits.values())
    assert all(len(s) == 1 for s in expression_splits.values())
    return manifest


def features(text, i):
    f = [("left", text[i-1]), ("right", text[i]), ("pair", text[i-1:i+1])]
    if i > 1:
        f.append(("left_triple", text[i-2:i+1]))
    if i + 1 < len(text):
        f.append(("right_triple", text[i-1:i+2]))
    return f


def fit(cases):
    counts = {k: {"boundary": Counter(), "inside": Counter()} for k in
              ("left", "right", "pair", "left_triple", "right_triple")}
    starts, ends, inside2, inside3 = Counter(), Counter(), Counter(), Counter()
    atoms = {p for c in cases for p in c["parts"]}
    for p in atoms:
        starts[p[0]] += 1
        ends[p[-1]] += 1
        inside2.update(p[i:i+2] for i in range(len(p)-1))
        inside3.update(p[i:i+3] for i in range(len(p)-2))
    seen = set()
    for c in cases:
        key = (c["text"], tuple(c["boundaries"]))
        if key in seen:
            continue
        seen.add(key)
        for i in range(1, len(c["text"])):
            cls = "boundary" if i in c["boundaries"] else "inside"
            for f, v in features(c["text"], i):
                counts[f][cls][v] += 1
    return dict(feature_counts=counts, start_characters=starts, end_characters=ends,
                within_expression_bigrams=inside2, within_expression_trigrams=inside3,
                distinct_fit_expressions=len(seen), distinct_fit_atoms=len(atoms),
                smoothing=1, weights="all_observed_features_equal_1")


def gap_score(model, text, i):
    score = 0.0
    for feature, value in features(text, i):
        counts = model["feature_counts"][feature]
        vocab = set(counts["boundary"]) | set(counts["inside"])
        if value not in vocab:
            if feature in {"left", "right"}:
                return None
            continue
        v = len(vocab)
        pos = (counts["boundary"].get(value, 0) + 1) / (sum(counts["boundary"].values()) + v)
        neg = (counts["inside"].get(value, 0) + 1) / (sum(counts["inside"].values()) + v)
        score += math.log(pos / neg)
    return score


def decode(model, text, bias):
    if len(text) < 4:
        return dict(status="not_testable", reason="no_alternative_partition_with_two_character_minimum")
    gaps = {i: gap_score(model, text, i) for i in range(2, len(text)-1)}
    if any(v is None for v in gaps.values()):
        return dict(status="abstain", reason="unseen_single_character_role")
    dp = {0: [(0.0, ())]}
    for end in range(2, len(text)+1):
        choices = []
        for start in range(end-1):
            for previous, cuts in dp.get(start, []):
                choices.append((previous + (gaps[start]-bias if start else 0.0),
                                cuts + ((start,) if start else ())))
        dp[end] = sorted(choices, key=lambda v: (-v[0], v[1]))[:2]
    first, second = dp[len(text)]
    if any(not model["end_characters"].get(text[i-1]) or
           not model["start_characters"].get(text[i]) for i in first[1]):
        return dict(status="abstain", reason="chosen_boundary_lacks_start_or_end_support")
    return dict(status="scored", boundaries=list(first[1]), alternative=list(second[1]),
                score=first[0], margin=first[0]-second[0])


def classify(c):
    return "multi" if c["boundaries"] else "long_whole" if len(c["text"]) >= 5 else "whole4" if len(c["text"]) == 4 else "short_whole"


def evaluate(model, cases, bias, margin):
    records, totals = [], Counter()
    by_class = defaultdict(Counter)
    for c in cases:
        pred = decode(model, c["text"], bias)
        reliable = pred["status"] == "scored" and pred["margin"] > margin and pred["margin"] > 0
        correct = pred.get("boundaries") == c["boundaries"] if reliable else None
        state = "reliable_correct" if correct is True else "reliable_error" if correct is False else pred["status"] if pred["status"] != "scored" else "abstain_margin"
        totals[state] += 1
        by_class[classify(c)][state] += 1
        records.append(dict(row=c["row"], title=c["title"], source_kind=c["source_kind"],
                            group_id=c["group_id"], text=c["text"], expected_boundaries=c["boundaries"],
                            prediction=pred, evaluation=state))
    return dict(totals=totals, by_class=dict(by_class), records=records)


def calibrate(model, cases):
    if not any(classify(c) == "multi" for c in cases) or not any(classify(c) == "long_whole" for c in cases):
        return None, dict(reason="missing_multi_or_long_whole_calibration_material", candidates=[])
    scores = sorted({s for c in cases for i in range(2, len(c["text"])-1)
                     if (s := gap_score(model, c["text"], i)) is not None})
    if not scores:
        return None, dict(reason="no_supported_calibration_gaps", candidates=[])
    biases = sorted({0.0, scores[0]-1, scores[-1]+1} | {(a+b)/2 for a,b in zip(scores,scores[1:])})
    candidates = []
    best = None
    denominators = Counter(classify(c) for c in cases)
    for bias in biases:
        predictions = [(c, decode(model, c["text"], bias)) for c in cases]
        wrong = [p["margin"] for c,p in predictions if p["status"] == "scored" and p["boundaries"] != c["boundaries"]]
        margin = max([0.0] + wrong)
        accepted = Counter(classify(c) for c,p in predictions if p["status"] == "scored" and
                           p["margin"] > margin and p["boundaries"] == c["boundaries"])
        objective = min(accepted["multi"]/denominators["multi"], accepted["long_whole"]/denominators["long_whole"])
        candidate = dict(bias=bias, margin_strictly_above=margin,
                         accepted_correct=dict(accepted), balanced_coverage=objective)
        candidates.append(candidate)
        if not accepted["multi"] or not accepted["long_whole"]:
            continue
        key = (objective, sum(accepted.values()), -abs(bias), -bias)
        if best is None or key > best[0]:
            best = (key, candidate)
    return (best[1] if best else None), dict(reason="selected" if best else "no_candidate_protects_long_whole_and_restores_multi", candidates=candidates)


def calibration_coverage(model, cases):
    """Explain a failed calibration without touching holdout or target scores."""
    counts, long_controls = defaultdict(Counter), []
    for c in cases:
        unknown = [i for i in range(2, len(c["text"])-1)
                   if gap_score(model, c["text"], i) is None]
        state = "not_testable" if len(c["text"]) < 4 else "unknown_gap" if unknown else "covered"
        counts[classify(c)][state] += 1
        if classify(c) == "long_whole":
            long_controls.append(dict(row=c["row"], title=c["title"], text=c["text"],
                                      source_kind=c["source_kind"], coverage=state,
                                      unknown_gap_positions=unknown))
    return dict(by_class=dict(counts), long_controls=long_controls)


def main():
    source = ROOT / ".local/pilot-20261010/inventory.jsonl"
    raw = [{k:r[k] for k in ("row", "rows", "title")} for r in read_jsonl(source)]
    targets, excluded_spans = target_exclusions(raw)
    target_titles = {t["title"] for t in targets}
    material, rejected, excluded = [], Counter(), []
    for r in raw:
        if r["title"] in target_titles:
            excluded.append(dict(row=r["row"], rows=r["rows"], title=r["title"], reason="target_title"))
            continue
        m, reason = parse_material(r)
        if not m:
            rejected[reason] += 1
            continue
        overlaps = [p for p in m["parts"] if p in excluded_spans]
        if overlaps:
            excluded.append(dict(row=r["row"], rows=r["rows"], title=r["title"],
                                 reason="possible_target_substring", matched_spans=overlaps))
        else:
            material.append(m)
    groups = group_split(material)
    save_lines("sources.jsonl", material)
    save("groups.json", groups)
    save("exclusions.json", dict(targets=targets, possible_contiguous_target_spans=sorted(excluded_spans), excluded_records=excluded))
    partitions = {split:[m for m in material if m["split"] == split] for split in ("fit","calibration","holdout")}
    model = fit(partitions["fit"])
    save("aggregate-model.json", model)
    selected, search = calibrate(model, partitions["calibration"])
    save("calibration-search.json", search)
    coverage = calibration_coverage(model, partitions["calibration"])
    save("calibration-coverage.json", coverage)
    frozen = dict(stage="A", model_family="one_predeclared_character_context_naive_bayes", seed=SEED,
                  source_path=str(source.relative_to(ROOT)), target_predictions_computed=False,
                  code_entrypoint="experiment.py", protocol="protocol.md",
                  status="frozen_for_holdout" if selected else "stopped_insufficient_calibration_evidence",
                  selected=selected, title_truth_claimed=False, minimum_piece_length=2,
                  no_maximum_piece_length=True, no_surname_table=True, no_full_name_lookup=True,
                  coverage_rule="all_feasible_gaps_have_seen_left_and_right_character_roles",
                  boundary_support_rule="chosen_cut_left_observed_at_end_and_right_observed_at_start",
                  model_features=["left", "right", "pair", "left_triple", "right_triple"],
                  equal_feature_weights=1, laplace_smoothing=1)
    # The holdout is first scored only after parameters are written.
    save("frozen-parameters.json", frozen)
    evaluations = {}
    if selected:
        for split in ("calibration", "holdout"):
            evaluated = evaluate(model, partitions[split], selected["bias"], selected["margin_strictly_above"])
            save_lines(split + "-predictions.jsonl", evaluated.pop("records"))
            evaluations[split] = evaluated
    split_stats = {split:dict(titles=len(cases), groups=len({c["group_id"] for c in cases}),
                             kinds=dict(Counter(c["source_kind"] for c in cases)),
                             comparison_classes=dict(Counter(classify(c) for c in cases)))
                   for split,cases in partitions.items()}
    if selected:
        holdout = evaluations["holdout"]
        if holdout["totals"].get("reliable_error",0):
            outcome = "stopped_reliable_holdout_error"
        elif not holdout["by_class"].get("long_whole",{}).get("reliable_correct",0):
            outcome = "stopped_no_reliable_long_whole_holdout_coverage"
        elif not holdout["by_class"].get("multi",{}).get("reliable_correct",0):
            outcome = "stopped_no_reliable_multi_holdout_coverage"
        else:
            outcome = "awaiting_main_agent_review_before_B"
    else:
        outcome = "stopped_insufficient_calibration_evidence"
    summary = dict(stage="A", outcome=outcome, input_titles=len(raw), input_rows=sum(len(r["rows"]) for r in raw),
                   source_material_titles=len(material), source_material_rows=sum(len(m["rows"]) for m in material),
                   source_kinds=dict(Counter(m["source_kind"] for m in material)), rejected=dict(rejected),
                   excluded_record_count=len(excluded), target_record_count=len(targets), split_stats=split_stats,
                   group_disjointness_checks_passed=True, selected=selected, evaluations=evaluations,
                   calibration_parameter_candidates=len(search["candidates"]),
                   calibration_reason=search["reason"], calibration_coverage=coverage["by_class"],
                   best_calibration_correct_by_class={kind:max([c["accepted_correct"].get(kind,0)
                       for c in search["candidates"]]+[0]) for kind in ("multi", "long_whole", "whole4")},
                   holdout_scored=selected is not None,
                   target_predictions_computed=False, production_changed=False, independent_human_labels=0,
                   true_accuracy=None, limitation="All non-count whole controls are structural proxies; masking original punctuation is metamorphic validation, not true accuracy.")
    save("stage-a-summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
