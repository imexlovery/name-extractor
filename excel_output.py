"""Append name results without reserializing the original workbook cells."""

from __future__ import annotations

import argparse
import copy
import io
import json
from pathlib import Path
import re
import unicodedata
from typing import Iterable
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape
from zipfile import ZipFile


SHEET = "xl/worksheets/sheet1.xml"
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
ROW = re.compile(rb'<row\b[^>]*?(?:/>|>.*?</row>)', re.DOTALL)
CELL = re.compile(rb'<c\b[^>]*?(?:/>|>.*?</c>)', re.DOTALL)


def _attr(xml: bytes, name: bytes) -> bytes | None:
    match = re.search(rb'\b' + name + rb'="([^"]*)"', xml.split(b">", 1)[0])
    return match[1] if match else None


def _records(records: Iterable[dict]) -> dict[int, dict]:
    result = {}
    for record in records:
        row, name, length = record["row"], record["name"], record["length"]
        if type(row) is not int or row < 2 or row in result:
            raise ValueError(f"Invalid or duplicate Excel row: {row!r}")
        if name is None:
            if length is not None:
                raise ValueError(f"Unresolved row {row} must have a blank length")
        elif not isinstance(name, str) or type(length) is not int or length < 0:
            raise ValueError(f"Invalid name or numeric length at row {row}")
        elif (name == "") != (length == 0):
            raise ValueError(f"Empty names and zero length must agree at row {row}")
        result[row] = record
    return result


def _data_rows(xml: bytes) -> set[int]:
    result = set()
    for _, element in ET.iterparse(io.BytesIO(xml), events=("end",)):
        if element.tag == NS + "row":
            row = int(element.attrib["r"])
            if row > 1 and any(
                cell.find(NS + "v") is not None or cell.find(NS + "is") is not None
                or cell.find(NS + "f") is not None
                for cell in element.findall(NS + "c")
            ):
                result.add(row)
            element.clear()
    return result


def _cell(address: str, value: str | int | None, style: bytes | None) -> bytes:
    attrs = f'r="{address}"'.encode()
    if style is not None:
        attrs += b' s="' + style + b'"'
    if value is None or value == "":
        return b"<c " + attrs + b"/>"
    if isinstance(value, str):
        # Inline strings avoid changing sharedStrings.xml; XML text cannot be a formula.
        text = escape(value).encode("utf-8")
        return b'<c ' + attrs + b' t="inlineStr"><is><t xml:space="preserve">' + text + b'</t></is></c>'
    return b"<c " + attrs + b"><v>" + str(value).encode() + b"</v></c>"


def _expand_ref(match: re.Match) -> bytes:
    tag = match[0]
    ref = _attr(tag, b"ref")
    if ref is None:
        return tag
    return tag.replace(b'ref="' + ref + b'"', b'ref="' + re.sub(rb'M(\d+)$', rb'O\1', ref) + b'"', 1)


def _name_column_width(records) -> int:
    return max(48, max((sum(2 if unicodedata.east_asian_width(char) in 'WF' else 1 for char in row['name']) + 4 for row in records if row['name']), default=48))


def _new_columns(xml: bytes, name_width: int) -> bytes:
    match = re.search(rb"<cols>.*?</cols>", xml, re.DOTALL)
    cols = match[0] if match else b"<cols></cols>"
    inherited_style = None
    new = []
    for col in re.finditer(rb"<col\b[^>]*/>", cols):
        raw = col[0]
        first, last = int(_attr(raw, b"min")), int(_attr(raw, b"max"))
        if first <= 14 <= last:
            inherited_style = _attr(raw, b"style")
        if last < 14 or first > 15:
            new.append(raw)
        else:
            if first < 14:
                new.append(re.sub(rb'\bmax="\d+"', b'max="13"', raw))
            if last > 15:
                new.append(re.sub(rb'\bmin="\d+"', b'min="16"', raw))
    style = b' style="' + inherited_style + b'"' if inherited_style else b""
    # Column definitions are kept in ascending order, including a preexisting default tail.
    new.extend([
        b'<col min="14" max="14" width="' + str(name_width).encode() + b'" customWidth="1"' + style + b"/>",
        b'<col min="15" max="15" width="14" customWidth="1"' + style + b"/>",
    ])
    new.sort(key=lambda item: int(_attr(item, b"min")))
    replacement = b"<cols>" + b"".join(new) + b"</cols>"
    if match:
        return xml[:match.start()] + replacement + xml[match.end():]
    return xml.replace(b"<sheetData>", replacement + b"<sheetData>", 1)


def export_workbook(source: str | Path, output: str | Path, records: Iterable[dict]) -> dict:
    """records: {row: Excel row >= 2, name: str|None, length: int|None}."""
    source, output = Path(source), Path(output)
    if source.resolve() == output.resolve():
        raise ValueError("The source workbook must not be overwritten")
    indexed = _records(records)
    with ZipFile(source) as original:
        xml = original.read(SHEET)
        expected = _data_rows(xml)
        if indexed.keys() != expected:
            missing, extra = sorted(expected - indexed.keys()), sorted(indexed.keys() - expected)
            raise ValueError(f"Result row coverage differs: missing={missing[:10]}, extra={extra[:10]}")

        def append(match: re.Match) -> bytes:
            raw = match[0]
            row = int(_attr(raw, b"r"))
            if row != 1 and row not in indexed:
                return raw
            cells = list(CELL.finditer(raw))
            if any(re.match(rb'[NO]\d+$', _attr(c[0], b"r") or b"") for c in cells):
                raise ValueError(f"Source row {row} already contains result columns N/O")
            style = _attr(cells[-1][0], b"s") if cells else _attr(raw, b"s")
            name, length = ("提取姓名", "姓名字数") if row == 1 else (indexed[row]["name"], indexed[row]["length"])
            added = _cell(f"N{row}", name, style) + _cell(f"O{row}", length, style)
            if raw.endswith(b"/>"):
                return raw[:-2] + b">" + added + b"</row>"
            return raw[:-6] + added + b"</row>"

        xml = ROW.sub(append, xml)
        xml = re.sub(rb'<(?:dimension|autoFilter)\b[^>]*>', _expand_ref, xml)
        xml = _new_columns(xml, _name_column_width(indexed.values()))
        output.parent.mkdir(parents=True, exist_ok=True)
        with ZipFile(output, "w") as target:
            target.comment = original.comment
            for info in original.infolist():
                target.writestr(copy.copy(info), xml if info.filename == SHEET else original.read(info.filename))
    return verify_workbook(source, output, indexed.values())


def _top_metadata(xml: bytes) -> list[bytes]:
    root = ET.fromstring(xml)
    result = []
    for child in root:
        if child.tag in {NS + "sheetData", NS + "cols", NS + "dimension"}:
            continue
        if child.tag == NS + "autoFilter":
            child.attrib.pop("ref", None)
        result.append(ET.tostring(child))
    return result


def _column_formats(xml: bytes) -> dict[int, dict]:
    root = ET.fromstring(xml)
    result = {}
    for col in root.findall(NS + "cols/" + NS + "col"):
        attrs = {key: value for key, value in col.attrib.items() if key not in {"min", "max"}}
        for number in range(int(col.attrib["min"]), int(col.attrib["max"]) + 1):
            result[number] = attrs
    return result


def verify_workbook(source: str | Path, output: str | Path, records: Iterable[dict]) -> dict:
    """Independently check ZIP parts, raw original cells/rows and parsed N/O values."""
    indexed = _records(records)
    original_cells = 0
    with ZipFile(source) as original, ZipFile(output) as target:
        if original.namelist() != target.namelist() or original.comment != target.comment:
            raise ValueError("Workbook members/order or ZIP comment changed")
        for part in original.namelist():
            if part != SHEET and original.read(part) != target.read(part):
                raise ValueError(f"Original workbook member changed: {part}")
        before, after = original.read(SHEET), target.read(SHEET)
        if _data_rows(before) != indexed.keys():
            raise ValueError("Verification records do not cover the source data rows")
        if _top_metadata(before) != _top_metadata(after):
            raise ValueError("Original worksheet metadata changed")
        old_columns, new_columns = _column_formats(before), _column_formats(after)
        if any(old_columns.get(number) != new_columns.get(number)
               for number in old_columns.keys() | new_columns.keys() if number not in {14, 15}):
            raise ValueError("Original column formats or widths outside N/O changed")
        if new_columns.get(14, {}).get("width") != str(_name_column_width(indexed.values())) or new_columns.get(15, {}).get("width") != "14":
            raise ValueError("Result columns have incorrect widths")
        for tag in (b"dimension", b"autoFilter"):
            old_range = re.search(rb"<" + tag + rb"\b[^>]*>", before)
            new_range = re.search(rb"<" + tag + rb"\b[^>]*>", after)
            if old_range and (not new_range or _expand_ref(old_range) != new_range[0]):
                raise ValueError(f"Incorrect {tag.decode()} range or metadata")
        source_rows, output_rows = ROW.finditer(before), ROW.finditer(after)
        row_count = 0
        for left, right in zip(source_rows, output_rows, strict=True):
            old, new = left[0], right[0]
            row = int(_attr(old, b"r"))
            if old.split(b">", 1)[0] != new.split(b">", 1)[0]:
                raise ValueError(f"Original row metadata changed at row {row}")
            old_cells = [c[0] for c in CELL.finditer(old)]
            new_cells = [c[0] for c in CELL.finditer(new)]
            kept = [c for c in new_cells if not re.match(rb'[NO]\d+$', _attr(c, b"r") or b"")]
            if old_cells != kept:
                raise ValueError(f"Original cell XML/value/type/style/order changed at row {row}")
            original_cells += len(old_cells)
            if row == 1 or row in indexed:
                node = ET.fromstring(b'<root xmlns="' + NS[1:-1].encode() + b'">' + new + b'</root>')[0]
                additions = {c.attrib["r"]: c for c in node if c.attrib["r"] in {f"N{row}", f"O{row}"}}
                expected = ("提取姓名", "姓名字数") if row == 1 else (indexed[row]["name"], indexed[row]["length"])
                if len(additions) != 2 or len(new_cells) != len(old_cells) + 2:
                    raise ValueError(f"Missing/extra result cells at row {row}")
                for column, wanted in zip(("N", "O"), expected):
                    c = additions[f"{column}{row}"]
                    if wanted is None or wanted == "":
                        valid = len(c) == 0 and "t" not in c.attrib
                    elif isinstance(wanted, str):
                        valid = c.attrib.get("t") == "inlineStr" and "".join(c.itertext()) == wanted
                    else:
                        valid = "t" not in c.attrib and c.findtext(NS + "v") == str(wanted)
                    if not valid:
                        raise ValueError(f"Incorrect result value or type at {column}{row}")
            elif old != new:
                raise ValueError(f"Original formatting row changed at row {row}")
            row_count += 1
        return {
            "records_verified": len(indexed), "original_field_slots_verified": len(indexed) * 13,
            "original_cells_xml_verified": original_cells, "xml_rows_preserved": row_count,
            "unchanged_zip_members": len(original.namelist()) - 1,
            "result_cells_verified": (len(indexed) + 1) * 2,
            "original_values_types_styles_order_preserved": True,
            "original_column_formats_preserved": True,
            "dimension_and_filter_expanded_to_O": True,
            "source_overwritten": False,
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("records", type=Path, help="JSON array or JSONL records")
    args = parser.parse_args()
    raw = args.records.read_text(encoding="utf-8")
    rows = json.loads(raw) if raw.lstrip().startswith("[") else [json.loads(line) for line in raw.splitlines() if line.strip()]
    print(json.dumps(export_workbook(args.source, args.output, rows), ensure_ascii=False, indent=2))
