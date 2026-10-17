"""Optional local InLegalBERT classifier for legal rhetorical sentence roles."""

from functools import lru_cache
import logging
import os
from pathlib import Path

from app.services.gemini_analysis import SourceText, StructuredExtractionItem


logger = logging.getLogger(__name__)
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MODEL_DIR = REPO_ROOT / ".runtime" / "models" / "legal_sentence_roles" / "model"
MAX_CLASSIFICATION_BATCH = 16
MODEL_LABELS = {
    "argument",
    "fact",
    "precedent",
    "ratio_decidendi",
    "ruling_lower_court",
    "ruling_present_court",
    "statute",
}


def _model_path() -> Path:
    configured = os.getenv("LEGAL_SENTENCE_ROLE_MODEL_PATH")
    return Path(configured).expanduser() if configured else DEFAULT_MODEL_DIR


@lru_cache(maxsize=1)
def _load_classifier():
    model_path = _model_path()
    if not model_path.is_dir():
        return None
    try:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
        model = AutoModelForSequenceClassification.from_pretrained(model_path, local_files_only=True)
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model.to(device)
        model.eval()
        return torch, tokenizer, model, device
    except Exception:  # noqa: BLE001 — optional local model must not break case analysis.
        logger.exception("Optional InLegalBERT sentence-role model could not be loaded")
        return None


def sentence_role_classifier_available() -> bool:
    return _load_classifier() is not None


def classify_sentence_roles(sources: list[SourceText]) -> list[StructuredExtractionItem]:
    """Add exact-source sentence-role predictions; scores are not calibrated."""
    loaded = _load_classifier()
    if loaded is None:
        return []

    torch, tokenizer, model, device = loaded
    predictions: list[StructuredExtractionItem] = []
    active_sources = [source for source in sources if source.text.strip()]
    id_to_label = {
        int(index): str(label).casefold()
        for index, label in model.config.id2label.items()
    }
    if not id_to_label or any(label not in MODEL_LABELS for label in id_to_label.values()):
        logger.error("InLegalBERT sentence-role model has an unexpected label map")
        return []

    for start in range(0, len(active_sources), MAX_CLASSIFICATION_BATCH):
        batch_sources = active_sources[start : start + MAX_CLASSIFICATION_BATCH]
        try:
            encoded = tokenizer(
                [source.text for source in batch_sources],
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=min(
                    512,
                    int(getattr(model.config, "max_position_embeddings", 512)),
                ),
            )
            encoded = {key: value.to(device) for key, value in encoded.items()}
            with torch.inference_mode():
                logits = model(**encoded).logits
                probabilities = torch.softmax(logits, dim=-1)
                scores, label_ids = probabilities.max(dim=-1)
            for source, label_id, score in zip(
                batch_sources,
                label_ids.cpu().tolist(),
                scores.cpu().tolist(),
                strict=True,
            ):
                label = id_to_label.get(label_id)
                if label is None:
                    continue
                predictions.append(
                    StructuredExtractionItem(
                        source_unit_id=source.source_unit_id,
                        item_kind="sentence_role",
                        category=label,
                        text=source.text,
                        evidence_quote=source.text,
                        confidence=float(score),
                        extractor="inlegalbert",
                    )
                )
        except Exception:  # noqa: BLE001 — keep the other case-analysis extractors available.
            logger.exception("InLegalBERT failed to classify a sentence batch")
    return predictions
