export type CaseRecord = {
  id: string;
  title: string;
  client_reference: string | null;
  court: string | null;
  jurisdiction: string | null;
  case_type: string | null;
  stage: string | null;
  case_number: string | null;
  next_hearing_date: string | null;
  analysis_status?: string | null;
  attention_count?: number;
  deadline_attention_count?: number;
  created_at: string;
  updated_at: string;
};

export type CaseChatCitation = {
  kind: "document" | "india_code";
  statement?: string | null;
  source_unit_id?: string | null;
  document_id?: string | null;
  source_start_char?: number | null;
  source_end_char?: number | null;
  filename?: string | null;
  locator?: string | null;
  page_number?: number | null;
  quote: string;
  title?: string | null;
  url?: string | null;
  citation?: string | null;
};

export type CaseChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: CaseChatCitation[];
  follow_up_questions: string[];
  retrieval_mode?: string | null;
  created_at: string;
};

export type CaseChatConversation = {
  id: string;
  case_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  messages?: CaseChatMessage[];
};

export type CaseDocument = {
  id: string;
  case_id: string;
  original_filename: string;
  content_type: string;
  file_extension: string;
  size_bytes: number;
  sha256: string;
  processing_status: string;
  extraction_error: string | null;
  description: string | null;
  document_type: string | null;
  text_unit_count: number;
  readable_location_count: number;
  unreadable_location_count: number;
  page_count: number;
  pages_with_text_count: number;
  pages_without_text_count: number;
  review_location_count: number;
  near_duplicate_matches: { document_id: string; filename: string; similarity: number }[];
  uploaded_at: string;
};

export type CaseDocumentSimilarity = { document_id: string; filename: string; similarity: number };

export type CaseDeadline = {
  id: string;
  case_id: string;
  title: string;
  due_date: string;
  note: string | null;
  status: "open" | "complete";
  created_at: string;
};

export type DocumentTextUnit = {
  id: string;
  document_id: string;
  unit_number: number;
  page_number: number | null;
  locator_label: string;
  text: string;
  character_count: number;
  extraction_method: string;
  ocr_confidence: number | null;
  ocr_needs_review: boolean;
  created_at: string;
};

export type CaseAnalysisAvailability = {
  ready: boolean;
  provider: string;
  model: string;
  message: string;
};

export type CaseAnalysisRun = {
  id: string;
  case_id: string;
  status: string;
  provider: string;
  model: string;
  retrieval_metadata: {
    method: "hybrid_semantic_lexical" | "lexical_fallback";
    status: string;
    facts_total: number;
    facts_eligible: number;
    facts_embedded: number;
    semantic_candidate_pairs: number;
    lexical_candidate_pairs: number;
    candidate_pairs_sent: number;
    max_lexical_neighbors_per_fact: number;
    max_semantic_neighbors_per_fact: number;
    max_facts_per_embedding_run: number;
    similarity_threshold: number;
    truncated: boolean;
    warning: string;
  } | null;
  document_count: number;
  text_unit_count: number;
  incomplete_sources_acknowledged: boolean;
  fact_count: number;
  finding_count: number;
  claim_review_count: number;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
};

export type CaseAnalysisFact = {
  id: string;
  fact_type: string;
  topic_key: string;
  statement: string;
  evidence_quote: string;
  normalized_value: string | null;
  confidence: number;
  effective_confidence: number;
  source_ocr_confidence: number | null;
  ocr_needs_review: boolean;
  source_text_unit_id: string;
  source_document_id: string;
  source_filename: string;
  source_locator: string;
  page_num: number | null;
  source_start_char: number | null;
  source_end_char: number | null;
};

export type CaseAnalysisFinding = {
  id: string;
  finding_type: string;
  relation_label: string | null;
  explanation: string;
  confidence: number;
  review_status: "confirmed_contradiction" | "possible_contradiction" | "not_a_contradiction" | "needs_review";
  review_note: string | null;
  left_fact: CaseAnalysisFact;
  right_fact: CaseAnalysisFact;
};

export type CaseAnalysisExtractionItem = {
  id: string;
  item_kind: "sentence" | "sentence_role" | "entity" | "legal_reference" | "date" | "amount";
  category: string;
  text: string;
  normalized_value: string | null;
  legal_role: string | null;
  evidence_quote: string;
  confidence: number;
  source_ocr_confidence: number | null;
  ocr_needs_review: boolean;
  extractor: "gemini" | "regex" | "spacy_legal" | "inlegalbert";
  source_text_unit_id: string;
  source_document_id: string;
  source_filename: string;
  source_locator: string;
  page_num: number | null;
  source_start_char: number | null;
  source_end_char: number | null;
};

export type CaseAnalysisResult = {
  run: CaseAnalysisRun;
  facts: CaseAnalysisFact[];
  extraction_items: CaseAnalysisExtractionItem[];
  findings: CaseAnalysisFinding[];
  claim_reviews: CaseClaimReview[];
  advocate_reviews: CaseAnalysisReview[];
};

export type CaseAnalysisReview = {
  id: string;
  target_kind: "fact" | "extraction_item" | "finding" | "claim_review";
  target_id: string;
  status: string;
  correction_text: string | null;
  correction_category: string | null;
  note: string | null;
  created_at: string;
};

export type CaseAnalysisChanges = {
  latest_run_at: string | null;
  previous_run_at: string | null;
  new_facts: { statement: string; filename: string; document_id: string; locator: string; page_num: number | null; quote: string }[];
  new_findings: { finding_type: string; explanation: string; review_status: string; left: { statement: string; filename: string; document_id: string; locator: string; quote: string }; right: { statement: string; filename: string; document_id: string; locator: string; quote: string } }[];
  resolved_findings: { finding_type: string; explanation: string; left_statement: string; right_statement: string }[];
  documents_since_previous_run: { id: string; filename: string; uploaded_at: string }[];
};

export type CaseSummaryRun = {
  id: string;
  case_id: string;
  status: string;
  provider: string;
  model: string;
  document_count: number;
  text_unit_count: number;
  incomplete_sources_acknowledged: boolean;
  point_count: number;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
};

export type CaseSummaryCitation = {
  source_document_id: string;
  source_filename: string;
  source_locator: string;
  evidence_quote: string;
};

export type CaseSummaryPoint = {
  text: string;
  citations: CaseSummaryCitation[];
};

export type CaseSummarySection = {
  section_key: string;
  title: string;
  points: CaseSummaryPoint[];
};

export type CaseSummaryResult = {
  run: CaseSummaryRun;
  narrative_summary: CaseSummaryPoint[];
  structured_summary: CaseSummarySection[];
};

export type CaseKnowledgeGraphRun = {
  id: string;
  case_id: string;
  analysis_run_id: string;
  status: string;
  provider: string;
  embedding_model: string;
  node_count: number;
  edge_count: number;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
};

export type CaseKnowledgeGraphNode = {
  node_id: string;
  node_type: "fact" | "issue" | "evidence" | "provision" | "party";
  text: string;
  label: string;
  category: string;
  evidence_quote: string;
  confidence: number;
  source_document_id: string;
  source_filename: string;
  source_text_unit_id: string;
  source_locator: string;
  page_num: number | null;
  source_start_char: number | null;
  source_end_char: number | null;
  ocr_confidence: number | null;
  ocr_needs_review: boolean;
};

export type CaseKnowledgeGraphEdge = {
  edge_id: string;
  source_id: string;
  target_id: string;
  relation: "supports" | "contradicts" | "applies_to" | "unrelated";
  explanation: string;
  confidence: number;
  source_kind: string;
};

export type CaseKnowledgeGraphResult = {
  run: CaseKnowledgeGraphRun;
  nodes: CaseKnowledgeGraphNode[];
  edges: CaseKnowledgeGraphEdge[];
  capabilities?: {
    semantic_embeddings?: "available" | "unavailable";
    graph_relationships?: "available";
    search_mode?: "hybrid" | "lexical_only";
  };
};

export type CaseKnowledgeGraphSearchContext = {
  relation: string;
  explanation: string;
  confidence: number;
  source_kind: string;
  source_node_id: string;
  related_node: CaseKnowledgeGraphNode;
};

export type CaseKnowledgeGraphSearchHit = {
  node: CaseKnowledgeGraphNode;
  score: number;
  semantic_score: number;
  lexical_score: number;
  related_context: CaseKnowledgeGraphSearchContext[];
};

export type CaseKnowledgeGraphSearchResult = {
  case_id: string;
  graph_run_id: string;
  query: string;
  results: CaseKnowledgeGraphSearchHit[];
  search_truncated: boolean;
};

export type CaseClaimReviewEvidence = { evidence_fact: CaseAnalysisFact };

export type CaseClaimReview = {
  id: string;
  claim_kind: "document" | "advocate";
  claim_text: string;
  support_status: "supported" | "partially_supported" | "unsupported";
  explanation: string;
  is_overstated: boolean;
  overstatement_reason: string | null;
  source_fact: CaseAnalysisFact | null;
  evidence: CaseClaimReviewEvidence[];
};

export type UploadRejection = { filename: string; reason: string };

export type UploadBatchResult = {
  uploaded: CaseDocument[];
  rejected: UploadRejection[];
};

export type LegalResearchProviderStatus = {
  provider: "india_code" | "indian_kanoon";
  enabled: boolean;
  configured: boolean;
  message: string;
};

export type LegalResearchResult = {
  provider: "india_code" | "indian_kanoon";
  title: string;
  url: string;
  snippet: string | null;
  citation: string | null;
  court: string | null;
  date: string | null;
  result_type: string | null;
  source_id: string | null;
};

export type LegalAuthorityReview = {
  provider: "india_code" | "indian_kanoon";
  source_id: string;
  title: string;
  url: string;
  status: "verified" | "needs_review" | "not_relevant";
  note: string | null;
  reviewed_at: string | null;
};

export type LegalResearchResponse = {
  query: string;
  results: LegalResearchResult[];
  providers: { provider: string; status: "ok" | "error" | "not_configured"; message: string; count: number }[];
  retrieved_at: string;
  notice: string;
};

export type LegalResearchSuggestion = {
  query: string; kind: string; evidence_quote: string; document: string; locator: string; confidence: number;
};
export type LegalResearchDocument = {
  provider: string; source_id: string; document: Record<string, unknown>; metadata: Record<string, unknown>;
  url: string; notice: string;
};
export type GroundedResearchAnswer = {
  answer: string; citations: { source_id: string; title: string; url: string; quote: string }[];
  sources_used: { source_id: string; title: string; url: string }[]; notice: string;
};

function apiBaseUrl(): string {
  if (process.env.NEXT_PUBLIC_API_BASE_URL) {
    return process.env.NEXT_PUBLIC_API_BASE_URL.replace(/\/$/, "");
  }
  if (typeof window !== "undefined") {
    return "/api/v1";
  }
  return "http://127.0.0.1:8000/api/v1";
}

export class ApiRequestError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBaseUrl()}${path}`, { credentials: "include", ...init });
  const contentType = response.headers.get("content-type") ?? "";
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    if (
      response.status === 401 &&
      typeof window !== "undefined" &&
      !path.startsWith("/auth/login") &&
      !path.startsWith("/auth/me")
    ) {
      window.dispatchEvent(new Event("legal-engine:auth-required"));
    }
    const detail = payload?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : typeof detail?.message === "string"
          ? `${detail.message}${Array.isArray(detail.documents) ? ` Documents: ${detail.documents.join(", ")}` : ""}`
        : detail?.rejected?.map((item: UploadRejection) => `${item.filename}: ${item.reason}`).join("\n") ||
          (contentType.includes("text/html")
            ? `The server returned an HTML error (HTTP ${response.status}). The response did not include a readable API error. Refresh the case documents before retrying an upload.`
            : `Request failed (${response.status}).`);
    throw new ApiRequestError(message, response.status);
  }
  return payload as T;
}

export type AdvocateSession = { email: string };
export type AuthSetupStatus = { configured: boolean; signup_available: boolean; mode: "single_advocate"; message: string };

export function getAuthSetupStatus(): Promise<AuthSetupStatus> {
  return request<AuthSetupStatus>("/auth/setup-status", { cache: "no-store" });
}

export function registerAdvocate(email: string, password: string): Promise<AdvocateSession> {
  return request<AdvocateSession>("/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
}

export function login(email: string, password: string): Promise<AdvocateSession> {
  return request<AdvocateSession>("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
}

export function getAdvocateSession(): Promise<AdvocateSession> {
  return request<AdvocateSession>("/auth/me", { cache: "no-store" });
}

export async function logout(): Promise<void> {
  await request<void>("/auth/logout", { method: "POST" });
}

export function listCases(): Promise<CaseRecord[]> {
  return request<CaseRecord[]>("/cases", { cache: "no-store" });
}

export function createCase(input: {
  title: string;
  client_reference?: string;
  court?: string;
  jurisdiction?: string;
  case_type?: string;
  stage?: string;
  case_number?: string;
  next_hearing_date?: string | null;
}): Promise<CaseRecord> {
  return request<CaseRecord>("/cases", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function getCase(caseId: string): Promise<CaseRecord> {
  return request<CaseRecord>(`/cases/${caseId}`, { cache: "no-store" });
}

export function listCaseDeadlines(caseId: string): Promise<CaseDeadline[]> {
  return request<CaseDeadline[]>(`/cases/${caseId}/deadlines`, { cache: "no-store" });
}

export function createCaseDeadline(caseId: string, input: { title: string; due_date: string; note?: string }): Promise<CaseDeadline> {
  return request<CaseDeadline>(`/cases/${caseId}/deadlines`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input),
  });
}

export function updateCaseDeadline(caseId: string, deadlineId: string, input: Partial<Pick<CaseDeadline, "title" | "due_date" | "note" | "status">>): Promise<CaseDeadline> {
  return request<CaseDeadline>(`/cases/${caseId}/deadlines/${deadlineId}`, {
    method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input),
  });
}

export function deleteCaseDeadline(caseId: string, deadlineId: string): Promise<void> {
  return request<void>(`/cases/${caseId}/deadlines/${deadlineId}`, { method: "DELETE" });
}

export function updateCase(
  caseId: string,
  input: Partial<Pick<CaseRecord, "title" | "client_reference" | "court" | "jurisdiction" | "case_type" | "stage" | "case_number" | "next_hearing_date">>,
): Promise<CaseRecord> {
  return request<CaseRecord>(`/cases/${caseId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function deleteCase(caseId: string): Promise<void> {
  return request<void>(`/cases/${caseId}`, { method: "DELETE" });
}

export function deleteDocument(caseId: string, documentId: string): Promise<void> {
  return request<void>(`/cases/${caseId}/documents/${documentId}`, { method: "DELETE" });
}

export function updateDocument(caseId: string, documentId: string, input: { description?: string | null; document_type?: string | null }): Promise<CaseDocument> {
  return request<CaseDocument>(`/cases/${caseId}/documents/${documentId}`, {
    method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input),
  });
}

export function replaceDocumentFile(caseId: string, documentId: string, file: File): Promise<CaseDocument> {
  const body = new FormData(); body.append("file", file);
  return request<CaseDocument>(`/cases/${caseId}/documents/${documentId}/file`, { method: "PUT", body });
}

export function saveAnalysisReview(caseId: string, runId: string, input: {
  target_kind: CaseAnalysisReview["target_kind"]; target_id: string; status: string;
  correction_text?: string | null; correction_category?: string | null; note?: string | null;
}): Promise<CaseAnalysisReview> {
  return request<CaseAnalysisReview>(`/cases/${caseId}/analysis/${runId}/reviews`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input),
  });
}

export function listDocuments(caseId: string): Promise<CaseDocument[]> {
  return request<CaseDocument[]>(`/cases/${caseId}/documents`, { cache: "no-store" });
}

export function findNearDuplicateDocuments(caseId: string): Promise<Record<string, CaseDocumentSimilarity[]>> {
  return request<Record<string, CaseDocumentSimilarity[]>>(`/cases/${caseId}/documents/near-duplicates`, { cache: "no-store" });
}

export function getDocumentText(caseId: string, documentId: string): Promise<DocumentTextUnit[]> {
  return request<DocumentTextUnit[]>(`/cases/${caseId}/documents/${documentId}/text`, { cache: "no-store" });
}

export function retryDocumentExtraction(caseId: string, documentId: string): Promise<CaseDocument> {
  return request<CaseDocument>(`/cases/${caseId}/documents/${documentId}/extract`, { method: "POST" });
}

export function getAnalysisAvailability(caseId: string): Promise<CaseAnalysisAvailability> {
  return request<CaseAnalysisAvailability>(`/cases/${caseId}/analysis/config`, { cache: "no-store" });
}

export function startCaseAnalysis(caseId: string, advocateClaims: string[] = [], acknowledgeIncompleteSources = false): Promise<CaseAnalysisRun> {
  return request<CaseAnalysisRun>(`/cases/${caseId}/analysis`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ advocate_claims: advocateClaims, acknowledge_incomplete_sources: acknowledgeIncompleteSources }),
  });
}

export function getLatestCaseAnalysis(caseId: string): Promise<CaseAnalysisResult> {
  return request<CaseAnalysisResult>(`/cases/${caseId}/analysis/latest`, { cache: "no-store" });
}

export function getCaseAnalysisChanges(caseId: string): Promise<CaseAnalysisChanges> {
  return request<CaseAnalysisChanges>(`/cases/${caseId}/analysis/changes`, { cache: "no-store" });
}

export function startCaseSummary(caseId: string, acknowledgeIncompleteSources = false): Promise<CaseSummaryRun> {
  return request<CaseSummaryRun>(`/cases/${caseId}/summary`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ acknowledge_incomplete_sources: acknowledgeIncompleteSources }),
  });
}

export function getLatestCaseSummary(caseId: string): Promise<CaseSummaryResult> {
  return request<CaseSummaryResult>(`/cases/${caseId}/summary/latest`, { cache: "no-store" });
}

export function startCaseKnowledgeGraph(caseId: string): Promise<CaseKnowledgeGraphRun> {
  return request<CaseKnowledgeGraphRun>(`/cases/${caseId}/knowledge-graph`, { method: "POST" });
}

export function getLatestCaseKnowledgeGraph(caseId: string): Promise<CaseKnowledgeGraphResult> {
  return request<CaseKnowledgeGraphResult>(`/cases/${caseId}/knowledge-graph/latest`, { cache: "no-store" });
}

export function searchCaseKnowledgeGraph(
  caseId: string,
  query: string,
  topK = 8,
): Promise<CaseKnowledgeGraphSearchResult> {
  return request<CaseKnowledgeGraphSearchResult>(`/cases/${caseId}/knowledge-graph/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, top_k: topK }),
  });
}

export function getLegalResearchConfiguration(caseId: string): Promise<{ providers: LegalResearchProviderStatus[] }> {
  return request(`/cases/${caseId}/legal-research/config`, { cache: "no-store" });
}

export function listAuthorityReviews(caseId: string): Promise<LegalAuthorityReview[]> {
  return request(`/cases/${caseId}/legal-research/authority-reviews`, { cache: "no-store" });
}

export function saveAuthorityReview(caseId: string, review: Pick<LegalAuthorityReview, "provider" | "source_id" | "title" | "url" | "status" | "note">): Promise<LegalAuthorityReview> {
  return request<LegalAuthorityReview>(`/cases/${caseId}/legal-research/authority-reviews`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(review),
  });
}

export function listCaseChatConversations(caseId: string): Promise<CaseChatConversation[]> {
  return request(`/cases/${caseId}/chat/conversations`, { cache: "no-store" });
}

export function createCaseChatConversation(caseId: string): Promise<CaseChatConversation> {
  return request(`/cases/${caseId}/chat/conversations`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({}),
  });
}

export function renameCaseChatConversation(caseId: string, conversationId: string, title: string): Promise<CaseChatConversation> {
  return request<CaseChatConversation>(`/cases/${caseId}/chat/conversations/${conversationId}`, {
    method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title }),
  });
}

export function deleteCaseChatConversation(caseId: string, conversationId: string): Promise<void> {
  return request<void>(`/cases/${caseId}/chat/conversations/${conversationId}`, { method: "DELETE" });
}

export function getCaseChatConversation(caseId: string, conversationId: string): Promise<CaseChatConversation> {
  return request<CaseChatConversation>(`/cases/${caseId}/chat/conversations/${conversationId}`, { cache: "no-store" });
}

export function sendCaseChatMessage(caseId: string, conversationId: string, input: {
  content: string; include_india_code: boolean; acknowledge_incomplete_sources: boolean;
}): Promise<CaseChatConversation> {
  return request(`/cases/${caseId}/chat/conversations/${conversationId}/messages`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input),
  });
}

export function searchLegalAuthorities(caseId: string, query: string, options: {
  limit?: number; page?: number; court?: string; from_date?: string; to_date?: string;
  act?: string; section?: string; precedential?: boolean;
} = {}): Promise<LegalResearchResponse> {
  return request(`/cases/${caseId}/legal-research/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, ...options }),
  });
}

export function getLegalResearchSuggestions(caseId: string): Promise<{ suggestions: LegalResearchSuggestion[]; message: string }> {
  return request(`/cases/${caseId}/legal-research/suggestions`, { cache: "no-store" });
}

export function getIndianKanoonDocument(caseId: string, sourceId: string): Promise<LegalResearchDocument> {
  return request(`/cases/${caseId}/legal-research/indian-kanoon/${encodeURIComponent(sourceId)}`, { cache: "no-store" });
}

export function getIndianKanoonFragment(caseId: string, sourceId: string, query: string): Promise<Record<string, unknown>> {
  const params = new URLSearchParams({ query });
  return request(`/cases/${caseId}/legal-research/indian-kanoon/${encodeURIComponent(sourceId)}/fragment?${params.toString()}`, { cache: "no-store" });
}

export function getIndiaCodeSection(caseId: string, act: string, section: string): Promise<Record<string, unknown>> {
  return request(`/cases/${caseId}/legal-research/india-code/section/${encodeURIComponent(act)}/${encodeURIComponent(section)}`, { cache: "no-store" });
}

export function getIndiaCodeMappings(caseId: string, act: string, section?: string): Promise<Record<string, unknown>> {
  const params = new URLSearchParams({ from_act: act });
  if (section) params.set("section", section);
  return request(`/cases/${caseId}/legal-research/india-code/mappings?${params.toString()}`, { cache: "no-store" });
}

export function createGroundedResearchAnswer(caseId: string, query: string, sourceIds: string[]): Promise<GroundedResearchAnswer> {
  return request(`/cases/${caseId}/legal-research/answer`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, source_ids: sourceIds }),
  });
}

export function uploadDocuments(caseId: string, files: File[]): Promise<UploadBatchResult> {
  const formData = new FormData();
  files.forEach((file) => formData.append("files", file));
  return request<UploadBatchResult>(`/cases/${caseId}/documents`, {
    method: "POST",
    body: formData,
  });
}

export function formatFileSize(sizeBytes: number): string {
  if (sizeBytes < 1024 * 1024) return `${Math.max(1, Math.round(sizeBytes / 1024))} KB`;
  return `${(sizeBytes / (1024 * 1024)).toFixed(1)} MB`;
}
