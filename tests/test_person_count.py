import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from extract import extract
from validate import check


class PersonCountContract(unittest.TestCase):
    def assert_result(self, title, status, names):
        result = extract(title)
        self.assertEqual((result['status'], result['names']), (status, names), title)
        self.assertEqual(check(title, result)['failures'], [], title)
        return result

    def test_single_count_protects_names_of_different_lengths_and_forms(self):
        for name in ['王夏春子', '殷熊毅辉', '欧阳鹏飞', '索朗次旦', '渡边丈晴',
                     '温八十二', '𠮷田松彦', '阿拉腾础鲁', '孟和巴拉', '张三',
                     '杨宝秀和孟光', 'GohYihYee（吴子宇）']:
            for count in ['一人', '1人', '１人', '一位同志', '1名同志']:
                self.assert_result(f'关于{name}{count}任职资格的批复', 'names', [name])

    def test_count_never_guesses_boundaries_inside_run_on_names(self):
        for fragment in ['陈琳张瑞', '王夏春子', '殷熊毅辉', '欧阳鹏飞',
                         '林远张瑞陈琳', '阿拉腾础鲁', '渡边丈晴']:
            self.assert_result(f'关于{fragment}2人任职资格的批复', 'uncertain', [fragment])

    def test_delimited_rosters_and_complete_person_clauses(self):
        cases = [
            ('关于欧阳鹏飞、陈琳两人任职资格的批复', ['欧阳鹏飞', '陈琳']),
            ('关于张三一人董事、李四一人董事任职资格的批复', ['张三', '李四']),
            ('关于张三一人董事、李四共2人任职资格的批复', ['张三', '李四']),
            ('关于张三中国工商银行董事、李四中国银行董事共2人任职资格的批复', ['张三', '李四']),
            ('关于中国工商银行股份有限公司（董事名单：欧阳鹏飞一人）任职资格的批复', ['欧阳鹏飞']),
            ('关于中国工商银行股份有限公司（董事名单：欧阳鹏飞、林远两人）任职资格的批复', ['欧阳鹏飞', '林远']),
            ('关于杨宝秀和孟光两人任职资格的批复', ['杨宝秀', '孟光']),
            ('关于林远及陈琳2人任职资格的批复', ['林远', '陈琳']),
            ('关于林远与陈琳2人任职资格的批复', ['林远', '陈琳']),
        ]
        for title, names in cases:
            self.assert_result(title, 'names', names)

    def test_cardinality_conflicts_and_boundaries_are_not_hidden(self):
        for title in [
            '关于张三、李四1人任职资格的批复',
            '关于张三、李四3人任职资格的批复',
            '关于张三、李四共十二人任职资格的批复',
            '关于张三、李四共２１人任职资格的批复',
            '关于张三中国工商银行行长李四1人任职资格的批复',
            '关于林远及陈琳及张瑞2人任职资格的批复',
            '关于欧阳映秋一百零一人任职资格的批复',
            '关于欧阳映秋共一百一人任职资格的批复',
        ]:
            self.assertEqual(extract(title)['status'], 'uncertain', title)

    def test_omitted_people_are_not_exact_counts_of_visible_names(self):
        for title, names in [
            ('关于孙体虎等4人任职资格的批复', ['孙体虎']),
            ('关于孙体虎等一百零一人任职资格的批复', ['孙体虎']),
            ('关于欧阳鹏飞等2人任职资格的批复', ['欧阳鹏飞']),
            ('关于张三、李四等3人任职资格的批复', ['张三', '李四']),
        ]:
            self.assert_result(title, 'names', names)
            self.assertNotIn('person_count', extract(title))

    def test_four_characters_and_numeric_name_characters_are_not_vetoes(self):
        for name in ['欧阳鹏飞', '索朗次旦', '渡边丈晴', '温八十二', '王一名', '孟和巴拉']:
            self.assert_result(f'关于{name}任职资格的批复', 'names', [name])
        self.assert_result('关于林零1人任职资格的批复', 'names', ['林零'])

    def test_reviewed_ambiguities_abstain_without_changing_fragments(self):
        for fragment in ['王夏春子', '殷熊毅辉', '陈琳张瑞', '胡宇陈琳', '张瑞胡铁', '陈琳胡宇', '胡铁张瑞']:
            result = self.assert_result(f'关于{fragment}任职资格的批复', 'uncertain', [fragment])
            self.assertEqual(result['rule'], 'reviewed_title_ambiguity')

    def test_plural_structure_supports_connectors_but_never_run_on_splits(self):
        for title, names in [
            ('关于张三和李四分别担任董事任职资格的批复', ['张三', '李四']),
            ('关于林远及陈琳分别董事任职资格的批复', ['林远', '陈琳']),
            ('关于欧阳鹏飞、林远分别任职资格的批复', ['欧阳鹏飞', '林远']),
            ('关于林远中国工商银行董事、陈琳中国银行董事分别任职资格的批复', ['林远', '陈琳']),
        ]:
            self.assert_result(title, 'names', names)
        for name in ['王夏春子', '陈琳张瑞', '林远张瑞陈琳', '欧阳鹏飞']:
            self.assert_result(f'关于{name}分别担任董事任职资格的批复', 'uncertain', [name])


if __name__ == '__main__':
    unittest.main()
