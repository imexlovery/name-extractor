"""Compare this stage with frozen r61 and retained human feedback."""
from collections import Counter
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
            review_conclusion='完整命名机构及全部消费的岗位支持的为连接词；与已有人工答案一致' if match else result['note'],
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
        known_unresolved_error_rows=[11008],
        new_independent_human_review=False, full_human_review_complete=False, true_accuracy=None,
        production_source='script_only',
        conditional_accuracy_if_all_other_rows_correct=(sum(counts.values()) - counts['uncertain']) / sum(counts.values()),
        conditional_accuracy_is_measured=False))


if __name__ == '__main__':
    main()
