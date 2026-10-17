"""Optional Indian legal NER. Disabled until a supported model/runtime is validated."""

from functools import lru_cache
import json
import logging
from pathlib import Path
import subprocess

from app.core.config import settings
from app.services.gemini_analysis import SourceText, StructuredExtractionItem


MODEL_NAME = "en_legal_ner_sm"
logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _load_model():
    try:
        import spacy

        return spacy.load(MODEL_NAME)
    except Exception:  # noqa: BLE001 — optional direct installation may be absent.
        return None


def _external_runtime_ready() -> bool:
    interpreter = settings.legal_ner_python
    if not interpreter.is_file():
        return False
    try:
        result = subprocess.run(
            [str(interpreter), str(Path(__file__).with_name("legal_ner_worker.py"))],
            input=json.dumps({"sources": []}),
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
            shell=False,
        )
        return result.returncode == 0 and json.loads(result.stdout).get("ready") is True
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return False


def legal_ner_available() -> bool:
    return settings.legal_ner_enabled and (_load_model() is not None or _external_runtime_ready())


def _structured_item(source: SourceText, entity: dict) -> StructuredExtractionItem:
    label = entity["label"]
    entity_type_by_label = {
        "COURT": "court",
        "PETITIONER": "legal_role",
        "RESPONDENT": "legal_role",
        "JUDGE": "legal_role",
        "LAWYER": "legal_role",
        "WITNESS": "legal_role",
        "OTHER_PERSON": "person",
        "ORG": "organization",
        "GPE": "place",
        "DATE": "other",
        "STATUTE": "other",
        "PROVISION": "other",
        "PRECEDENT": "other",
        "CASE_NUMBER": "other",
    }
    if label not in entity_type_by_label:
        raise ValueError("OpenNyAI returned an unrecognized entity class.")
    text = entity["text"]
    return StructuredExtractionItem(
        source_unit_id=source.source_unit_id,
        item_kind="entity",
        category=entity_type_by_label[label],
        text=text,
        normalized_value=text,
        legal_role=label.casefold() if label in {"PETITIONER", "RESPONDENT", "JUDGE", "LAWYER", "WITNESS"} else None,
        evidence_quote=text,
        confidence=0.5,
        extractor="spacy_legal",
    )


def extract_legal_entities(sources: list[SourceText]) -> list[StructuredExtractionItem]:
    """Return exact spans using the app environment or isolated spaCy runtime."""
    if not settings.legal_ner_enabled:
        return []
    active = [source for source in sources if source.text.strip()]
    if not active:
        return []
    model = _load_model()
    try:
        if model is not None:
            outputs = [
                [{"text": entity.text, "label": entity.label_, "start": entity.start_char, "end": entity.end_char} for entity in doc.ents]
                for doc in model.pipe(source.text for source in active)
            ]
        else:
            interpreter = settings.legal_ner_python
            if not interpreter.is_file():
                return []
            worker_path = str(Path(__file__).with_name("legal_ner_worker.py"))
            result = subprocess.run(
                [str(interpreter), worker_path],
                input=json.dumps({"sources": [source.text for source in active]}, ensure_ascii=False),
                text=True,
                capture_output=True,
                timeout=120,
                check=False,
                shell=False,
            )
            if result.returncode != 0:
                logger.warning("Isolated OpenNyAI worker failed (exit %s).", result.returncode)
                return []
            outputs = json.loads(result.stdout).get("entities", [])
            if len(outputs) != len(active):
                logger.warning("Isolated OpenNyAI worker returned a mismatched batch size.")
                return []
        return [
            _structured_item(source, entity)
            for source, entities in zip(active, outputs, strict=True)
            for entity in entities
            if 0 <= entity["start"] < entity["end"] <= len(source.text)
            and source.text[entity["start"]:entity["end"]] == entity["text"]
        ]
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError, ValueError) as error:
        logger.warning("OpenNyAI extraction was unavailable (%s).", type(error).__name__)
        return []
