"""Compare this stage with frozen r61 and retained human feedback."""
from collections import Counter
import csv
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from extract import VERSION
from pilot import read_jsonl, write_json, write_jsonl

WORK = Path(__file__).resolve().parent
PREVIOUS = ROOT / 'validation/0.6.0'


def main():
    data = read_jsonl(WORK / f'script-{VERSION}.jsonl')
    changes = read_jsonl(WORK / f'changes-from-r61-{VERSION}.jsonl')
    human = {v['row']: v for v in read_jsonl(PREVIOUS / 'human-comparison.jsonl')}
    no_name_review = {v['row']: v for v in read_jsonl(PREVIOUS / 'no-name-ai-review.jsonl')}
    reviews = []
    for item in changes:
        expected = human.get(item['row'], {}).get('human_expected')
        result = item['result']
        match = expected is not None and (result['status'], result['names']) == (expected['status'], expected['names'])
        reviews.append(dict(item,
            matches_existing_human_judgment=match,
            human_expected=expected,
            previous_no_name_codex_review=no_name_review.get(item['row']),
            review_conclusion=f"{result['rule']}：{result['note'] or '标题结构支持当前确认状态'}" + ('；与已有人工记录一致' if match else ''),
            reviewed_by='Codex逐条标题结构复核',
            new_independent_human_review=False))
    write_jsonl(WORK / f'change-review-{VERSION}.jsonl', reviews)
    write_jsonl(WORK / 'remaining-unresolved.jsonl', [dict(item,
        human_expected=human.get(item['row'], {}).get('human_expected'),
        surname_split_candidates=human.get(item['row'], {}).get('surname_split_candidates', []))
        for item in data if item['result']['status'] == 'uncertain'])
    counts = {status: sum(len(v['rows']) for v in data if v['result']['status'] == status)
              for status in ('names', 'no_name', 'uncertain')}
    frozen_sample = {v['row'] for v in read_jsonl(PREVIOUS / 'random-human-frozen.jsonl')}
    solved = [v for v in reviews if v['before']['status'] == 'uncertain' and v['result']['status'] == 'names']
    current = {v['row']: v for v in data}
    determinate_human = [v for v in human.values()
                        if (v.get('human_expected') or {}).get('status') in {'names', 'no_name'}]
    complete_human = [v for v in determinate_human
                      if (current[v['row']]['result']['status'], current[v['row']]['result']['names'])
                      == (v['human_expected']['status'], v['human_expected']['names'])]
    blind_progress = {}
    for kind, path in [('no_name', PREVIOUS / '原694无姓名标题-人工盲审.csv'),
                       ('random', PREVIOUS / '随机200标题-人工盲审.csv')]:
        with path.open(encoding='utf-8-sig', newline='') as file:
            rows = list(csv.DictReader(file))
        blind_progress[kind] = dict(source=str(path.relative_to(ROOT)), titles=len(rows),
            filled=sum(bool(v['人工姓名或无姓名判断'].strip()) for v in rows),
            filling_is_not_correctness_validation=True)
    write_json(WORK / 'stage-report.json', dict(
        release_version='0.7.0', version=VERSION, baseline_version='r61', baseline_tag='v0.6.0-r61',
        unique_titles=len(data), mapped_rows=sum(counts.values()),
        status_titles=dict(Counter(v['result']['status'] for v in data)), status_rows=counts,
        changed_titles=len(changes), changed_rows=sum(len(v['rows']) for v in changes),
        newly_resolved_names_titles=len(solved), newly_resolved_names_rows=sum(len(v['rows']) for v in solved),
        solutions_matching_existing_human_titles=sum(v['matches_existing_human_judgment'] for v in solved),
        changed_existing_name_outputs=sum(v['before']['status'] == 'names' for v in changes),
        incomplete_no_name_to_uncertain_rows=[v['row'] for v in changes if v['before']['status'] == 'no_name' and v['result']['status'] == 'uncertain'],
        hard_failure_titles=sum(bool(v['checks']['failures']) for v in data),
        random_sample_changes=sum(v['row'] in frozen_sample for v in changes),
        known_unresolved_error_rows=[row for row in [11008]
            if (current[row]['result']['status'], current[row]['result']['names'])
            != (human[row]['human_expected']['status'], human[row]['human_expected']['names'])],
        historical_human_answer_completion=dict(
            reviewed_titles=len(human), determinate_answer_titles=len(determinate_human),
            exact_completed_titles=len(complete_human),
            pending_titles=len(determinate_human) - len(complete_human),
            answer_still_uncertain_titles=len(human) - len(determinate_human),
            completion_fraction=len(complete_human) / len(determinate_human),
            some_answers_content_assisted=True, independent_final_acceptance=False),
        historical_optional_human_review_progress=blind_progress,
        new_independent_human_review=False, full_human_review_complete=False, true_accuracy=None,
        production_source='script_only',
        conditional_accuracy_if_all_other_rows_correct=(sum(counts.values()) - counts['uncertain']) / sum(counts.values()),
        conditional_accuracy_is_measured=False))


if __name__ == '__main__':
    main()
