from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pandas as pd

def _column_index(label: str) -> int:
    index = 0
    for character in label:
        index = index * 26 + ord(character) - 64
    return index - 1

def read_first_sheet(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    with zipfile.ZipFile(path) as archive:
        shared_strings: list[str] = []
        with archive.open("xl/sharedStrings.xml") as handle:
            for _, element in ET.iterparse(handle, events=("end",)):
                if element.tag.endswith("}si"):
                    shared_strings.append(
                        "".join(
                            member.text or ""
                            for member in element.iter()
                            if member.tag.endswith("}t")
                        )
                    )
                    element.clear()

        rows: list[dict[int, object]] = []
        maximum_column = 0
        with archive.open("xl/worksheets/sheet1.xml") as handle:
            for _, element in ET.iterparse(handle, events=("end",)):
                if not element.tag.endswith("}row"):
                    continue
                values: dict[int, object] = {}
                for cell in list(element):
                    if not cell.tag.endswith("}c"):
                        continue
                    match = re.match(r"([A-Z]+)", cell.attrib.get("r", ""))
                    if not match:
                        continue
                    index = _column_index(match.group(1))
                    maximum_column = max(maximum_column, index + 1)
                    cell_type = cell.attrib.get("t")
                    value = None
                    for member in cell:
                        if member.tag.endswith("}v"):
                            value = member.text
                        elif member.tag.endswith("}is"):
                            value = "".join(
                                item.text or ""
                                for item in member.iter()
                                if item.tag.endswith("}t")
                            )
                    if cell_type == "s" and value is not None:
                        value = shared_strings[int(value)]
                    values[index] = value
                rows.append(values)
                element.clear()

    if not rows:
        return pd.DataFrame()
    matrix = []
    for row in rows:
        output = [None] * maximum_column
        for index, value in row.items():
            output[index] = value
        matrix.append(output)
    headers = [str(value or "").strip() for value in matrix[0]]
    return pd.DataFrame(matrix[1:], columns=headers)
