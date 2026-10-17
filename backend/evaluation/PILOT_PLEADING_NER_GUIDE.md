# Pleading and affidavit NER pilot

## What this pilot is for

This pack helps an advocate annotate entity mentions in English pleadings and affidavits so a future legal NER replacement can be measured on those document types. The current OpenNyAI runtime is retired and disabled. The pilot template is empty. `pilot_pleading_ner_example.jsonl` is a single **synthetic format example only**; do not mix it into the advocate gold set, training data, or reported scores.

This is named-entity annotation, not sentence classification. Do not assign fact / issue / irrelevant labels here.

## Gather pilot passages

1. Use text extracted by the app from representative pleadings and affidavits. Include more than one document type (for example, petition/plaint, written statement, affidavit, counter-affidavit) where available.
2. Start with about 100–200 passages across roughly 10–20 documents. A passage can be one sentence or a short paragraph if context is needed to identify a party's role. Include some passages with no target entities.
3. Keep `text` exactly as extracted, including capitalization and punctuation. Record the document type, anonymized document ID, page number, and passage ID so each annotation can be traced back for review.
4. If using real case material, follow the advocate's and project owner's data-handling rules. Use anonymized IDs in the annotation sheet; do not add client names or other private details to notes.

## How to annotate the CSV

Open `pilot_pleading_ner_annotation_template.csv` in Excel or another spreadsheet editor. The file is a blank template row; duplicate a row for each entity mention and repeat the passage metadata and exact passage text on each row.

- Enter the exact entity mention in `entity_text`.
- Use one label from the list below in `label`.
- If the passage contains the same exact mention more than once, put its 1-based appearance number in `occurrence_number` (first occurrence = 1). Otherwise use 1.
- For a passage with no target entities, add one row with `label` set to `NONE` and leave `entity_text` empty.
- Use `annotator_notes` only for genuine ambiguity, such as whether a party name is the petitioner or respondent. The advocate should resolve the label using the case context before the pilot is treated as gold data.

### Labels

Use these exact labels for the intended entity schema. They do not mean the retired OpenNyAI model is currently integrated or enabled:

| Label | Mark this text |
|---|---|
| `PETITIONER` | Exact name of a petitioner/appellant party in this case |
| `RESPONDENT` | Exact name of a respondent party in this case |
| `OTHER_PERSON` | Named person not better covered by another role |
| `JUDGE` | Judge's name |
| `LAWYER` | Advocate/counsel's name |
| `WITNESS` | Witness's name or clearly identified witness person |
| `COURT` | Name of a court or tribunal |
| `ORG` | Named organization, department, company, or institution that is not a court |
| `GPE` | Geographic place, state, country, or city |
| `DATE` | Date mention |
| `STATUTE` | Name of an Act, Code, or other statute |
| `PROVISION` | Section, article, rule, regulation, or schedule reference |
| `PRECEDENT` | Name of a cited prior case |
| `CASE_NUMBER` | Case number or docket identifier |

Do not label monetary amounts in this pilot: the current NER model has no `AMOUNT` class. Amount extraction is handled separately by the project's extraction rules/Gemini path.

Label the mention exactly as written. For example, if the text says `Section 138`, annotate that exact phrase as `PROVISION`; do not expand it to a full statute name unless the statute is also written in the passage. A party can only be labeled petitioner or respondent when the role is clear from the case context.

## Convert and evaluate

After annotation, save a copy as CSV/UTF-8 (comma-separated). From the project root run:

```powershell
& backend\.venv\Scripts\python.exe backend\evaluation\prepare_pleading_ner_gold.py `
  backend\evaluation\pilot_pleading_ner_annotation_template.csv `
  backend\evaluation\data\pilot\pleading_affidavit_ner_gold.jsonl
```

The converter checks labels, finds each exact mention in its passage, computes zero-based/end-exclusive offsets, and writes one JSONL record per passage. Check the converted JSONL before using it. After a Python 3.12/3.14-compatible replacement legal NER runtime is implemented and validated, evaluate with:

```powershell
& backend\.venv\Scripts\python.exe backend\evaluation\evaluate_legal_ner.py `
  backend\evaluation\data\pilot\pleading_affidavit_ner_gold.jsonl
```

Keep all passages from a given document/case in the same evaluation split. The pilot is a first diagnostic, not enough by itself to claim production accuracy or fine-tune a reliable model. Reserve complete documents for a held-out evaluation set, and never mix the synthetic example into that set.
