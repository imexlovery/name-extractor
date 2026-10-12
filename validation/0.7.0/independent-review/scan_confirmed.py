"""Offline risk census of frozen, confirmed name outputs.

This does not import or rerun an extractor, use a person/surname dictionary,
or read article bodies. Regex hits are nominations, never semantic truth.
Run from any directory: python3 scan_confirmed.py
"""

from __future__ import annotations

import argparse
import collections
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_SOURCE = HERE.parent / "script-r63.jsonl"
KNOWN_FOUR = HERE.parents[1] / "0.5.0" / "four-character-review.jsonl"

# Independent, deliberately broad cues. Incomplete position coverage is kept
# visible as a risk rather than hidden behind production institution anchors.
HAN = r"[\u3400-\u9fff\uf900-\ufaff\U00020000-\U0003347f]"
PERSON_OUTPUT_TOKEN = re.compile(
    r"银行|公司|任职|批复|核准|董事|理事|监事|经理|主任|负责人|"
    r"高管|信用社|联社|代表处|营业部|管理部|总行"
)
LEFT_INSTITUTION_END = re.compile(
    r"(?:公司|银行|分行|支行|分社|联社|信用社|农商行|农合行|农信社|"
    r"中支|财险|人寿|寿险|信托|村行|财务|代表处|营业部|服务点|中心|"
    r"公社|互保|金租|消金|理财|行|社)\s*$"
)
LEFT_HEADER = re.compile(
    r"^\s*(?:关于|对|核准|批准|不予核准|同意|同意核准|确认|拟任|"
    r"终止审查|不予许可|核定|任职|担任|出任|申请|注销|准予|决定|"
    r"取消|任命|变更|更换|[：:、，,；;\s])*\s*$"
)
LEFT_POSITION_END = re.compile(
    r"(?:经理|理事|董事|监事|主任|行长|代表|负责人|高管|管理人员|总监|"
    r"秘书|助理|会长|顾问|精算师|审计师|责任人|风险官|合规官|财务官|"
    r"信息官|运营官|会计师|总裁|董事会|风险管理部)\s*$"
)
POSITION_CUE = (
    r"(?:董事会秘书|行长助理|(?:副)?(?:董事|理事|监事)长|"
    r"(?:独立|执行|非执行|职工|股东)?董事|(?:独立|职工)?理事|监事|"
    r"(?:副)?行长|总经理助理|副总经理|总经理|总裁助理|副总裁|总裁|"
    r"主任助理|副主任|主任|(?:首席)?(?:合规|风险|财务|信息|运营)官|"
    r"(?:合规|财务|主要|内审)?负责人|风险总监|高管|高级管理人员|经理)"
)
AFTER_POSITION_LINK = re.compile(
    POSITION_CUE + r"(?:(?:[（(][^（）()]*[）)])?\s*)[、，,；;及和与]+\s*(.+)"
)
EXACT_COUNT = re.compile(r"([0-9０-９一二三四五六七八九十百两]+)(?:人|位同志|名同志|位|名)")


def read_jsonl(path):
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def count_value(text):
    digits = "０１２３４５６７８９"
    text = text.translate(str.maketrans(digits, "0123456789"))
    if text.isdigit():
        return int(text)
    values = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
              "六": 6, "七": 7, "八": 8, "九": 9}
    if text in values:
        return values[text]
    if "十" in text:
        left, right = text.split("十", 1)
        if (not left or left in values) and (not right or right in values):
            return values.get(left, 1) * 10 + values.get(right, 0)
    return None


def risk_scan(record):
    title, answer = record["title"], record["result"]
    names = answer["names"]
    risks, counters = [], collections.Counter()
    spans, cursor = [], 0
    masked = list(title)
    for name in names:
        start = title.find(name, cursor)
        if start < 0:
            risks.append({"category": "output_not_in_source_order", "text": name,
                          "reason": "输出姓名未按顺序原样出现于原标题"})
            continue
        end = start + len(name)
        if spans and not title[spans[-1][1]:start].strip():
            risks.append({"category": "undelimited_output_split", "span": [spans[-1][0], end],
                          "reason": "多个输出姓名之间无原标题分隔；人数边界需复核"})
        spans.append((start, end))
        masked[start:end] = "■" * len(name)
        cursor = end
        if PERSON_OUTPUT_TOKEN.search(name):
            risks.append({"category": "institution_or_position_in_output", "text": name,
                          "reason": "姓名输出包含完整机构或职务词片段"})
        if re.fullmatch(HAN + r"{4}", name):
            risks.append({"category": "four_character_person_count", "text": name,
                          "reason": "连续四字姓名没有内部人数边界；长度只作已知风险线索"})
        if re.fullmatch(HAN, name) or re.fullmatch(HAN + r"{5,}", name):
            risks.append({"category": "unusual_contiguous_length", "text": name,
                          "reason": "单字或超过四字的纯汉字姓名片段需要语义复核"})
        if any(c.isalpha() and c.isascii() is False and ord(c) < 0x3400 for c in name):
            counters["extended_latin_name_titles"] = 1
    if spans:
        left = title[:spans[0][0]]
        if not (LEFT_HEADER.fullmatch(left) or LEFT_INSTITUTION_END.search(left)
                or LEFT_POSITION_END.search(left)):
            risks.append({"category": "left_boundary_unparsed", "text": left,
                          "reason": "姓名左边不是简式许可前缀、机构结尾或岗位结尾；检查候选缺字/未消费主体"})
    outer_masked = "".join(masked)
    for match in AFTER_POSITION_LINK.finditer(outer_masked):
        tail = match.group(1)
        if not re.match(POSITION_CUE, tail) and not tail.startswith("■"):
            risks.append({"category": "unconsumed_after_position_link", "text": match.group(0),
                          "span": list(match.span()),
                          "reason": "已出现职务后仍有连接词及未输出尾段；检查第二主体或岗位词覆盖不足"})
    qualification_count = title.count("任职")
    if qualification_count > len(names):
        risks.append({"category": "qualification_count_exceeds_outputs", "count": qualification_count,
                      "reason": "任职字样次数多于输出人数；检查遗漏主体或原标题重复"})
    if "任职" not in title:
        risks.append({"category": "nonstandard_title_qualification", "reason": "原标题缺任职字样；检查非标准边界、错字及候选截断"})
    for match in EXACT_COUNT.finditer(title):
        if any(start <= match.start() and match.end() <= end for start, end in spans):
            continue  # 王一名 is an output name, not an explicit count claim.
        if "等" in title[max(0, match.start() - 5):match.start()]:
            continue  # The contract extracts only explicitly written names before 等.
        value = count_value(match.group(1))
        if value is None:
            continue
        counters["explicit_exact_count_titles"] = 1
        if value != len(names):
            risks.append({"category": "explicit_person_count_mismatch", "text": match.group(0),
                          "reason": f"标题精确人数{value}与输出姓名数{len(names)}不一致"})
    counters["multi_output_titles"] = int(len(names) > 1)
    counters["connector_titles_outside_outputs"] = int(bool(re.search(r"[；;、及和与]", outer_masked)))
    return risks, counters


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output-dir", type=Path, default=HERE)
    parser.add_argument("--reviews", type=Path, default=HERE / "scan_confirmed_reviews.jsonl")
    args = parser.parse_args()
    records = read_jsonl(args.source)
    known = {r["title"]: r for r in read_jsonl(KNOWN_FOUR)} if KNOWN_FOUR.exists() else {}
    reviews = {r["row"]: r for r in read_jsonl(args.reviews)} if args.reviews.exists() else {}
    statuses, status_rows = collections.Counter(), collections.Counter()
    signal_counts = collections.Counter({category: 0 for category in (
        "output_not_in_source_order", "undelimited_output_split",
        "institution_or_position_in_output", "unusual_contiguous_length",
        "four_character_person_count", "left_boundary_unparsed",
        "unconsumed_after_position_link", "qualification_count_exceeds_outputs",
        "nonstandard_title_qualification", "explicit_person_count_mismatch",
    )})
    census, judgments = collections.Counter(), collections.Counter()
    queue, uncertain_rows = [], []
    covered = 0
    for record in records:
        status = record["result"]["status"]
        statuses[status] += 1
        status_rows[status] += len(record["rows"])
        if status == "uncertain":
            uncertain_rows.append(record["row"])
        if status != "names":
            continue
        covered += 1
        risks, counts = risk_scan(record)
        census.update(counts)
        if not risks:
            continue
        signal_counts.update({r["category"] for r in risks})
        is_known = record["title"] in known and any(r["category"] == "four_character_person_count" for r in risks)
        item = {"row": record["row"], "rows": record["rows"], "title": record["title"],
                "script_answer": record["result"], "risk_triggers": risks,
                "known_risk": is_known,
                "known_evidence": str(KNOWN_FOUR.relative_to(HERE.parents[2])) if is_known else None,
                "review_judgment": "not_reviewed", "review_evidence": [],
                "program_evidence": "独立风险筛查覆盖全部status=names；规则命中仅表示需复核",
                "ai_review": False, "human_review": False,
                "body_viewed": False, "strict_blind_review": False}
        review = reviews.get(record["row"])
        if review and review.get("title") == record["title"] and review.get("script_names") == record["result"]["names"]:
            item.update({"review_judgment": review["judgment"], "review_evidence": review["evidence"],
                         "ai_review": review.get("ai_review", False),
                         "human_review": review.get("human_review", False),
                         "reviewer": review.get("reviewer")})
        judgments[item["review_judgment"]] += 1
        queue.append(item)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    target = args.output_dir / "scan_confirmed_suspects.jsonl"
    target.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in queue), encoding="utf-8")
    summary = {
        "source": str(args.source.resolve()), "extractor_imported_or_rerun": False,
        "body_fields_read": False, "person_or_surname_dictionary_used": False,
        "unique_titles": len(records), "mapped_rows": sum(status_rows.values()),
        "status_titles": dict(statuses), "status_rows": dict(status_rows),
        "confirmed_title_scan_coverage": covered, "confirmed_row_scan_coverage": status_rows["names"],
        "risk_nominated_titles": len(queue), "risk_nominated_rows": sum(len(r["rows"]) for r in queue),
        "risk_signal_counts": dict(signal_counts), "census": dict(census),
        "review_judgments": dict(judgments),
        "new_confirmed_errors": sum(r["review_judgment"] == "confirmed_error" and not r["known_risk"] for r in queue),
        "new_title_ambiguities": sum(r["review_judgment"] == "new_ambiguity" and not r["known_risk"] for r in queue),
        "reviewed_false_positive_titles": judgments["false_positive"],
        "known_person_count_risk_titles": sum(r["known_risk"] for r in queue),
        "unread_nominated_titles": judgments["not_reviewed"],
        "ai_reviewed_titles": sum(r["ai_review"] for r in queue),
        "confirmed_titles_not_individually_ai_reviewed": covered - sum(r["ai_review"] for r in queue),
        "independent_human_reviews_added": 0,
        "uncertain_titles_separately_counted": statuses["uncertain"],
        "uncertain_rows_separately_counted": status_rows["uncertain"],
        "uncertain_representative_rows": uncertain_rows,
        "interpretation": "全量程序风险筛查及命中集合的非盲AI原标题复核；不代表全量语义标注、人工验收或真实准确率。四字已知人数风险未被证明消除。",
        "review_file": str(args.reviews.resolve()), "suspects_file": str(target.resolve()),
    }
    summary_path = args.output_dir / "scan_confirmed_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
