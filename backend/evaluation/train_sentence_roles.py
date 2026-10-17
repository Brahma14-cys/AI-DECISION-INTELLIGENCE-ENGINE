"""Train and evaluate an InLegalBERT sentence-role classifier.

The CPU-friendly default freezes InLegalBERT, caches pooled sentence features,
and trains only the seven-label classification head. The split is made by
judgment (doc_id), never by sentence. The held-out test judgments are evaluated
once; the production head is then refit on train plus validation judgments.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import random
import time
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA = ROOT / "backend" / "evaluation" / "data" / "normalized" / "supreme_court_sentence_roles.jsonl"
DEFAULT_OUTPUT = ROOT / ".runtime" / "models" / "legal_sentence_roles"
BASE_MODEL = "law-ai/InLegalBERT"
LABELS = [
    "argument",
    "fact",
    "precedent",
    "ratio_decidendi",
    "ruling_lower_court",
    "ruling_present_court",
    "statute",
]
LABEL_BY_SOURCE = {
    "Argument": "argument",
    "Facts": "fact",
    "Precedent": "precedent",
    "Ratio of the decision": "ratio_decidendi",
    "Ruling by Lower Court": "ruling_lower_court",
    "Ruling by Present Court": "ruling_present_court",
    "Statute": "statute",
}


def _load_rows(path: Path) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    normalized = []
    for row in rows:
        label = LABEL_BY_SOURCE.get(row.get("label"))
        text = str(row.get("text", "")).strip()
        doc_id = str(row.get("doc_id", "")).strip()
        if label and text and doc_id:
            normalized.append({**row, "text": text, "doc_id": doc_id, "label_name": label})
    if not normalized:
        raise ValueError(f"No valid labeled records found in {path}")
    return normalized


def _split_by_document(rows, seed: int, np_module):
    """Find deterministic, group-disjoint train/validation/test sets with all labels."""
    from sklearn.model_selection import StratifiedGroupKFold

    y = np_module.asarray([row["label_name"] for row in rows])
    groups = np_module.asarray([row["doc_id"] for row in rows])
    all_indices = np_module.arange(len(rows))
    outer = None
    for attempt_seed in range(seed, seed + 100):
        splitter = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=attempt_seed)
        train_val_indices, test_indices = next(splitter.split(all_indices, y, groups))
        if set(y[test_indices]) == set(LABELS) and set(y[train_val_indices]) == set(LABELS):
            outer = (train_val_indices, test_indices, attempt_seed)
            break
    if outer is None:
        raise ValueError("Could not form a document-disjoint test split containing all seven labels.")

    train_val_indices, test_indices, outer_seed = outer
    inner = None
    for attempt_seed in range(seed + 100, seed + 200):
        splitter = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=attempt_seed)
        relative_train_indices, relative_validation_indices = next(
            splitter.split(train_val_indices, y[train_val_indices], groups[train_val_indices])
        )
        train_indices = train_val_indices[relative_train_indices]
        validation_indices = train_val_indices[relative_validation_indices]
        if (
            set(y[train_indices]) == set(LABELS)
            and set(y[validation_indices]) == set(LABELS)
            and len(set(groups[train_indices]) & set(groups[validation_indices])) == 0
        ):
            inner = (train_indices, validation_indices, attempt_seed)
            break
    if inner is None:
        raise ValueError("Could not form document-disjoint train/validation splits containing all labels.")

    train_indices, validation_indices, inner_seed = inner
    split = {
        "train": train_indices.tolist(),
        "validation": validation_indices.tolist(),
        "test": test_indices.tolist(),
        "train_doc_ids": sorted(set(groups[train_indices].tolist())),
        "validation_doc_ids": sorted(set(groups[validation_indices].tolist())),
        "test_doc_ids": sorted(set(groups[test_indices].tolist())),
        "outer_seed": outer_seed,
        "inner_seed": inner_seed,
    }
    if set(split["train_doc_ids"]) & set(split["validation_doc_ids"]):
        raise AssertionError("Judgment leakage between train and validation.")
    if set(split["train_doc_ids"]) & set(split["test_doc_ids"]):
        raise AssertionError("Judgment leakage between train and test.")
    if set(split["validation_doc_ids"]) & set(split["test_doc_ids"]):
        raise AssertionError("Judgment leakage between validation and test.")
    return split


def _score(y_true, y_pred, labels, sklearn_metrics):
    precision, recall, f1, support = sklearn_metrics.precision_recall_fscore_support(
        y_true, y_pred, labels=labels, zero_division=0
    )
    return {
        "accuracy": float(sklearn_metrics.accuracy_score(y_true, y_pred)),
        "macro_f1": float(sklearn_metrics.f1_score(y_true, y_pred, labels=labels, average="macro", zero_division=0)),
        "weighted_f1": float(sklearn_metrics.f1_score(y_true, y_pred, labels=labels, average="weighted", zero_division=0)),
        "per_label": {
            label: {
                "precision": float(precision[index]),
                "recall": float(recall[index]),
                "f1": float(f1[index]),
                "support": int(support[index]),
            }
            for index, label in enumerate(labels)
        },
        "confusion_matrix": sklearn_metrics.confusion_matrix(y_true, y_pred, labels=labels).tolist(),
    }


def _set_seed(seed: int, torch_module, np_module) -> None:
    random.seed(seed)
    np_module.random.seed(seed)
    torch_module.manual_seed(seed)
    if torch_module.cuda.is_available():
        torch_module.cuda.manual_seed_all(seed)


def _make_dataset(rows, tokenizer, max_length, torch_module):
    class SentenceDataset(torch_module.utils.data.Dataset):
        def __init__(self, records):
            self.records = records
            self.encodings = tokenizer(
                [row["text"] for row in records],
                truncation=True,
                max_length=max_length,
            )
            self.labels = torch_module.tensor([LABELS.index(row["label_name"]) for row in records], dtype=torch_module.long)

        def __len__(self):
            return len(self.records)

        def __getitem__(self, index):
            item = {key: value[index] for key, value in self.encodings.items()}
            item["labels"] = self.labels[index]
            return item

    return SentenceDataset(rows)


def _collate_batch(batch, tokenizer, torch_module):
    labels = torch_module.stack([item.pop("labels") for item in batch])
    padded = tokenizer.pad(batch, padding=True, return_tensors="pt")
    padded["labels"] = labels
    return padded


def _new_model(checkpoint, local_files_only, num_labels, AutoModelForSequenceClassification):
    return AutoModelForSequenceClassification.from_pretrained(
        checkpoint,
        num_labels=num_labels,
        id2label={index: label for index, label in enumerate(LABELS)},
        label2id={label: index for index, label in enumerate(LABELS)},
        local_files_only=local_files_only,
    )


def _encode_features(rows, tokenizer, model, args, torch_module, *, split_name: str):
    """Compute frozen encoder representations once so head training is cheap."""
    dataset = _make_dataset(rows, tokenizer, args.max_length, torch_module)
    loader = torch_module.utils.data.DataLoader(
        dataset,
        batch_size=args.embedding_batch_size,
        shuffle=False,
        num_workers=0,
        collate_fn=lambda batch: _collate_batch(batch, tokenizer, torch_module),
    )
    model.eval()
    features, labels = [], []
    with torch_module.inference_mode():
        for step, batch in enumerate(loader, 1):
            batch_labels = batch.pop("labels")
            inputs = {key: value.to(args.device) for key, value in batch.items()}
            outputs = model.base_model(**inputs)
            pooled = getattr(outputs, "pooler_output", None)
            if pooled is None:
                raise RuntimeError("The selected InLegalBERT base model has no pooled sentence representation.")
            features.append(pooled.cpu())
            labels.append(batch_labels.cpu())
            if step % max(1, len(loader) // 10) == 0 or step == len(loader):
                print(json.dumps({
                    "stage": "feature_progress",
                    "split": split_name,
                    "step": step,
                    "steps": len(loader),
                }), flush=True)
    return torch_module.cat(features), torch_module.cat(labels)


def _fit_classifier_head(
    classifier,
    features,
    labels,
    validation_features,
    validation_labels,
    args,
    torch_module,
    sklearn_metrics,
    *,
    max_epochs: int,
    save_to: Path | None = None,
):
    """Train only the linear classification head against cached features."""
    dataset = torch_module.utils.data.TensorDataset(features, labels)
    generator = torch_module.Generator().manual_seed(args.seed)
    loader = torch_module.utils.data.DataLoader(
        dataset,
        batch_size=args.head_batch_size,
        shuffle=True,
        generator=generator,
    )
    counts = Counter(labels.tolist())
    class_weights = torch_module.tensor(
        [np.sqrt(len(labels) / max(1, counts.get(index, 0))) for index in range(len(LABELS))],
        dtype=torch_module.float,
    )
    class_weights = class_weights / class_weights.mean()
    optimizer = torch_module.optim.AdamW(
        classifier.parameters(), lr=args.head_learning_rate, weight_decay=args.weight_decay
    )
    best_f1 = -1.0
    best_epoch = max_epochs
    best_state = None
    history = []

    for epoch in range(1, max_epochs + 1):
        classifier.train()
        total_loss = 0.0
        for batch_features, batch_labels in loader:
            logits = classifier(batch_features)
            loss = torch_module.nn.functional.cross_entropy(logits, batch_labels, weight=class_weights)
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
            total_loss += float(loss.detach())

        record = {"epoch": epoch, "train_loss": total_loss / max(1, len(loader))}
        if validation_features is not None and validation_labels is not None:
            classifier.eval()
            with torch_module.inference_mode():
                predictions = classifier(validation_features).argmax(dim=-1).tolist()
            truth = validation_labels.tolist()
            score = _score(
                [LABELS[index] for index in truth],
                [LABELS[index] for index in predictions],
                LABELS,
                sklearn_metrics,
            )
            record["validation"] = score
            if score["macro_f1"] > best_f1:
                best_f1 = score["macro_f1"]
                best_epoch = epoch
                best_state = {key: value.detach().clone() for key, value in classifier.state_dict().items()}
        history.append(record)
        print(json.dumps({"stage": "head_train", **record}), flush=True)

    if best_state is not None:
        classifier.load_state_dict(best_state)
    if save_to is not None:
        save_to.parent.mkdir(parents=True, exist_ok=True)
        torch_module.save(classifier.state_dict(), save_to)
    return best_epoch, history


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--base-model", default=BASE_MODEL)
    parser.add_argument("--local-files-only", action="store_true")
    parser.add_argument("--max-length", type=int, default=128)
    parser.add_argument("--embedding-batch-size", type=int, default=64)
    parser.add_argument("--head-batch-size", type=int, default=512)
    parser.add_argument("--max-epochs", type=int, default=3)
    parser.add_argument("--torch-threads", type=int, default=4)
    parser.add_argument("--head-learning-rate", type=float, default=0.01)
    parser.add_argument("--weight-decay", type=float, default=0.01)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if not args.data.is_file():
        raise FileNotFoundError(f"Training data not found: {args.data}")

    import torch
    from sklearn import metrics as sklearn_metrics
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    torch.set_num_threads(max(1, args.torch_threads))
    np.random.seed(args.seed)
    _set_seed(args.seed, torch, np)
    rows = _load_rows(args.data)
    split = _split_by_document(rows, args.seed, np)
    data = {
        name: [rows[index] for index in split[name]]
        for name in ("train", "validation", "test")
    }
    tokenizer = AutoTokenizer.from_pretrained(args.base_model, local_files_only=args.local_files_only)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "split.json").write_text(json.dumps({
        "train_doc_ids": split["train_doc_ids"],
        "validation_doc_ids": split["validation_doc_ids"],
        "test_doc_ids": split["test_doc_ids"],
        "outer_seed": split["outer_seed"],
        "inner_seed": split["inner_seed"],
        "row_counts": {name: len(data[name]) for name in data},
        "label_counts": {name: dict(Counter(row["label_name"] for row in data[name])) for name in data},
    }, indent=2), encoding="utf-8")

    print(json.dumps({
        "stage": "start",
        "base_model": args.base_model,
        "device": "cuda" if torch.cuda.is_available() else "cpu",
        "cuda_device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "data_rows": len(rows),
        "documents": len(set(row["doc_id"] for row in rows)),
        "split_docs": {name: len(split[f"{name}_doc_ids"]) for name in ("train", "validation", "test")},
        "split_rows": {name: len(data[name]) for name in data},
        "labels": LABELS,
    }, indent=2), flush=True)

    started = time.time()
    eval_model = _new_model(args.base_model, args.local_files_only, len(LABELS), AutoModelForSequenceClassification)
    args.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    eval_model.to(args.device)
    eval_model.classifier.cpu()
    eval_features = {
        name: _encode_features(data[name], tokenizer, eval_model, args, torch, split_name=name)
        for name in ("train", "validation", "test")
    }
    best_epoch, history = _fit_classifier_head(
        eval_model.classifier,
        *eval_features["train"],
        *eval_features["validation"],
        args,
        torch,
        sklearn_metrics,
        max_epochs=args.max_epochs,
        save_to=args.output_dir / "evaluation_classifier_head.pt",
    )

    eval_model.eval()
    with torch.inference_mode():
        y_pred = eval_model.classifier(eval_features["test"][0]).argmax(dim=-1).tolist()
    y_true = eval_features["test"][1].tolist()
    test_scores = _score(
        [LABELS[index] for index in y_true],
        [LABELS[index] for index in y_pred],
        LABELS,
        sklearn_metrics,
    )
    majority_label = Counter(row["label_name"] for row in data["train"]).most_common(1)[0][0]
    majority_predictions = [majority_label] * len(data["test"])
    majority_truth = [row["label_name"] for row in data["test"]]
    majority_baseline = _score(majority_truth, majority_predictions, LABELS, sklearn_metrics)

    # Refit the deployment head on train + validation after the held-out test
    # set is scored, using the validation-selected epoch count.
    model_dir = args.output_dir / "model"
    model_dir.mkdir(parents=True, exist_ok=True)
    deploy_model = _new_model(args.base_model, args.local_files_only, len(LABELS), AutoModelForSequenceClassification)
    deploy_model.to(args.device)
    deploy_model.classifier.cpu()
    deploy_model.base_model.eval()
    for parameter in deploy_model.base_model.parameters():
        parameter.requires_grad_(False)
    deploy_features = torch.cat([eval_features["train"][0], eval_features["validation"][0]])
    deploy_labels = torch.cat([eval_features["train"][1], eval_features["validation"][1]])
    _fit_classifier_head(
        deploy_model.classifier,
        deploy_features,
        deploy_labels,
        None,
        None,
        args,
        torch,
        sklearn_metrics,
        max_epochs=best_epoch,
    )
    deploy_model.save_pretrained(model_dir, safe_serialization=True)
    tokenizer.save_pretrained(model_dir)
    (model_dir / "label_map.json").write_text(json.dumps({
        "id2label": {str(index): label for index, label in enumerate(LABELS)},
        "label2id": {label: index for index, label in enumerate(LABELS)},
    }, indent=2), encoding="utf-8")

    report = {
        "model": args.base_model,
        "training_method": "frozen InLegalBERT encoder with a trained linear classification head",
        "encoder_frozen": True,
        "task": "Indian legal rhetorical sentence role classification",
        "labels": LABELS,
        "training_rows": len(data["train"]),
        "training_documents": len(split["train_doc_ids"]),
        "validation_rows": len(data["validation"]),
        "validation_documents": len(split["validation_doc_ids"]),
        "deployment_training_rows": len(data["train"]) + len(data["validation"]),
        "deployment_training_documents": len(split["train_doc_ids"]) + len(split["validation_doc_ids"]),
        "held_out_test_rows": len(data["test"]),
        "held_out_test_documents": len(split["test_doc_ids"]),
        "max_length": args.max_length,
        "selected_epochs": best_epoch,
        "selection_metric": "validation macro F1",
        "test_metrics": test_scores,
        "majority_class_test_baseline": majority_baseline,
        "validation_history": history,
        "split": "document-disjoint; test split was evaluated once",
        "device": str(args.device),
        "elapsed_seconds": round(time.time() - started, 2),
        "limitations": [
            "Only 50 Supreme Court judgments are available; results have high sampling uncertainty.",
            "Labels represent rhetorical roles in judgments, not case-specific relevance or the existing fact/issue/irrelevant taxonomy.",
            "The saved model is fit on training documents; validation selected its epoch and the test documents remain held out.",
        ],
    }
    (args.output_dir / "metrics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"stage": "complete", "best_epoch": best_epoch, "test_metrics": test_scores, "majority_baseline": majority_baseline, "model_dir": str(model_dir), "metrics": str(args.output_dir / "metrics.json")}, indent=2), flush=True)


if __name__ == "__main__":
    main()
