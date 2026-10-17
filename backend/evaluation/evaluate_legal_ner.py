"""Exact-span precision/recall/F1 for OpenNyAI spaCy NER on hand-labelled JSONL.

Each line in the gold file is an object like:
{"text":"Section 138 of the Negotiable Instruments Act applies.",
 "entities":[{"start":0,"end":10,"label":"PROVISION"}]}
Offsets are zero-based and end-exclusive, matching spaCy and this application's source spans.
"""

import argparse
import json
from collections import Counter
from pathlib import Path

# KING's judgment corpus uses labels that are finer-grained and partly unrelated
# to OpenNyAI's runtime schema. Only the reviewed role/date/place/court crosswalk
# below is scored; document classes, party abbreviations and legal section codes
# are reported as unmapped rather than guessed into model categories.
KING_TO_OPENNYAI = {
    "JD": "JUDGE",
    "AUTH": "JUDGE",
    "HC": "COURT",
    "SC": "COURT",
    "DC": "COURT",
    "PETR": "PETITIONER",
    "RES": "RESPONDENT",
    "DOJUD": "DATE",
    "STE": "GPE",
    "PLC": "GPE",
    "ORG": "ORG",
}
OPENNYAI_TO_BENCHMARK = {
    "JUDGE": "JUDGE",
    "COURT": "COURT",
    "PETITIONER": "PETITIONER",
    "RESPONDENT": "RESPONDENT",
    "DATE": "DATE",
    "GPE": "GPE",
    "ORG": "ORG",
}


def evaluate(gold_path: Path, model_name: str, label_map_name: str = "identity") -> dict:
    import spacy

    nlp = spacy.load(model_name)
    if label_map_name not in {"identity", "king-opennyai"}:
        raise ValueError(f"Unknown label mapping: {label_map_name}")
    counts: dict[str, Counter] = {}
    mapped_gold_count = 0
    unmapped_gold_count = 0
    for line_number, line in enumerate(gold_path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        text = row["text"]
        raw_gold = {(int(item["start"]), int(item["end"]), item["label"]) for item in row["entities"]}
        if any(start < 0 or end <= start or end > len(text) for start, end, _ in raw_gold):
            raise ValueError(f"Invalid span in {gold_path}:{line_number}")
        if label_map_name == "king-opennyai":
            gold = {
                (start, end, KING_TO_OPENNYAI[label])
                for start, end, label in raw_gold
                if label in KING_TO_OPENNYAI
            }
            mapped_gold_count += len(gold)
            unmapped_gold_count += len(raw_gold) - len(gold)
            predicted = {
                (entity.start_char, entity.end_char, OPENNYAI_TO_BENCHMARK[entity.label_])
                for entity in nlp(text).ents
                if entity.label_ in OPENNYAI_TO_BENCHMARK
            }
        else:
            gold = raw_gold
            mapped_gold_count += len(gold)
            predicted = {(entity.start_char, entity.end_char, entity.label_) for entity in nlp(text).ents}
        for label in {item[2] for item in gold | predicted}:
            counter = counts.setdefault(label, Counter())
            label_gold = {item for item in gold if item[2] == label}
            label_predicted = {item for item in predicted if item[2] == label}
            counter["tp"] += len(label_gold & label_predicted)
            counter["fp"] += len(label_predicted - label_gold)
            counter["fn"] += len(label_gold - label_predicted)

    def scores(counter: Counter) -> dict[str, float | int]:
        tp, fp, fn = counter["tp"], counter["fp"], counter["fn"]
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1}

    total = sum(counts.values(), Counter())
    result = {
        "model": model_name,
        "label_mapping": label_map_name,
        "exact_span_micro": scores(total),
        "per_label": {label: scores(value) for label, value in sorted(counts.items())},
    }
    if label_map_name == "king-opennyai":
        result["gold_coverage"] = {
            "mapped_spans": mapped_gold_count,
            "unmapped_spans": unmapped_gold_count,
            "mapped_fraction": mapped_gold_count / (mapped_gold_count + unmapped_gold_count) if mapped_gold_count + unmapped_gold_count else 0.0,
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gold_jsonl", type=Path, nargs="?", default=Path(__file__).parent / "data/normalized/king_ner_gold.jsonl")
    parser.add_argument("--model", default="en_legal_ner_sm")
    parser.add_argument("--label-map", choices=("identity", "king-opennyai"), default="identity")
    args = parser.parse_args()
    print(json.dumps(evaluate(args.gold_jsonl, args.model, args.label_map), indent=2))


if __name__ == "__main__":
    main()
