# Indian legal NER evaluation

The repository includes the KING Indian Court Decision Annotated Corpus: 50 manually annotated Supreme Court judgments with 1,062 exact entity spans, normalized at `backend/evaluation/data/normalized/king_ner_gold.jsonl`. Its published license is CC BY 4.0. The source paper describes ten coarse legal entity classes and 30 fine-grained classes. This is a useful public NER benchmark, but it is judgment-domain data; it does not provide advocate-reviewed labels for pleadings, affidavits, or the app's fact/issue/irrelevant sentence classes. Keep those as separate evaluation needs.

Source: [dataset on Figshare](https://doi.org/10.6084/m9.figshare.19719088.v4); [source paper and label definitions](https://ceur-ws.org/Vol-3257/paper9.pdf).

The legacy OpenNyAI `en_legal_ner_sm` runtime is retired. Its released wheel pins spaCy 3.2.x, requiring an unsupported Python 3.10 environment, and its KING exact-span F1 was only 0.165. The backend uses Python 3.12; do not enable `LEGAL_NER_ENABLED` or install the legacy model. A replacement must support Python 3.12 or 3.14 and be evaluated on target legal document types before advocate-facing use. The reported legacy benchmark remains for reproducibility only.

To evaluate on advocate-reviewed annotations, create UTF-8 JSONL with one object per sentence/page passage:

```json
{"text":"Section 138 of the Negotiable Instruments Act applies.","entities":[{"start":0,"end":10,"label":"PROVISION"}]}
```

Then run `python backend/evaluation/evaluate_legal_ner.py path/to/gold.jsonl`. Metrics use exact, end-exclusive character spans and report micro precision, recall, F1, and per-label scores. Keep a document-level holdout to avoid leakage between passages from the same judgment.

For the checked-in KING corpus, use `--label-map king-opennyai`. This explicit coarse crosswalk maps `JD` and `AUTH` to `JUDGE`; `HC`, `SC`, and `DC` to `COURT`; `PETR` to `PETITIONER`; `RES` to `RESPONDENT`; `DOJUD` to `DATE`; `STE` and `PLC` to `GPE`; and `ORG` to `ORG`. It scores only these 11 semantically reviewed KING tags. All other KING labels are excluded from the mapped score and reported in `gold_coverage` as unmapped; no equivalence is guessed for petition/document types, generic party labels, jurisdiction tags, or citation/section mentions. The court/location mapping intentionally collapses KING's distinctions to the coarser OpenNyAI output classes. This is a diagnostic cross-domain benchmark on judgments, not an advocate-pleading quality estimate.

Run from the project root after installing the isolated model:

```powershell
& backend\evaluation\install_legal_ner.ps1
& backend\.venv\Scripts\python.exe backend\evaluation\evaluate_legal_ner.py --label-map king-opennyai
```

The historical OpenNyAI `3.2.0` / spaCy `3.2.2` runtime scored **precision 0.133, recall 0.217, F1 0.165** (125 TP, 816 FP, 451 FN). The mapping covers 576 of 1,062 gold spans (54.2%); 486 labels are excluded as unmapped. Per-class figures are in the evaluator output. This weak, partial, cross-domain baseline is retained for reproducibility only; it must not be enabled as an advocate-facing quality signal or generalized to pleadings/affidavits.

The public KING gold set is present; no contact agreement is required for this corpus. OpenNyAI's separate InLegalNER page has its own access conditions, and this repository does not accept those conditions or package its annotations. No project-specific pleading/affidavit NER metrics or fact/issue/irrelevant accuracy have been measured. To validate advocate case-file performance, add a separately reviewed and consented corpus of the target document types and preserve a held-out set by case/document.

`synthetic_fact_issue_seed.jsonl` contains 24 balanced, synthetic pleading/affidavit-style examples for prompt development and schema smoke checks. They are invented examples, not excerpts from filed documents and not an evaluated gold set. The project still needs advocate-reviewed, consented examples from real target documents, adjudication guidance for ambiguous allegations versus issues, and a case-level holdout before training or claiming fact/issue/irrelevant accuracy. Do not mix these examples into the KING NER benchmark.
