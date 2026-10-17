# Indian legal sentence-role model

The local classifier uses law-ai/InLegalBERT as a frozen encoder and trains a
seven-label classification head on pooled sentence features from the Law-AI
Supreme Court sentence-role corpus. This CPU-friendly feature-extraction
approach avoids full-transformer backpropagation. It is a separate output from
Gemini's case-specific fact / issue / irrelevant sentence classification. The
public role corpus has no issue or case-specific relevance labels.

## Train and evaluate

Use Python 3.12 or another version supported by the selected PyTorch release.
For CPU-only Windows, run these commands from the repository root:

    python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
    python -m pip install -r backend/requirements-role-classifier.txt
    $env:HF_HOME = "$PWD\.runtime\huggingface"
    python backend/evaluation/train_sentence_roles.py

The script creates a document-disjoint train / validation / test split. It
computes frozen pooled features for each split, selects the number of head
training epochs using validation macro F1, evaluates the held-out judgments
once, compares against a majority-class baseline, then refits the deployable
head on train plus validation judgments. The encoder weights are unchanged.
The final model and reports stay in the ignored
.runtime/models/legal_sentence_roles/ directory.

Useful overrides include --max-epochs, --embedding-batch-size,
--head-batch-size, --max-length, --torch-threads, and --output-dir. For a
CPU-only run, use a moderate thread count (for example, --torch-threads 4) and
an embedding batch size of 32 or 64.

## Enable inference in the app

Install backend/requirements-role-classifier.txt in the backend's Python
environment. By default, the app loads the trained model from
.runtime/models/legal_sentence_roles/model/. Set
LEGAL_SENTENCE_ROLE_MODEL_PATH to use a different local model directory.
Inference is local-only; if the optional package or model is missing, the
existing Gemini / regex analysis continues without sentence-role items.

## Interpretation

The model covers rhetorical roles in English Supreme Court judgments. Its
confidence scores are raw softmax scores and are not calibrated probabilities.
It does not decide whether a sentence is relevant to an advocate's particular
case, establish a fact as true, or replace legal review. Metrics from 50
judgments are a limited baseline, not a production accuracy guarantee. The
encoder is not fine-tuned; using GPU-backed full-model fine-tuning would be a
separate, more resource-intensive training method.
