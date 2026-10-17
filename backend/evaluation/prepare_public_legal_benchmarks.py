"""Normalize the downloaded public Indian legal annotation corpora to JSONL."""

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import openpyxl


ROOT = Path(__file__).resolve().parent / "data"
NER_XLSX = ROOT / "king_indian_court_ner" / "Indian_Court_Decision_Annotated_Corpus_xlsx.xlsx"
ROLE_DIR = ROOT / "indian_court_sentence_roles"
OUTPUT_DIR = ROOT / "normalized"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _tag_parts(tag: object) -> tuple[str, str]:
    value = str(tag or "O").strip()
    if "-" not in value:
        return "O", ""
    prefix, label = value.split("-", 1)
    return prefix.upper(), label.strip()


def normalize_king_ner() -> tuple[list[dict], Counter]:
    workbook = openpyxl.load_workbook(NER_XLSX, read_only=True, data_only=True)
    sheet = workbook["Dataset_50"]
    documents: list[dict] = []
    label_counts: Counter = Counter()
    tokens: list[str] = []
    tags: list[object] = []
    document_number = 0

    def finish_document() -> None:
        nonlocal tokens, tags, document_number
        if not tokens:
            return
        document_number += 1
        pieces: list[str] = []
        token_spans: list[tuple[int, int]] = []
        cursor = 0
        for token in tokens:
            if pieces:
                cursor += 1
            start = cursor
            pieces.append(token)
            cursor += len(token)
            token_spans.append((start, cursor))
        entities: list[dict] = []
        active_label: str | None = None
        active_start = 0

        def flush(end: int) -> None:
            nonlocal active_label
            if active_label is not None and end > active_start:
                entities.append({"start": active_start, "end": end, "label": active_label})
                label_counts[active_label] += 1
            active_label = None

        for (start, end), raw_tag in zip(token_spans, tags):
            prefix, label = _tag_parts(raw_tag)
            if prefix in {"U", "S"} and label:
                flush(start)
                entities.append({"start": start, "end": end, "label": label})
                label_counts[label] += 1
            elif prefix == "B" and label:
                flush(start)
                active_label, active_start = label, start
            elif prefix == "I" and label:
                if active_label != label:
                    flush(start)
                    active_label, active_start = label, start
            elif prefix == "L" and label:
                if active_label != label:
                    flush(start)
                    active_label, active_start = label, start
                flush(end)
            else:
                flush(start)

        flush(len(" ".join(pieces)))
        text = " ".join(pieces)
        documents.append({"doc_id": f"KING-{document_number:03d}", "text": text, "entities": entities})
        tokens, tags = [], []

    for row in sheet.iter_rows(min_row=2, values_only=True):
        token = row[0] if len(row) > 0 else None
        bilou_tag = row[2] if len(row) > 2 else None
        token_text = str(token).strip() if token is not None else ""
        if token_text == "<sof>":
            finish_document()
            continue
        if token_text == "<eof>":
            finish_document()
            continue
        if token_text:
            tokens.append(token_text)
            tags.append(bilou_tag)
    finish_document()
    return documents, label_counts


def normalize_sentence_roles() -> tuple[list[dict], Counter]:
    records: list[dict] = []
    label_counts: Counter = Counter()
    for path in sorted(ROLE_DIR.glob("*.txt")):
        for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
            if "\t" not in line:
                continue
            sentence, label = line.rsplit("\t", 1)
            sentence, label = sentence.strip(), label.strip()
            if not sentence or not label:
                continue
            records.append({"doc_id": path.stem, "line_num": line_number, "text": sentence, "label": label})
            label_counts[label] += 1
    return records, label_counts


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ner_docs, ner_labels = normalize_king_ner()
    role_rows, role_labels = normalize_sentence_roles()
    ner_path = OUTPUT_DIR / "king_ner_gold.jsonl"
    role_path = OUTPUT_DIR / "supreme_court_sentence_roles.jsonl"
    ner_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in ner_docs), encoding="utf-8")
    role_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in role_rows), encoding="utf-8")
    summary = {
        "ner": {
            "source_file": str(NER_XLSX.relative_to(ROOT)),
            "sha256": _sha256(NER_XLSX),
            "license": "CC BY 4.0",
            "documents": len(ner_docs),
            "tokens": sum(len(re.findall(r"\S+", row["text"])) for row in ner_docs),
            "entities_by_label": dict(sorted(ner_labels.items())),
            "normalized_file": ner_path.name,
        },
        "sentence_roles": {
            "source_directory": str(ROLE_DIR.relative_to(ROOT)),
            "license": "MIT (upstream repository); confirm underlying judgment text terms before redistribution",
            "documents": len({row["doc_id"] for row in role_rows}),
            "sentences": len(role_rows),
            "sentences_by_label": dict(sorted(role_labels.items())),
            "normalized_file": role_path.name,
        },
        "split_guidance": "Create train/dev/test partitions by doc_id; never split sentences from one judgment across partitions.",
    }
    (OUTPUT_DIR / "benchmark_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ner_documents": len(ner_docs), "ner_entities": sum(ner_labels.values()), "ner_labels": dict(ner_labels), "role_documents": len({row['doc_id'] for row in role_rows}), "role_sentences": len(role_rows), "role_labels": dict(role_labels)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
