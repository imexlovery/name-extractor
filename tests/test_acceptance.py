"""Evidence failures must not silently become full-corpus coverage."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from acceptance import validate_answer, read, lines, compare, save, freeze_reference, final_compare


class IndependentEvidenceContract(unittest.TestCase):
    def test_unicode_line_separator_in_original_body_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'original.jsonl'
            records = [dict(内容='原文\u2028仍属于同一条正文')]
            lines(path, records)
            self.assertEqual(read(path), records)

    def setUp(self):
        self.source = dict(input_id='input-00001', row_id='Sheet1:00002', 标题='关于白玉娥李毅昕任职资格的批复',
                           内容='核准白玉娥、李毅昕的任职资格，另提张明。')
        self.answer = dict(input_id='input-00001', row_id='Sheet1:00002', names=['白玉娥', '李毅昕'],
             title_evidence=[dict(name='白玉娥', quote='白玉娥'), dict(name='李毅昕', quote='李毅昕')],
             body_evidence=['核准白玉娥、李毅昕的任职资格'], status='names', reason='正文明确分别列名，标题连续片段为二人。',
             model='gpt-6-luna', prompt_version='title-body-blind-v1')

    def test_two_people_keep_two_title_spans(self):
        result = validate_answer(self.answer, self.source)
        self.assertEqual([(e['start'], e['end']) for e in result['title_evidence']], [(2, 5), (5, 8)])
        self.assertEqual(result['names'], ['白玉娥', '李毅昕'])

    def test_body_only_name_cannot_enter_reference(self):
        answer = copy.deepcopy(self.answer)
        answer['names'] = ['张明']
        answer['title_evidence'] = [dict(name='张明', quote='张明')]
        with self.assertRaises(AssertionError):
            validate_answer(answer, self.source)

    def test_rewritten_body_quote_is_rejected(self):
        answer = dict(self.answer, body_evidence=['核准白玉娥与李毅昕任职资格'])
        with self.assertRaises(AssertionError):
            validate_answer(answer, self.source)

    def test_body_quote_object_is_rejected_even_when_its_quote_is_literal(self):
        answer = dict(self.answer, body_evidence=[dict(quote=self.answer['body_evidence'][0])])
        with self.assertRaises(AssertionError):
            validate_answer(answer, self.source)

    def test_independent_prompt_is_accepted_only_in_second_round(self):
        answer = dict(self.answer, prompt_version='title-body-independent-v1')
        with self.assertRaises(AssertionError):
            validate_answer(answer, self.source)
        self.assertEqual(validate_answer(answer, self.source, ('title-body-independent-v1',))['names'], self.answer['names'])

    def test_wrong_identity_and_empty_confirmed_answer_are_rejected(self):
        for change in [dict(row_id='Sheet1:00003'), dict(names=[], title_evidence=[], status='names'),
                       dict(status='no_name'), dict(prompt_version='old-reference')]:
            with self.subTest(change=change), self.assertRaises(AssertionError):
                validate_answer(dict(self.answer, **change), self.source)

    def test_corrected_first_answer_still_gets_raw_independent_reread(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work = root / 'acceptance'
            source = dict(self.source, 标题='关于张明任职资格的批复', 内容='核准张明的任职资格。')
            answer = dict(self.answer, names=['张明'], title_evidence=[dict(name='张明', quote='张明')],
                          body_evidence=[], reason='标题明示一人。')
            lines(work / 'blind/inputs.jsonl', [source])
            lines(work / 'valid-first-answers.jsonl', [answer])
            lines(work / 'row-map.jsonl', [dict(input_id=source['input_id'], row_id=source['row_id'], excel_row=2)])
            lines(root / 'validation/0.7.0/script-r64.jsonl', [dict(rows=[2], result=dict(status='names', names=['张明']), risk_categories=[])])
            lines(work / 'answers/retries/old.jsonl', [dict(answer, names=[], title_evidence=[], status='no_name')])
            with patch('acceptance.ROOT', root), patch('acceptance.WORK', work):
                compare()
            self.assertEqual(read(work / 'blind/second-inputs.jsonl'), [source])
            self.assertNotIn('names', read(work / 'blind/second-inputs.jsonl')[0])
            # Later-round retries must not redefine the already fixed first-review cohort.
            lines(work / 'answers/retries/old.jsonl', [dict(answer, names=[], status='no_name',
                  prompt_version='title-body-adjudication-v1')])
            with patch('acceptance.ROOT', root), patch('acceptance.WORK', work):
                compare()
            self.assertEqual(read(work / 'blind/second-inputs.jsonl'), [])

    def test_freezing_requires_coverage_and_preserves_each_cached_row_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            save(work / 'manifest.json', dict(source_rows=2, unique_full_inputs=1))
            lines(work / 'blind/inputs.jsonl', [self.source])
            lines(work / 'blind/second-inputs.jsonl', [self.source])
            lines(work / 'adjudication/third-inputs.jsonl', [])
            lines(work / 'valid-first-answers.jsonl', [])
            lines(work / 'valid-second-answers.jsonl', [dict(self.answer, prompt_version='title-body-independent-v1')])
            lines(work / 'valid-third-answers.jsonl', [])
            lines(work / 'row-map.jsonl', [dict(input_id=self.source['input_id'], row_id=f'Sheet1:{n:05d}', excel_row=n) for n in (2, 3)])
            for stage in ('', 'second-', 'third-'):
                save(work / f'invalid-{stage}answers.json', [])
            with patch('acceptance.WORK', work):
                with self.assertRaises(ValueError):
                    freeze_reference()
                self.assertFalse((work / 'fixed-reference.jsonl').exists())
                lines(work / 'valid-first-answers.jsonl', [self.answer])
                freeze_reference()
                with self.assertRaises(ValueError):
                    freeze_reference()
            records = read(work / 'fixed-row-reference.jsonl')
            self.assertEqual([r['row_id'] for r in records], ['Sheet1:00002', 'Sheet1:00003'])
            self.assertEqual([r['source_row_id'] for r in records], ['Sheet1:00002'] * 2)
            self.assertEqual([r['names'] for r in records], [['白玉娥', '李毅昕']] * 2)
            self.assertFalse(__import__('json').loads((work / 'reference-manifest.json').read_text())['final_acceptance_passed'])

    def test_final_comparison_counts_real_splits_and_excludes_unknown_truth(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory) / 'acceptance'
            from extract import VERSION
            title = self.source['标题']
            sources = [dict(row_id=f'Sheet1:{i:05d}', excel_row=i, fields={'标题': title}) for i in (2, 3, 4)]
            references = [dict(row_id=s['row_id'], input_id=f'input-{i}', names=['白玉娥', '李毅昕'],
                               status='conflict' if i == 1 else 'names') for i, s in enumerate(sources)]
            snapshots = [dict(rows=[s['excel_row']], title=title,
                result=dict(names=['白玉娥李毅昕'] if i == 2 else ['白玉娥', '李毅昕'], status='names'))
                for i, s in enumerate(sources)]
            save(work / 'reference-manifest.json', dict(row_count=3, version='v1'))
            save(work / 'progress.json', dict(ai_review_coverage=1, human_reviewed_rows=0, human_status_rows={}))
            lines(work / 'source-rows.jsonl', sources)
            lines(work / 'fixed-row-reference.jsonl', references)
            lines(work.parent / f'script-{VERSION}.jsonl', snapshots)
            with patch('acceptance.WORK', work), patch('acceptance.collect'):
                final_compare()
            metrics = __import__('json').loads((work / 'final-comparison.json').read_text())
            self.assertEqual(metrics['categories_rows'], {'match': 1, 'unresolved_reference': 1, 'count_or_split_difference': 1})
            self.assertEqual(metrics['reference_agreement'], 1/3)
            self.assertEqual(metrics['confirmed_reference_agreement'], 1/2)
            self.assertIsNone(metrics['true_accuracy'])
            self.assertFalse(metrics['acceptance_passed'])


if __name__ == '__main__':
    unittest.main()
