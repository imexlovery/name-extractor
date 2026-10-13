"""Evidence failures must not silently become full-corpus coverage."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from acceptance import validate_answer, read, lines


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


if __name__ == '__main__':
    unittest.main()
