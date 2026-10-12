import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from extract import extract
from validate import check


class HumanFeedbackRules(unittest.TestCase):
    def test_generic_bank_posts_and_complete_institutions(self):
        for title, names in [
            ('关于核准钱建东村镇银行董事任职资格的批复', ['钱建东']),
            ('关于李群农村商业银行董事任职资格的批复', ['李群']),
            ('关于林长沙翔安民生村镇银行行长助理任职资格的批复', ['林长沙']),
            ('关于冯毅健安金汇保险销售服务有限公司总经理任职资格的批复', ['冯毅健']),
            ('关于郝际安融泰保险经纪有限公司总经理任职资格的批复', ['郝际安']),
            ('关于核准袁斯佳井冈山九银村镇银行有限公司计划财务部负责人任职资格的批复', ['袁斯佳']),
        ]:
            result = extract(title)
            self.assertEqual((result['status'], result['names']), ('names', names), title)
            self.assertEqual(check(title, result)['failures'], [])
        self.assertEqual(extract('关于村镇银行董事任职资格的批复')['status'], 'no_name')
        self.assertEqual(extract('关于核准逯晓利村镇银行高级管理人员任职资格的批复')['names'], ['逯晓利'])
        self.assertEqual(extract('关于核准逯晓利村镇银行高级管理人员任职资格的批复')['status'], 'names')
        self.assertEqual(extract('关于通辽金谷村镇银行股份有限公司白玉娥李毅昕高级管理人员任职资格的批复')['status'], 'uncertain')

    def test_connector_rosters_consume_every_fragment(self):
        for title, names in [
            ('关于孙刚与谭雅俊任职资格的批复', ['孙刚', '谭雅俊']),
            ('关于周友和谷政任职资格的批复', ['周友', '谷政']),
            ('关于核准陈远、王宝刚及顾弘任职资格的批复', ['陈远', '王宝刚', '顾弘']),
            ('关于何广利和魏云等四人任职资格的批复', ['何广利', '魏云']),
            ('关于张三和李四、王五任职资格的批复', ['张三', '李四', '王五']),
        ]:
            result = extract(title)
            self.assertEqual((result['status'], result['names']), ('names', names), title)
            self.assertEqual(check(title, result)['failures'], [])
        for name in ['郑和', '刘金和', '孟和巴拉']:
            self.assertEqual(extract(f'关于{name}任职资格的批复')['names'], [name])
        self.assertEqual(extract('关于坂内和隆（SAKAUCHIKAZUTAKA）任职资格的批复')['names'],
                         ['坂内和隆（SAKAUCHIKAZUTAKA）'])
        self.assertEqual(extract('关于呼和格日乐任职资格的批复')['status'], 'uncertain')
        self.assertEqual(extract('关于杨宝秀和孟光一人任职资格的批复')['names'], ['杨宝秀和孟光'])
        self.assertEqual(extract('关于张三和张三一人任职资格的批复')['names'], ['张三和张三'])
        self.assertEqual(extract('关于张三和李四共三人任职资格的批复')['status'], 'uncertain')

    def test_appointment_verb_before_complete_institution_and_department_post(self):
        for title, name in [
            ('关于申玉林任东宁农商行财务会计部总经理的批复', '申玉林'),
            ('关于张继迪任绥芬河农商行内审合规部总经理的批复', '张继迪'),
            ('关于侯琳任绥芬河农商行风险管理部总经理的批复', '侯琳'),
        ]:
            result = extract(title)
            self.assertEqual((result['status'], result['names']), ('names', [name]), title)
            self.assertEqual(check(title, result)['failures'], [], title)
        for title in [
            '关于刘任深圳市南华保险经纪有限公司副总经理任职资格的批复',
            '关于核准何子任高级管理人员任职资格的批复',
            '关于刘永任新华人寿九江中支副总经理（主持工作）的批复',
            '关于张明任农商行财务会计部总经理任职资格的批复',
            '关于张明任东宁农商行财务会计部总经理李华任职资格的批复',
        ]:
            self.assertEqual(extract(title)['status'], 'uncertain', title)
        self.assertEqual(extract('关于何子任村镇银行财务会计部总经理任职资格的批复')['names'], ['何子任'])


if __name__ == '__main__':
    unittest.main()
