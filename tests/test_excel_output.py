import sys
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from excel_output import export_workbook, verify_workbook


XML = b'''<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><dimension ref="A1:M1048576"/><sheetViews><sheetView workbookViewId="0"/></sheetViews><cols><col min="1" max="13" width="12" style="1"/><col min="14" max="16384" width="8" style="1"/></cols><sheetData><row r="1" s="1" spans="1:13"><c r="A1" s="1" t="s"><v>0</v></c><c r="M1" s="2" t="inlineStr"><is><t>body</t></is></c></row><row r="2" s="1"><c r="A2" s="1" t="s"><v>1</v></c><c r="L2" s="3"><v>45000</v></c><c r="M2" s="2" t="inlineStr"><is><t>original &amp; text</t></is></c></row><row r="3" ht="22" customHeight="1"><c r="A3" s="1" t="inlineStr"><is><t>another</t></is></c><c r="M3" s="2"/></row><row r="4" s="1"><c r="A4" t="s"><v>2</v></c></row><row r="1048576" customFormat="1" ht="14"/></sheetData><autoFilter ref="A1:M1048576"><extLst/></autoFilter><pageMargins left="0.75" right="0.75"/></worksheet>'''
RECORDS = [
    {"row": 2, "name": "郑和；A&B", "length": 4},
    {"row": 3, "name": "", "length": 0},
    {"row": 4, "name": None, "length": None},
]


class ExcelPreservation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.source = Path(self.tmp.name) / "source.xlsx"
        self.output = Path(self.tmp.name) / "output.xlsx"
        with ZipFile(self.source, "w") as workbook:
            workbook.writestr("xl/worksheets/sheet1.xml", XML)
            workbook.writestr("xl/styles.xml", b"original styles date and text")
            workbook.writestr("xl/sharedStrings.xml", b"original shared strings")
            workbook.writestr("customXml/item1.xml", b"custom metadata")

    def test_preserves_original_and_distinguishes_zero_from_unresolved(self):
        report = export_workbook(self.source, self.output, RECORDS)
        self.assertEqual(report["records_verified"], 3)
        self.assertEqual(report["xml_rows_preserved"], 5)
        with ZipFile(self.output) as output:
            xml = output.read("xl/worksheets/sheet1.xml")
            self.assertIn(b'<c r="O3" s="2"><v>0</v></c>', xml)
            self.assertIn(b'<c r="O4"/>', xml)
            self.assertIn(b'<row r="1048576" customFormat="1" ht="14"/>', xml)
            self.assertIn(b'ref="A1:O1048576"', xml)
            self.assertIn(b'<col min="16" max="16384" width="8" style="1"/>', xml)
            self.assertEqual(output.read("xl/styles.xml"), b"original styles date and text")

    def test_missing_or_duplicate_result_row_is_rejected(self):
        for records in (RECORDS[:2], RECORDS + [RECORDS[0]]):
            with self.assertRaises(ValueError):
                export_workbook(self.source, self.output, records)
        self.assertFalse(self.output.exists())

    def test_independent_check_detects_original_and_result_corruption(self):
        export_workbook(self.source, self.output, RECORDS)
        for old, new in ((b'<v>45000</v>', b'<v>45001</v>'), (b'<v>4</v>', b'<v>5</v>')):
            damaged = Path(self.tmp.name) / "damaged.xlsx"
            with ZipFile(self.output) as good, ZipFile(damaged, "w") as bad:
                for part in good.namelist():
                    content = good.read(part)
                    bad.writestr(part, content.replace(old, new) if part == "xl/worksheets/sheet1.xml" else content)
            with self.assertRaises(ValueError):
                verify_workbook(self.source, damaged, RECORDS)

    def test_invalid_state_or_source_overwrite_is_rejected(self):
        with self.assertRaises(ValueError):
            export_workbook(self.source, self.source, RECORDS)
        with self.assertRaises(ValueError):
            export_workbook(self.source, self.output, [dict(RECORDS[2], length=0)])

    def test_long_names_expand_only_result_column(self):
        records = [dict(RECORDS[0], name="少数民族较长姓名表达" * 3, length=30), *RECORDS[1:]]
        export_workbook(self.source, self.output, records)
        with ZipFile(self.output) as output:
            xml = output.read("xl/worksheets/sheet1.xml")
            self.assertIn(b'<col min="14" max="14" width="64" customWidth="1" style="1"/>', xml)
            self.assertIn(b'<col min="1" max="13" width="12" style="1"/>', xml)
            self.assertIn(b'<col min="15" max="15" width="14" customWidth="1" style="1"/>', xml)


if __name__ == "__main__":
    unittest.main()
