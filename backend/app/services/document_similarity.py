"""Local, conservative detection of near-duplicate extracted documents."""

import re
from collections import defaultdict
from uuid import UUID


MIN_TOKEN_COUNT = 80
MAX_SHINGLES_PER_DOCUMENT = 1_500
NEAR_DUPLICATE_THRESHOLD = 0.82


def _sampled_shingles(text: str) -> set[tuple[str, ...]]:
    tokens = re.findall(r"[\w]{2,}", text.casefold())
    if len(tokens) < MIN_TOKEN_COUNT:
        return set()
    shingles = [tuple(tokens[index : index + 5]) for index in range(len(tokens) - 4)]
    if len(shingles) > MAX_SHINGLES_PER_DOCUMENT:
        stride = len(shingles) / MAX_SHINGLES_PER_DOCUMENT
        shingles = [shingles[int(index * stride)] for index in range(MAX_SHINGLES_PER_DOCUMENT)]
    return set(shingles)


def find_near_duplicate_documents(
    documents: list[tuple[UUID, str, str]],
) -> dict[UUID, list[dict[str, object]]]:
    """Return likely duplicate pairs using sampled five-word shingle Jaccard.

    This is a review prompt only. It never merges, rejects, or deletes files.
    Text remains in process memory and no fingerprint is persisted.
    """
    signatures = {document_id: _sampled_shingles(text) for document_id, _name, text in documents}
    names = {document_id: filename for document_id, filename, _text in documents}
    matches: dict[UUID, list[dict[str, object]]] = defaultdict(list)
    active = [(document_id, signature) for document_id, signature in signatures.items() if signature]
    for index, (left_id, left) in enumerate(active):
        for right_id, right in active[index + 1 :]:
            union_size = len(left | right)
            if not union_size:
                continue
            similarity = len(left & right) / union_size
            if similarity < NEAR_DUPLICATE_THRESHOLD:
                continue
            matches[left_id].append({
                "document_id": right_id,
                "filename": names[right_id],
                "similarity": round(similarity, 3),
            })
            matches[right_id].append({
                "document_id": left_id,
                "filename": names[left_id],
                "similarity": round(similarity, 3),
            })
    return dict(matches)
