"""JSON stdin/stdout worker for an optional legal NER runtime."""

import json
import sys


def main() -> None:
    request = json.load(sys.stdin)
    import spacy

    nlp = spacy.load("en_legal_ner_sm")
    texts = request.get("sources", [])
    entities = [
        [
            {"text": entity.text, "label": entity.label_, "start": entity.start_char, "end": entity.end_char}
            for entity in doc.ents
        ]
        for doc in nlp.pipe(texts)
    ]
    json.dump({"ready": True, "entities": entities}, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
