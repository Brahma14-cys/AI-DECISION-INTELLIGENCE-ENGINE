/**
 * Data presentation, humanisation and legal citation normalisation utilities
 */

/**
 * Converts snake_case or raw identifier strings into clean sentence case.
 * Example: 'final_hearing_date' -> 'Final hearing date'
 * Example: 'statute_section' -> 'Statute section'
 */
export function formatLabel(str: string | null | undefined): string {
  if (!str) return "";
  const cleaned = str
    .replace(/[_-]+/g, " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .trim();
  if (!cleaned) return "";
  return cleaned.charAt(0).toUpperCase() + cleaned.slice(1).toLowerCase();
}

/**
 * Canonicalizes legal authority queries, case citations, and section mentions.
 * Standardizes common Indian citation formats (e.g. O.S. No., Section, AIR, SCC, etc.)
 */
export function canonicalizeAuthority(str: string | null | undefined): string {
  if (!str) return "";
  let s = str.trim();

  // Normalize spaces around punctuation
  s = s.replace(/\s+/g, " ");

  // Normalize "O.S. No." variations: O.S.No.537/1983, OS 537 of 1983, O.S.No. 537 of 1983
  s = s.replace(/\bO\.?S\.?\s*(?:No\.?)?\s*(\d+)\s*(?:\/|\s*of\s*)(\d{4})\b/gi, "O.S. No. $1 of $2");

  // Normalize "W.P. No."
  s = s.replace(/\bW\.?P\.?\s*(?:No\.?)?\s*(\d+)\s*(?:\/|\s*of\s*)(\d{4})\b/gi, "W.P. No. $1 of $2");

  // Normalize "C.A. No." / "Civil Appeal No."
  s = s.replace(/\b(?:C\.?A\.?|Civil\s+Appeal)\s*(?:No\.?)?\s*(\d+)\s*(?:\/|\s*of\s*)(\d{4})\b/gi, "Civil Appeal No. $1 of $2");

  // Normalize "S.L.P. (C) No." / "SLP"
  s = s.replace(/\bS\.?L\.?P\.?\s*(?:\(C\))?\s*(?:No\.?)?\s*(\d+)\s*(?:\/|\s*of\s*)(\d{4})\b/gi, "SLP (C) No. $1 of $2");

  // Normalize "Section 113, Act" vs "Sec. 113" vs "Sec 113"
  s = s.replace(/\bSec(?:tion|\.)?\s*(\d+[A-Za-z]*)\b/gi, "Section $1");

  // Normalize "Article 226"
  s = s.replace(/\bArt(?:icle|\.)?\s*(\d+[A-Za-z]*)\b/gi, "Article $1");

  // Normalize "Order 39 Rule 1"
  s = s.replace(/\bOrder\s*(\d+[A-Za-z]*)\s*Rule\s*(\d+[A-Za-z]*)\b/gi, "Order $1, Rule $2");

  return s;
}

/**
 * Validates if an extracted suggestion or text passage is a genuine legal authority
 * (statute, section, rule, article, or judicial case number) and not a question/heading/fragment.
 */
export function isValidLegalReference(str: string | null | undefined): boolean {
  if (!str) return false;
  const s = str.trim();
  if (s.length < 3 || s.length > 180) return false;

  // Filter out question / sentence fragments / generic headings
  if (/\?$/.test(s)) return false;
  if (/^(?:to\s+what\s+relief|issues?\s+no\.?|point\s+for\s+consideration|whether\s+|in\s+the\s+result)/i.test(s)) {
    return false;
  }
  if (/^(?:at\s+this\s+stage|per\s+contra|further,?\s+it\s+is|it\s+is\s+the\s+contention)/i.test(s)) {
    return false;
  }

  // Check for strong statutory or case reference patterns
  const patterns = [
    /\b(?:section|sec\.?|article|art\.?|order|rule|schedule|clause)\s+\d+/i,
    /\b(?:act|code|rules|regulations|adhiniyam|sanhita)\b/i,
    /\b(?:o\.?s\.?|w\.?p\.?|s\.?l\.?p\.?|c\.?a\.?|c\.?r\.?p\.?|m\.?a\.?c\.?t\.?|c\.?s\.?(?:\s*\(comm\))?)\s*(?:no\.?)?\s*\d+/i,
    /\b(?:19|20)\d{2}\s+(?:scc|air|scr|scale|ald|altc|bom\s+cr|del)\b/i,
    /\bv(?:s|\.)\b/i, // Adversarial citation e.g. Party v. Party
  ];

  return patterns.some((p) => p.test(s));
}

/**
 * Formats a currency number in the Indian numbering system: ₹1,25,000
 */
export function formatCurrency(amount: number | null | undefined): string {
  if (amount == null || isNaN(amount)) return "";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(amount);
}

/**
 * Formats a date string into Indian legal style: '07 Oct 2026' or dense '7 Oct'
 */
export function formatDate(dateStr: string | Date | null | undefined, dense: boolean = false): string {
  if (!dateStr) return "";
  const d = typeof dateStr === "string" ? new Date(dateStr) : dateStr;
  if (isNaN(d.getTime())) return "";

  if (dense) {
    return d.toLocaleDateString("en-IN", {
      day: "numeric",
      month: "short",
    });
  }

  return d.toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}
