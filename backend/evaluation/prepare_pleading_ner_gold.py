"""Convert advocate annotations from the pilot CSV into evaluator-ready JSONL.

CSV has one row per entity mention. Repeat document_id, page_num, passage_id,
and text for each mention in the same passage. Use label NONE for passages
with no target entities. Offsets are derived from exact text and occurrence_number.
"""

import argparse
import csv
import json
from collections import OrderedDict
from pathlib import Path


ALLOWED_LABELS = {
    "COURT", "PETITIONER", "RESPONDENT", "JUDGE", "LAWYER", "WITNESS",
    "OTHER_PERSON", "ORG", "GPE", "DATE", "STATUTE", "PROVISION",
    "PRECEDENT", "CASE_NUMBER", "NONE",
}


def convert(source: Path, destination: Path) -> int:
    passages: OrderedDict[tuple[str, str], dict] = OrderedDict()
    with source.open(encoding="utf-8-sig", newline="") as stream:
        for line_number, row in enumerate(csv.DictReader(stream), 2):
            document_id = (row.get("document_id") or "").strip()
            passage_id = (row.get("passage_id") or "").strip()
            text = row.get("text") or ""
            label = (row.get("label") or "").strip().upper()
            entity_text = row.get("entity_text") or ""
            if not any((document_id, text, label, entity_text)):
                continue
            if not document_id or not passage_id or not text.strip():
                raise ValueError(f"Row {line_number}: document_id, passage_id, and text are required")
            if label not in ALLOWED_LABELS:
                raise ValueError(f"Row {line_number}: unsupported label {label!r}")

            key = (document_id, passage_id)
            passage = passages.setdefault(key, {
                "document_id": document_id,
                "document_type": (row.get("document_type") or "").strip(),
                "page_num": (row.get("page_num") or "").strip(),
                "passage_id": passage_id,
                "text": text,
                "entities": [],
            })
            if passage["text"] != text:
                raise ValueError(f"Row {line_number}: text differs for passage {passage_id}")
            if label == "NONE":
                if entity_text.strip():
                    raise ValueError(f"Row {line_number}: NONE rows must have empty entity_text")
                continue
            if not label and not entity_text.strip():
                raise ValueError(f"Row {line_number}: label this row or mark it NONE after review")
            if not label or not entity_text:
                raise ValueError(f"Row {line_number}: provide both entity_text and label")

            try:
                occurrence = int((row.get("occurrence_number") or "1").strip())
            except ValueError as error:
                raise ValueError(f"Row {line_number}: occurrence_number must be a positive integer") from error
            if occurrence < 1:
                raise ValueError(f"Row {line_number}: occurrence_number must be a positive integer")
            starts = []
            cursor = 0
            while True:
                start = text.find(entity_text, cursor)
                if start < 0:
                    break
                starts.append(start)
                cursor = start + 1
            if occurrence > len(starts):
                raise ValueError(
                    f"Row {line_number}: occurrence {occurrence} of {entity_text!r} not found exactly in passage"
                )
            start = starts[occurrence - 1]
            passage["entities"].append({"start": start, "end": start + len(entity_text), "label": label})

    if not passages:
        raise ValueError("No annotated passages found in the CSV")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="\n") as stream:
        for passage in passages.values():
            stream.write(json.dumps(passage, ensure_ascii=False) + "\n")
    return len(passages)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("jsonl_path", type=Path)
    args = parser.parse_args()
    count = convert(args.csv_path, args.jsonl_path)
    print(f"Wrote {count} annotated passages to {args.jsonl_path}")


if __name__ == "__main__":
    main()
