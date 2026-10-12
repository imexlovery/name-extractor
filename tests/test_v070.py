import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from extract import extract
from validate import check


class IncompleteTitlesAndInstitutionLinker(unittest.TestCase):
    def test_incomplete_institution_is_not_confirmed_no_name(self):
        for title in [
            '关于同意民生人寿保险股份有限公司河南分公司',
            '关于同意中原农业保险股份有限公司河南省分公司',
            '关于同意中国人民健康保险股份有限公司新乡中心支公司',
            '关于中国工商银行辽宁省分行',
            '关于同意国元农业保险股份有限公司河南分公司',
        ]:
            result = extract(title)
            self.assertEqual((result['status'], result['names']), ('uncertain', []), title)
            self.assertEqual(check(title, result)['failures'], [], title)
        for title in [
            '关于同意民生人寿保险股份有限公司河南分公司的批复',
            '关于同意民生人寿保险股份有限公司河南分公司开业的批复',
            '关于民生人寿保险股份有限公司河南分公司总经理任职资格的批复',
        ]:
            self.assertEqual(extract(title)['status'], 'no_name', title)

    def test_linker_requires_complete_institution_and_consumed_post(self):
        for title, name in [
            ('关于核准叶建中的中国人民财产保险股份有限公司乌兰察布市分公司总经理的批复', '叶建中'),
            ('关于核准杨兴的渤海财产保险股份有限公司乌兰察布市中心支公司总经理的批复', '杨兴'),
        ]:
            result = extract(title)
            self.assertEqual((result['status'], result['names']), ('names', [name]), title)
            self.assertEqual(check(title, result)['failures'], [], title)
        for title in [
            '关于核准叶建中的中国人民财产保险股份有限公司乌兰察布市分公司任职资格的批复',
            '关于核准叶建中的中国人民财产保险股份有限公司乌兰察布市分公司总经理李华任职资格的批复',
        ]:
            self.assertEqual(extract(title)['status'], 'uncertain', title)
        self.assertEqual(extract('关于核准张明的村镇银行总经理任职资格的批复')['names'], ['张明的'])
        self.assertEqual(extract('关于殷熊毅辉任职资格的批复')['status'], 'uncertain')
        self.assertEqual(extract('关于通辽金谷村镇银行股份有限公司白玉娥李毅昕高级管理人员任职资格的批复')['status'], 'uncertain')


if __name__ == '__main__':
    unittest.main()
