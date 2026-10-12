"""Offline cross-title boundary experiment; never imports or changes extraction."""
from collections import defaultdict
import json
from pathlib import Path
import re

WORK = Path(__file__).resolve().parent
PREVIOUS = WORK.parent / '0.6.0'
# A deliberately narrow, independent boundary: bare qualification subjects or
# explicitly punctuated names. Institutional/role-bearing titles are excluded.
DIRECT = re.compile(
    r'.*?关于(?:同意核准|不予核准|核准|批准|同意|核定|确认|注销)?'
    r'(?P<names>[\u3400-\u9fff]{2,4}(?:[、；;][\u3400-\u9fff]{2,4})*)'
    r'(?:的)?任职资格(?:的)?批复')
NON_PERSON = re.compile(r'银行|公司|联社|信用|保险|经理|董事|行长|主任|高管|任职|核准|关于|同志|先生|女士|分局|通知|资格|开业')


def read(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def boundary_index(items):
    index = defaultdict(dict)
    for item in items:
        match = DIRECT.fullmatch(item['title'])
        if match:
            for name in re.split('[、；;]', match['names']):
                if not NON_PERSON.search(name):
                    index[name][item['title']] = item
    return index


def proposals(fragment, title, index):
    """Enumerate only pieces observed at independent complete title boundaries."""
    def visit(start):
        if start == len(fragment):
            return [[]]
        choices = []
        for end in range(start + 2, min(start + 4, len(fragment)) + 1):
            piece = fragment[start:end]
            if any(other != title for other in index.get(piece, {})):
                choices.extend([[piece] + tail for tail in visit(end)])
        return choices
    return [parts for parts in visit(0) if len(parts) > 1]


def main():
    inventory = read(WORK / 'script-r62.jsonl')
    unresolved = read(WORK / 'unresolved-r62.jsonl')
    human = {item['row']: item for item in read(PREVIOUS / 'human-comparison.jsonl')}
    index = boundary_index(inventory)
    cases = []
    controls = {49883, 51022}
    for item in unresolved:
        expected = human.get(item['row'], {}).get('human_expected')
        names = item['result']['names']
        if len(names) != 1 or expected is None:
            continue
        fragment = names[0]
        positive = len(expected['names']) > 1 and ''.join(expected['names']) == fragment
        if not positive and item['row'] not in controls:
            continue
        parts = expected['names'] if positive else (
            human[item['row']].get('surname_split_candidates') or [['殷熊', '毅辉']])[0]
        support = []
        for piece in parts:
            substring_hits = [other for other in inventory
                              if other['title'] != item['title'] and piece in other['title']]
            bounded = [other for title, other in index.get(piece, {}).items() if title != item['title']]
            support.append(dict(piece=piece,
                substring_distinct_titles=len(substring_hits),
                substring_rows=[other['row'] for other in substring_hits],
                independent_boundary_distinct_titles=len(bounded),
                boundary_evidence=[{'row': v['row'], 'rows': v['rows'], 'title': v['title']} for v in bounded]))
        candidates = proposals(fragment, item['title'], index)
        cases.append(dict(row=item['row'], rows=item['rows'], title=item['title'], fragment=fragment,
            case_type='historical_multiple_name_answer' if positive else 'single_name_or_disputed_risk_control',
            historical_human_expected=expected, human_answer_is_independent_blind_truth=False,
            checked_parts=parts, support=support,
            all_parts_have_substring_support=all(v['substring_distinct_titles'] for v in support),
            all_parts_have_boundary_support=all(v['independent_boundary_distinct_titles'] for v in support),
            proposed_splits=candidates, whole_name_competing_interpretation=fragment,
            historical_answer_proposed=expected['names'] in candidates, production_enabled=False))
    # Both pieces can be independent names elsewhere while the target explicitly
    # says one person. This tests the actual sufficiency of cross-title evidence.
    synthetic_index = boundary_index([
        {'row': 'synthetic-a', 'title': '关于张三任职资格的批复'},
        {'row': 'synthetic-b', 'title': '关于李四任职资格的批复'},
    ])
    synthetic = []
    for count, expected in [('两人', ['张三', '李四']), ('一人', ['张三李四'])]:
        title = f'关于张三李四{count}任职资格的批复'
        candidates = proposals('张三李四', title, synthetic_index)
        synthetic.append(dict(title=title, expected=expected, proposed_splits=candidates,
            split_only_policy_would_be_wrong=len(expected) == 1 and bool(candidates),
            production_enabled=False, source='synthetic boundary counterexample'))
    positives = [v for v in cases if v['case_type'] == 'historical_multiple_name_answer']
    report = dict(input_version='r62', title_only=True, duplicate_titles_counted_once=True,
        extraction_imported=False, human_answers_used_only_for_case_selection_and_evaluation=True,
        boundary_scope='仅自动检查直接资格主体和明示标点名单；机构后姓名等其他结构仍需单独核验。',
        positive_cases=len(positives), original_risk_controls=len(cases) - len(positives),
        all_parts_substring_supported=sum(v['all_parts_have_substring_support'] for v in positives),
        all_parts_independent_boundary_supported=sum(v['all_parts_have_boundary_support'] for v in positives),
        historical_multiple_answers_proposed=sum(v['historical_answer_proposed'] for v in positives),
        original_risk_controls_with_split_proposals=sum(bool(v['proposed_splits']) for v in cases if v not in positives),
        synthetic_cases=synthetic, synthetic_false_split_if_evidence_alone_confirms=sum(v['split_only_policy_would_be_wrong'] for v in synthetic),
        production_rules_changed_by_experiment=0, corrected_original_rows=0,
        production_regressed_rows=0, true_accuracy=None,
        conclusion='跨标题边界证据只用于提出研究候选，不能证明当前目标人数；整段解释必须保留。暂不接入生产。')
    write(WORK / 'concatenated-experiment-r63.json', dict(summary=report, cases=cases))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
