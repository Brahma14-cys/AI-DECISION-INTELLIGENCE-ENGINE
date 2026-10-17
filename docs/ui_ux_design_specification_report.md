# AI Legal Decision Intelligence Engine
## Comprehensive Frontend UI/UX Design Specification Report

> **Target Audience:** UI/UX Designers, Product Designers, and Frontend Engineers  
> **Application Type:** Enterprise Legal Decision Intelligence & Case Workspace (SaaS)  
> **Primary Users:** Senior Indian Advocates, Chamber Associates, and Legal Researchers  
> **Design Tone:** *Chambers Authority* — Quiet, minimal, classic, trustworthy, highly functional. Comparable in polish to Linear, Stripe Dashboard, or a boutique law firm's client portal.

---

## 1. Executive Vision & Non-Negotiables

### 1.1 Product Purpose
The **AI Legal Decision Intelligence Engine** is a high-precision case workspace built for Indian litigation practice. It ingests complex case files (plaints, written statements, affidavits, interim orders, and documentary evidence), extracts grounded factual propositions, detects cross-filing contradictions, maps legal entities and precedents into an interactive knowledge graph, and retrieves relevant Indian statutory provisions (India Code) and judicial precedents (Indian Kanoon).

### 1.2 Core Product Truths (Design Guardrails)
1. **Decision Support, Not Automated Decisions:** The platform *never* predicts case outcomes and *never* gives automated legal advice. It presents grounded facts, references, citations, and review leads.
2. **Every Finding Must Be Grounded:** Every fact, issue, and graph node originates from an exact file coordinate with a clickable citation chip (`[Document · Location]`).
3. **Strict OCR & Document Quality Gating:** If a scanned document is unreadable or yields 0 clean text units, the system **strictly locks further AI analysis** across the platform and prominently flags the file for rescan/replacement.
4. **No Visual Fluff:** Zero full-page decorative cards, zero fluorescent neon buttons, zero cartoonish illustrations, and zero low-contrast text. Maximum border radius is `8px` (`6px` for buttons and inputs).

---

## 2. Design System Tokens & Global Styling

### 2.1 Color Palette

| Token | Light Theme (Default) | Dark Theme | Purpose / Usage |
| :--- | :--- | :--- | :--- |
| **`--bg`** | `#FAF7F2` (Parchment/Ivory) | `#141311` (Dark Charcoal) | Application page background |
| **`--surface`** | `#FFFFFF` (Pure Crisp White) | `#1C1A17` (Elevated Charcoal) | Cards, toolbars, tables, panels |
| **`--surface-2`** | `#F3EFEA` (Warm Linen) | `#26231F` (Subtle Tint) | Table headers, secondary pills, hover states |
| **`--primary`** | `#5E1B2C` (Oxblood Burgundy) | `#8A2B3D` (Burgundy) | Primary action buttons, active tabs, major issues |
| **`--primary-tint`** | `rgba(94, 27, 44, 0.08)` | `rgba(138, 43, 61, 0.20)` | Active tab badges, selected table rows |
| **`--brass`** | `#A07830` (Warm Brass) | `#C89D42` (Burnished Gold) | Scales monogram, citations, entities, accents |
| **`--text`** | `#1C1917` (Deep Ink) | `#FAF7F2` (Ivory Text) | Headings, primary body content |
| **`--text-muted`** | `#78716C` (Warm Gray) | `#A8A29E` (Muted Warm Gray) | Secondary labels, descriptions, metadata |
| **`--border`** | `#E7E2DA` (Fine Hairline) | `#2E2A24` (Dark Hairline) | Structural dividing lines (1px) |
| **`--danger`** | `#B91C1C` (Crimson) | `#EF4444` (Bright Red) | Unreadable scan warnings, analysis lock, errors |
| **`--warning`** | `#D97706` (Amber) | `#F59E0B` (Warm Amber) | Low OCR confidence, review leads |
| **`--success`** | `#15803D` (Forest Green) | `#22C55E` (Emerald Green) | Ready/completed statuses |
| **`--info`** | `#2563EB` (Cobalt Blue) | `#3B82F6` (Blue Slate) | Statutory provisions & India Code links |

> ⚠️ **Design Warning:** Never use green, cyan, or teal for primary action buttons. The primary interactive color is strictly **Oxblood Burgundy** (`#5E1B2C`).

### 2.2 Typography Hierarchy

| Font Family | Style / Weight | Usage |
| :--- | :--- | :--- |
| **Satoshi** | Sans-Serif (400, 500, 600) | Primary interface font (body text, toolbars, tables, buttons, inputs) |
| **Montserrat** | Sans-Serif (500, 600, 700) | Display headings (`h1`, `h2`, `h3`), case titles, chamber names |
| **Poppins / Inter** | Sans-Serif (400, 500) | Micro-labels, tooltips, secondary stats |
| **JetBrains Mono** | Monospace (400, 500, 600) | Citation chips, case numbers, statutory sections, dates, coordinates |

### 2.3 Component Geometry & Layout Tokens
* **Standard Button Height:** `36px` (`padding: 0 14px; border-radius: 6px; font-weight: 500; font-size: 14px;`)
* **Standard Input Height:** `36px` (`padding: 0 12px; border-radius: 6px; font-size: 14px;`)
* **Search Inputs with Leading Icon:** Icon left-centered at `14px`, text `padding-left: 40px !important;`
* **Citation Chip Height:** `22px` (`padding: 0 6px; border-radius: 6px; font-family: JetBrains Mono; font-size: 12px; background: var(--surface-2); border: 1px solid var(--border);`)
* **Fixed Header Height:** `56px` (`z-index: 40; border-bottom: 1px solid var(--border);`)
* **Left Navigation Rail:** `232px` width, fixed/sticky layout.
* **Drawers / Slide-Overs:** Right-docked `360px` or `720px` width with `box-shadow: -4px 0 24px rgba(0,0,0,0.12)`.

---

## 3. Global Application Architecture & Layout Shell

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ TOP BAR (56px) - [Logo/Scales Monogram] [Case Switcher] [Ctrl+K Quick Search] [Theme] [Avatar]│
├──────────────┬─────────────────────────────────────────────────────────────────────────┤
│ LEFT RAIL    │ MAIN CONTENT AREA (Single vertical scroll, max-w-6xl or full canvas)   │
│ (232px)      │                                                                         │
│              │ ┌─────────────────────────────────────────────────────────────────────┐ │
│ 1. Overview  │ │ PageHeader: Title + Description + Primary Action Button             │ │
│ 2. Documents │ ├─────────────────────────────────────────────────────────────────────┤ │
│ 3. Analysis  │ │ PageToolbar: Search bar + Filter Pills + View Switchers              │ │
│ 4. Graph     │ ├─────────────────────────────────────────────────────────────────────┤ │
│ 5. Research  │ │ PageBody: Single clean bordered surface with tables/cards/canvas     │ │
│ 6. Assistant │ ├─────────────────────────────────────────────────────────────────────┤ │
│ 7. Decision  │ │ PageFootnote: Candidate legal notices / statutory disclaimers       │ │
│ 8. Summary   │ └─────────────────────────────────────────────────────────────────────┘ │
│ ──────────── │                                                                         │
│ Hearing Info │                                                                         │
└──────────────┴─────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Module-by-Module Detailed Screen Specifications

---

### Module 1: Authentication & Chamber Onboarding

#### 1.1 Sign In (`/signin` or `/login`)
* **Purpose:** Secure advocate authentication.
* **Layout:** Centered card (`440px` max-width) on Parchment background with subtle Scales Monogram header.
* **Elements Required:**
  * Chamber/Firm Branding with Oxblood and Brass emblem.
  * Form fields: `Email Address` and `Password` with clear focus borders.
  * Primary Action: **"Sign In to Chamber"** (`.btn-primary`).
  * Secondary Action: "Forgot password?" and "Create chamber account".
  * Security reassurance: *"Local encrypted session · Offline-first privacy architecture"*.

#### 1.2 Sign Up & Initial Chamber Setup (`/signup` & `/setup`)
* **Purpose:** Register advocate profile and initialize chamber settings.
* **Elements Required:**
  * Full Name, Bar Registration Number / Council ID, Chamber/Firm Name.
  * Primary Court Jurisdiction dropdown (Supreme Court, High Courts, District Courts, NCLT, etc.).
  * Primary Action: **"Initialize Workspace"**.

---

### Module 2: Cases Management & Case Intake (`/cases` & `/cases/new`)

#### 2.1 Cases Directory (`/cases`)
* **Purpose:** The master portfolio list of all active and archived legal matters.
* **Layout:** `PageShell` with standard Header, Toolbar, and Table/Grid view.
* **Elements Required:**
  * **Header:** Title *"Cases"*, Description *"Active matters in chamber"*, Action **"+ New Case"**.
  * **Toolbar:**
    * Search Input: 40px left-padded search box with magnifying glass (*"Search cases by title, number, client, court..."*).
    * Filter Dropdowns: Stage filter (*All stages*, *Intake*, *Filed*, *Pleadings*, *Evidence*, *Arguments*, *Judgment reserved*, *Appeal*), Court filter.
    * View Switcher: Table View vs Grid Cards View.
  * **Cases Table:**
    * Columns: `Case Title / Matter`, `Court / Forum`, `Stage (Pill Badge)`, `Documents`, `Next Hearing Date`, `Status Dot`, `Actions (⋯ Menu)`.
    * Hover State: Row highlight with subtle Burgundy tint on title.
    * Quick Actions in ⋯ Menu: *Open Workspace*, *Edit Details*, *Delete Case*.

#### 2.2 Case Intake Slide-Over Drawer (`/cases/new`)
* **Purpose:** Fast creation of a new case file without page navigation.
* **Layout:** Right slide-over drawer (`480px` width) with backdrop dim.
* **Form Fields:**
  * `Case Title` (e.g., *M/s Apex Infrastructure vs. State of Karnataka*)
  * `Case / Filing Number` (e.g., *W.P. No. 14208/2024*)
  * `Court / Forum` (e.g., *High Court of Karnataka, Bengaluru Bench*)
  * `Our Client & Role` (e.g., *Petitioner / Appellant / Respondent / Defendant*)
  * `Opposing Party` (e.g., *State of Karnataka & Ors.*)
  * `Current Procedural Stage`
  * `Next Hearing Date` (Date picker)
  * `Case Summary / Intake Notes`
* **Actions:** **"Create Case"** (Primary) and "Cancel".

---

### Module 3: Case Overview & Strategy Board (`/cases/[caseId]` → Overview)

* **Purpose:** The command dashboard for a single case matter showing health, progress, and extracted authorities.
* **Elements Required:**
  1. **Key Case Statistics Bar (4-Column Hairline Metric Block):**
     * `Documents Uploaded` (Count)
     * `Pages Read / Units` (Count)
     * `Items to Review` (Count of unreadable or flagged items)
     * `Next Hearing Date` (Formatted date with days countdown)
  2. **5-Step Workflow Progress Indicator:**
     * Horizontal segmented track: `1. Upload` → `2. Extract` → `3. Analyse` → `4. Graph` → `5. Research`.
     * Shows completed (Brass checkmark), current (Burgundy ring), or pending state.
  3. **"Needs Attention" Triage Box:**
     * Single clean bordered box listing critical warnings.
     * **Unreadable Document Warning:** Shows when any file failed OCR, with a prominent red badge: *"Analysis Locked — Clean text could not be extracted"*, with direct button **"Fix in Documents"**.
  4. **Legal Authorities in the Case File Section:**
     * Displays all explicit statutes, sections, and case citations extracted from pleadings.
     * Collapsible rows with **Scale icon** showing: Section/Act, source document, cited quote.
     * **India Code Live Accordion:** Expanding a row fetches and displays statutory text directly from India Code with a button to perform deeper research.

---

### Module 4: Document Management & OCR Verification (`/cases/[caseId]` → Documents)

* **Purpose:** Upload, manage, preview, and verify plaints, affidavits, orders, and evidence documents.
* **Elements Required:**
  1. **Strict Low-OCR / Unreadable Document Alert Banner:**
     * Rendered at the top whenever files have failed text extraction (`text_unit_count === 0` or OCR failure).
     * Clear warning text: *"{N} unreadable / low-OCR document(s) detected — Analysis locked. Further AI analysis and graph generation are locked until you retry extraction or replace with clearer scans."*
  2. **Single-Line Drag-and-Drop Dropzone:**
     * Compact `56px` height dashed container with upload icon (*"Drop files here or browse · 50 MB max · PDF, DOCX, images"*).
  3. **Documents Master Table:**
     * Columns: `Name (with type icon)`, `Document Type`, `Pages (Mono tabular number)`, `Reading Status (Status Dot)`, `Date Added`, `Actions (⋯ Menu)`.
     * **Unreadable Row Treatment:** Red tint background, red failure dot, warning message *"Unreadable / Low OCR (0 readable lines) — Blocks analysis"*, with inline **Retry scan** and **Replace file** actions.
  4. **Document Actions (⋯ Menu):**
     * `Open Text Preview`: Opens extracted text drawer.
     * `Retry Extraction`: Re-triggers local OCR pipeline.
     * `Replace File`: Direct file input to swap bad scan with higher-resolution scan.
     * `Download Original`: Downloads raw PDF/DOCX file.
     * `Remove`: Deletes document with confirmation modal.
  5. **Text Preview & Inspection Drawer (`720px` width):**
     * Header with filename and page metadata.
     * Segmented view toggle: *Extracted Text Units* vs *Raw Document Coordinates*.
     * Search within extracted document text.

---

### Module 5: Case Intelligence & Cross-Document Analysis (`/cases/[caseId]` → Analysis)

* **Purpose:** Fact extraction, issue formulation, party identification, contradiction detection, and claim verification.
* **Elements Required:**
  1. **Privacy & Batching Info Bar:**
     * Status indicator showing documents ready for analysis.
     * Information popover confirming that raw files stay local and text is processed in encrypted batches.
  2. **Strict Analysis Lockout State:**
     * If unreadable documents exist, the **"Run analysis"** button is disabled with label *"Analysis locked (unreadable files)"*.
     * Red banner lists problematic filenames with guidance to replace them in Documents.
  3. **Advocate Claims Input (Collapsible):**
     * Textarea allowing advocates to enter up to 20 specific claims to test against the evidence.
  4. **5-Tab Analysis Results Section:**
     * **Tab 1: Facts (`{count}`):** Extracted factual statements with source citation chips linking to exact document page/character coordinates.
     * **Tab 2: Issues (`{count}`):** Legal and factual questions framed from the pleadings.
     * **Tab 3: Parties & Dates (`{count}`):** Entities, witnesses, and chronological timeline events with category tags.
     * **Tab 4: Review Leads / Contradictions (`{count}`):** Side-by-side comparison of conflicting statements (Statement A from Doc 1 vs Statement B from Doc 2) with exact quotes and citations.
     * **Tab 5: Claim Verification (`{count}`):** Submitted advocate claims rated as *Supported*, *Unsupported*, or *Needs Review* with explanatory reasoning.

---

### Module 6: Interactive Knowledge Graph (`/cases/[caseId]` → Graph)

* **Purpose:** Visual spatial map of relationships between case issues, facts, parties, and legal provisions.
* **Layout:** Full-width high-clarity SVG canvas (`1100px × 720px`) with right-side 360px Inspector Drawer.
* **Elements Required:**
  1. **Interactive Toolbar:**
     * Search Input with centered icon (`pl-10`) to filter nodes in real-time.
     * **Category Filter Pills:** `All`, `Issues (Burgundy)`, `Parties (Brass)`, `Provisions (Blue)`, `Facts (Linen)`.
     * **Label Density Toggle:** `Smart labels` (default: key hubs & hovered nodes), `All`, `Minimal`.
     * **Canvas Controls:** Zoom in, Zoom out, Reset canvas, View Switcher (Network Canvas vs Tabular List).
  2. **Force-Directed SVG Canvas:**
     * Multi-pass relaxation physics preventing node overlap (minimum `44px` clearance).
     * **Semantic Hub Layout:**
       * *Top Arc:* Case Issues & Core Findings.
       * *Left Flank:* Statutory Provisions & Acts.
       * *Right Flank:* Parties, Courts & Authorities.
       * *Bottom Field:* Grounded Facts & Timeline.
     * **Curved Edge Vectors:** Color-coded links for `supports` (brass/green), `contradicts` (dashed crimson), and `applies_to` (dotted blue).
     * **Hover Isolation:** Hovering any node dims all unrelated nodes to 18% opacity, highlights connected paths, and reveals relationship badges on links.
     * **Node Dragging:** Full mouse drag support to reposition nodes freely.
     * **Pill Badges:** Labels displayed on clean rounded background pills with contrast borders.
  3. **Node Inspector Drawer (360px right slide-over):**
     * Node type pill badge, label, full extracted statement.
     * Exact source citation chip (`[Doc · Locator]`).
     * Interactive list of connected neighbor nodes with relationship tags.

---

### Module 7: Legal Research & Statutory Precedents (`/cases/[caseId]` → Research)

* **Purpose:** Search, inspect, bookmark, and ground statutory sections (India Code) and judicial citations (Indian Kanoon).
* **Elements Required:**
  1. **5-Field Structured Search Filter Grid:**
     * `Query input` (Search sections, acts, doctrines, case citations).
     * `Court / Jurisdiction` dropdown (Supreme Court, Delhi High Court, Bombay High Court, etc.).
     * `From Date` & `To Date` limitation filter inputs.
     * `Specific Act` & `Section` inputs.
  2. **Segmented Results View:**
     * `All`, `Statutes (India Code)`, `Judgments (Indian Kanoon)`, `Saved Authorities`.
  3. **Authority Result Cards:**
     * Title, Court/Forum, Year, Citation, Relevance snippet with highlighted query terms.
     * Actions: **"Read Full Judgment / Section"**, **"Save / Bookmark"**, **"Generate Research Note"**.
  4. **Side-by-Side Kanoon & India Code Reader Drawer (`720px` width):**
     * Complete official statutory/judgment text with paragraph anchors and copy citation tools.
  5. **Grounded AI Research Note Generator:**
     * Synthesizes legal propositions across selected authorities with exact paragraph references.

---

### Module 8: Case Assistant / Advocate Copilot (`/cases/[caseId]` → Assistant)

* **Purpose:** Contextual AI conversational chat grounded exclusively on uploaded case pleadings and extracted facts.
* **Elements Required:**
  1. **Conversation History Stream:**
     * User queries and Assistant responses.
     * Strict inline numbered citation badges (e.g., `[1]`, `[2]`).
     * Hovering citation shows a preview tooltip; clicking opens the source document reader directly.
  2. **Pinned Bottom Composer Bar:**
     * Multi-line expanding textarea with prompt suggestion chips (*"Summarize plaintiff's primary claims"*, *"Identify timeline discrepancies"*, *"Check limitation applicability"*).
     * Disclaimer text: *"Assistant responses are grounded strictly on uploaded case files. Independently verify all citations."*
  3. **Chat History & Session Slide-Over Drawer:**
     * Switch between previous case conversation threads or start a fresh session.

---

### Module 9: Decision Support & Hearing Agenda (`/cases/[caseId]` → Decision & Summary)

#### 9.1 Decision Support Focus Board
* **Purpose:** Prepare senior advocate for oral arguments and cross-examination.
* **Sections:**
  * `Core Argument Strengths` (With grounded evidence anchors).
  * `Identified Vulnerabilities & Counter-Arguments` (Where opposition evidence is strong).
  * `Recommended Questions for Opposing Witness / Cross-Examination`.

#### 9.2 Case Summary Brief (`/cases/[caseId]` → Summary)
* **Purpose:** One-page executive brief covering matter facts, parties, contested issues, and applicable precedents.
* **Actions:** Export as Clean PDF, Copy Markdown Brief.

---

### Module 10: Hearing Dates & Court Calendar (`/dates`)

* **Purpose:** Chamber-wide calendar of upcoming hearing dates, filing deadlines, and limitation periods.
* **Layout:** Month grid / Agenda list with color-coded stage badges and direct links to case workspaces.

---

### Module 11: Chamber & System Settings (`/settings`)

* **Purpose:** Configure chamber profile, local storage paths, OCR preferences, and API keys.
* **Sections:**
  * `Advocate & Chamber Profile` (Name, Bar council ID, Chamber address).
  * `OCR & Document Parsing Engine` (Tesseract / EasyOCR local engine settings).
  * `AI Inference Configuration` (Gemini API key management, offline fallback settings).
  * `Data Privacy & Storage Controls` (Local cache purge, database backup).

---

## 5. Summary Checklist for Frontend Designers

| Section / Component | Key Deliverable | Priority |
| :--- | :--- | :--- |
| **Global Theme & Shell** | 56px Top Bar + 232px Left Rail in Parchment (`#FAF7F2`) & Dark Charcoal (`#141311`) | P0 (Critical) |
| **Typography System** | Satoshi (Body) + Montserrat (Headings) + JetBrains Mono (Citations) | P0 (Critical) |
| **Low-OCR Analysis Lock** | Prominent warning banner and disabled analysis trigger on unreadable scans | P0 (Critical) |
| **Knowledge Graph Canvas** | Force-directed 4-cluster map with label pills, hover isolation, and node dragging | P0 (Critical) |
| **Search Input Alignment** | 40px left-padded inputs with centered icons across all toolbars | P0 (Critical) |
| **Citation Chip Component** | 22px height JetBrains Mono badge (`[Doc · Locator]`) opening source drawer | P1 (High) |
| **Drawers & Slide-Overs** | 360px & 720px drawers for text previews, Kanoon reader, and node inspector | P1 (High) |

---
*Report compiled for AI Legal Decision Intelligence Engine UI/UX implementation.*
