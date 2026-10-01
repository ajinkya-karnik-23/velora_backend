# V.E.L.O.R.A

**Validation Engine for Logic driven Orchestration and Risk Assurance**

## Approach Document

| | |
|---|---|
| Document type | Solution approach and architecture |
| Version | 2.0 |
| Status | For review |
| Supersedes | VELORA Approach Document v1 |

---

## Table of contents

1. [Document scope](#1-document-scope)
2. [Solution overview](#2-solution-overview)
3. [Design principles](#3-design-principles)
4. [Architecture](#4-architecture)
5. [The knowledge layer](#5-the-knowledge-layer)
6. [Control testing lifecycle](#6-control-testing-lifecycle)
7. [Agentic execution model](#7-agentic-execution-model)
8. [Evidence model](#8-evidence-model)
9. [Observability and execution transparency](#9-observability-and-execution-transparency)
10. [Persistence and audit trail](#10-persistence-and-audit-trail)
11. [Reporting](#11-reporting)
12. [Security and multi-tenancy](#12-security-and-multi-tenancy)
13. [Extensibility model](#13-extensibility-model)
14. [Engineering quality](#14-engineering-quality)
15. [Current boundaries and roadmap](#15-current-boundaries-and-roadmap)
16. [Summary](#16-summary)

---

## 1. Document scope

This document describes the approach behind VELORA: what the platform sets out to do, the principles it is built on, how its architecture is organised, and how a control test travels from an auditor's request to a signed-off work paper.

It is written for engagement leadership, audit methodology owners, platform engineers and reviewers who need to understand not only what the platform does but **why it is built the way it is**. Component-level API documentation and deployment runbooks are maintained separately.

---

## 2. Solution overview

VELORA is a control testing platform for SOX and internal audit engagements. It manages the audit lifecycle — engagements, controls, evidence, testing and reporting — and executes control tests through an agentic assessment pipeline that reads the evidence an auditor would read and produces a structured, justified conclusion.

The platform is built around a simple proposition: **an auditor's judgement is expensive and their document handling is not.** Reading a SAP screenshot, counting rows in an export, checking that an approval email names the right person before the right date, reconciling a spreadsheet against a system extract — this work is mechanical, voluminous and entirely traceable. VELORA automates that layer and returns the auditor a conclusion with its reasoning attached, so their judgement is applied to the exception rather than the transcription.

### 2.1 Core objectives

| Objective | What it means in practice |
|---|---|
| Automate evidence assessment | Read and evaluate evidence in the formats audit actually receives: spreadsheets, SAP screenshots, emails, PDFs, scanned documents |
| Make testing methodology explicit | Testing approaches are declared as data, not buried in code or in an individual's head |
| Produce audit-grade output | Every conclusion carries a structured result and a written justification a reviewer can challenge |
| Keep the work traceable | Which evidence, which methodology, which tools, which model, when, by whom |
| Stay extensible | A new control category is a configuration and agent definition, not a platform rewrite |
| Keep the auditor in charge | The platform proposes and evidences a conclusion; the engagement team reviews, overrides and signs |

---

## 3. Design principles

These principles run through every layer of the platform and explain most of its design decisions.

**1. Evidence is the unit of truth.**
Nothing is concluded without evidence that can be pointed at. Every assessment names the files it read and, where the format allows, the pages or rows within them.

**2. Methodology is declared, not implied.**
Each testing category carries a title, the criteria that select it, the tools it may use and its step-by-step procedure. That declaration is the single source used both to classify an incoming test and to instruct the agent that executes it, so classification and execution can never drift apart.

**3. Structured outputs over prose.**
Agents return typed schemas — compliance status, counts, matched attributes, discrepancies, flagged anomalies, justification — rather than free narrative. Structured output is what makes results comparable, reportable and reviewable at scale.

**4. Fail fast, and fail informatively.**
If required evidence is missing, the pipeline stops before any model is invoked and says so plainly. Spending model budget on a test that cannot conclude helps nobody, and a vague failure message is worse than none.

**5. Determinism where determinism belongs.**
File resolution, evidence linkage, permission checks, persistence and reporting are ordinary deterministic code. Language models are used only where judgement over unstructured content is genuinely required, and are constrained by schemas and explicit tool rules.

**6. Observable by construction.**
The pipeline streams its own progress: each stage, each node, each tool call and result. A reviewer watching a run sees the same sequence the auditor would have performed manually.

**7. Configuration over code.**
Client onboarding, control definitions, testing methodologies and knowledge content are data. Adding an engagement does not mean adding a release.

---

## 4. Architecture

### 4.1 Layers

VELORA separates audit management from audit execution, so the pipeline can evolve independently of the workflow around it.

| Layer | Responsibility | Built with |
|---|---|---|
| **Presentation** | Engagement workspace, controls, evidence, testing, live run visibility, reporting, knowledge base | React 19, TypeScript, Vite, Redux Toolkit Query, Tailwind |
| **API** | Authentication, authorisation, engagement and control management, evidence handling, test execution and streaming, reporting | FastAPI, Pydantic v2 |
| **Orchestration** | Payload preparation, classification, evidence resolution, work-order compilation, agent routing | LangGraph |
| **Agentic** | Category-specific assessment: tool invocation, evidence analysis, structured conclusion | Google ADK, LiteLLM |
| **Tooling** | Format-specific extraction and analysis | OCR (Tesseract, OpenCV, Pillow), pandas, openpyxl, multimodal model calls |
| **Knowledge** | Methodology corpus and the curated audit knowledge graph | Declarative Python corpus, markdown knowledge base |
| **Persistence** | Engagement, control, evidence and result records; evidence artefacts | PostgreSQL (async SQLAlchemy, Alembic), Azure Blob Storage |
| **Observability** | Execution streaming, structured logs, metrics, model tracing | SSE, structlog, Prometheus, LangSmith |

### 4.2 Request flow

```
  Auditor (browser)
        │  initiate test
        ▼
  ┌───────────────┐   work order   ┌──────────────────┐
  │  FastAPI      │───────────────▶│  LangGraph       │
  │  API layer    │                │  preprocessing   │
  └───────────────┘                └──────────────────┘
        ▲                             │          │
        │ SSE events                  │          │ parallel
        │                    interpreter      evidence gatherer
        │                             │          │
        │                             └────┬─────┘
        │                                  ▼
        │                        evidence completeness gate
        │                                  │
        │                                  ▼
        │                          ┌──────────────┐
        │                          │  ADK agent   │──▶ tools (OCR, Excel,
        │                          │  (by category)│     image, email)
        │                          └──────────────┘
        │                                  │ structured result
        │                                  ▼
        └───────────────────  PostgreSQL + Blob Storage ──▶ work paper
```

### 4.3 Why this shape

Three decisions define the architecture:

- **Classification is separated from assessment.** Deciding *what kind of test this is* is a small, cheap, well-bounded problem. Doing the test is a large one. Separating them means the expensive step always receives an explicit instruction set rather than inferring its own task.
- **Evidence resolution runs in parallel with classification.** The two do not depend on each other, and running them together means the completeness gate can fire before any assessment cost is incurred.
- **Each category owns its output schema.** A row-count reconciliation and an email approval check are not the same shape of finding, and flattening them into a common "result" field would lose exactly the detail a reviewer needs.

---

## 5. The knowledge layer

VELORA holds audit knowledge in two complementary forms: a **methodology corpus** the machine executes, and a **knowledge graph** the organisation reads. Both describe the same doctrine, at different levels of abstraction.

### 5.1 The methodology corpus

Each testing category is declared once, with four parts:

| Element | Purpose |
|---|---|
| `title` | The human name of the methodology |
| `classification_criteria` | When this category applies — and, importantly, when it does not |
| `expected_tools` | The tools the category is expected to use |
| `methodology_instructions` | The step-by-step testing procedure, including decision rules and output requirements |

This single declaration is used twice: the classification prompt is **compiled from the criteria of every category**, and the executing agent is **instructed with the selected category's procedure**. Adding a category therefore updates both the classifier and the executor at once — they cannot disagree.

The criteria carry negative guidance as well as positive, because the hard classification cases are near-misses. A test naming a SAP condition code may be a screenshot field validation, a row-count reconciliation or a pricing commentary check; the corpus states which signal distinguishes them. This is the accumulated judgement of the methodology owner, written down where the platform can apply it consistently.

### 5.2 The audit knowledge graph

The knowledge graph is the platform's institutional memory: a curated set of linked articles covering methodology, evidence types, classification rules, tooling strategy and the auditor workflow. Each article declares its place in the graph, and links to related articles as `[[wiki links]]`; the platform resolves those links into a navigable, force-directed graph rendered alongside the articles themselves.

```
                    Control Testing & SOX Methodology
                                  │
                ┌─────────────────┼─────────────────┐
                ▼                 ▼                 ▼
           How To Scope    Control Effectiveness  Evidence Gatherer
                │                                    │
        ┌───────┴────────┐                    ┌──────┴──────┐
        ▼                ▼                    ▼             ▼
 Test Classification  Evidence            IPE             CPT
        │            Characteristics        │
        ▼                                   ▼
 Classification     ┌──────────────────────┴───────────────┐
 Decision Rules     ▼                  ▼                   ▼
        │    IPE SAP Image      ROW_LEVEL_ANALYSIS    Evidence Processing
        │      Validation              │                   │
        └───────────┬──────────────────┴─────────┬─────────┘
                    ▼                            ▼
             Tool Selection Strategy       OCR / Structured Extraction
                    │
                    ▼
              Tool Registry
```

Node metadata (`level`, `nodeType`, `color`) gives the graph a deliberate taxonomy — root, methodology, classification, evidence, evidence-type, method, support — so the visual layout carries meaning rather than decoration.

The graph serves four purposes:

1. **Shared vocabulary.** Testers, reviewers and engineers describe evidence and methodology in the same terms.
2. **Explicit decision rules.** Classification and tool-selection heuristics are written down, reviewable and challengeable.
3. **Onboarding.** A new joiner can traverse from the root to any methodology and understand how the platform reasons.
4. **Change control.** When methodology changes, the article and the corpus entry move together, and the graph shows what else is affected.

Because knowledge bases are configured per engagement, methodology that is specific to a client sits alongside the platform's core doctrine without polluting it.

### 5.3 How the two forms relate

The knowledge graph is the **doctrine**; the methodology corpus is its **executable projection**. Doctrine is written for humans and is broad — it covers scoping, evidence characteristics and effectiveness conclusions that no agent executes. The corpus is narrow and precise, because an agent acts on it. Keeping them distinct avoids the common failure of documentation that drifts from behaviour: the corpus is code and cannot drift, and the graph is reviewed as methodology rather than mistaken for it.

---

## 6. Control testing lifecycle

A control travels through five stages, each with its own source of information.

| Stage | Activity | Output |
|---|---|---|
| **1. Scope** | The control's definition, risk, frequency, rating and objective are established; sample sizes follow the engagement's sampling methodology | Tested population and sample |
| **2. Gather** | Evidence is attached per sample, from upload or from the engagement's evidence vault | Evidence linked to the item it supports |
| **3. Execute** | The agentic pipeline classifies, resolves evidence, runs the assessment and returns a structured conclusion | Result, justification, execution record |
| **4. Conclude** | The engagement team reviews results, records manual procedures where the standard attributes are insufficient, and resolves exceptions | Concluded control |
| **5. Report** | Results and their supporting detail are rendered into the engagement's work paper format | Work paper and audit trail |

Two rules govern the lifecycle:

- **Evidence changes void conclusions.** A result describes the evidence it was produced from. If that evidence is replaced or removed, the result no longer describes what is attached, and the item returns to untested. This prevents a fresh upload inheriting a previous verdict.
- **Not concluded is never passed.** A test that could not reach a conclusion is reported as such, and is never absorbed into the pass count. Exceptions and inconclusive items are distinct states with distinct reporting consequences.

---

## 7. Agentic execution model

### 7.1 Stage 1 — Preparation

The incoming request is normalised and enriched with the control's testing definition, producing a consistent payload regardless of which surface initiated the run.

### 7.2 Stage 2 — Parallel analysis

Two independent nodes execute concurrently in a LangGraph state graph:

**Interpreter node.** Classifies the test into a methodology category using criteria compiled from the corpus, and extracts the target parameters the test refers to. Output is bound to a JSON schema, so the classification is a typed value rather than parsed prose.

**Evidence gatherer node.** Extracts the evidence filenames the test description refers to, constructs their expected storage paths for the engagement, control and test, and verifies each one exists. It returns what was found, what was required and what is missing.

### 7.3 Stage 2.5 — Evidence completeness gate

If any required evidence is absent, the run stops here with a clear, non-technical message and no agent is invoked. This is deliberate: an agent asked to test against missing evidence will loop searching for it, burn budget and eventually produce an unreliable answer.

### 7.4 Stage 3 — Work order

Classification and evidence resolution are merged into a work order: task, engagement, control, test, category, description and verified evidence paths. This is the contract handed to the agentic layer, and the unit that is logged.

### 7.5 Stage 4 — Routing and the agent suite

The category selects a purpose-built agent. Each is configured with its methodology instructions, its own tools, and a typed input and output schema.

| Agent | Assesses | Principal tools | Output includes |
|---|---|---|---|
| **Price change validation** | Pricing modifications carry required commentary | Spreadsheet price-change extraction, image text extraction | Modifications found, uncommented count, flagged anomalies |
| **Email analysis** | Approvals, sign-offs and deadline windows in correspondence | Email evidence analysis | Stakeholders verified, timeline met |
| **Row-level analysis** | Reconciliation between sources: row counts, first/last row alignment | Spreadsheet extraction, table extraction from images, multi-image analysis | Source and target counts, match flags, discrepancies |
| **SAP image validation** | Fields visible in system screenshots: transaction code, organisation, condition type, validity | Image analysis, OCR, transaction-code inspection | Extracted fields, interface discrepancies |
| **Generic validation** | Controls outside a specialised category | Text and attribute comparison | Files processed, matched attributes |

Every agent returns `compliance_status` and `audit_justification`; the remaining fields are category-specific.

### 7.6 Stage 5 — Execution

A dedicated session is created per test. The agent receives the work order, invokes its tools, and returns a response conforming to its output schema. The session lives only for that test, so runs cannot contaminate each other.

### 7.7 Guardrails

Model behaviour is constrained deliberately:

- **Tool-call discipline.** Methodology instructions state how many times a tool may be invoked and when it must not be — for example, analysing a set of images in a single multimodal call rather than iterating, with retries explicitly forbidden.
- **Schema enforcement.** Output must satisfy the category's schema; there is no free-text escape hatch for the verdict itself.
- **Scope boundaries.** Where a control references evidence outside the category's remit, the agent is instructed to note the dependency in its justification rather than assess it.
- **Deterministic settings.** Classification runs at zero temperature.

---

## 8. Evidence model

Evidence is a first-class record, not an attachment.

- **Linked to what it supports.** Evidence is associated with the engagement, control, test and, where applicable, the individual sample it evidences. Assessment of one item never relies on another item's evidence.
- **Stored separately from metadata.** Artefacts live in Blob Storage under an engagement-scoped path; the record, status, uploader and version live in PostgreSQL.
- **Requirement-aware.** Where an engagement declares what a control's evidence must be, uploads are judged against that requirement, per item. Mismatch messages are deliberately generic so internal validation rules cannot be inferred from the interface.
- **Versioned in effect.** Re-uploading changes the evidence fingerprint an assessment was pinned to, which voids the conclusion drawn from the earlier file.
- **Format-agnostic at the boundary.** Spreadsheets, images, PDFs, emails and scans are accepted; the tooling layer, not the auditor, deals with format.

---

## 9. Observability and execution transparency

Execution is streamed to the client over Server-Sent Events. The event taxonomy mirrors the pipeline exactly:

| Phase | Events |
|---|---|
| Pipeline | `pipeline_start`, `pipeline_complete`, `error` |
| Preprocessing | `preprocessing_start`, `preprocessing_complete` |
| Graph | `graph_start`, `node_start`, `node_complete`, `methodology_resolved`, `graph_complete` |
| Agent | `work_order_compiled`, `agent_selected`, `agent_session_created`, `agent_start`, `agent_complete` |
| Tools | `tool_call`, `tool_result` |

The interface renders this as a live progression, so the auditor sees which methodology was resolved, which agent was selected, which tools ran and what each returned. This matters for two reasons: a long-running assessment that shows its work is trusted, and an assessment that goes wrong is diagnosable without reading logs.

Alongside streaming, the platform emits structured application logs, Prometheus metrics and model-level traces for prompt, token and latency analysis.

---

## 10. Persistence and audit trail

| Record | Holds |
|---|---|
| Engagement, control and test records | Scope of work: cycles, attached controls, test definitions, sample sizing |
| Evidence records | Artefact metadata, linkage, status, uploader, version |
| Assessment results | Compliance status, audit justification, execution time, execution status, task identity |
| Test logs | Every executed test: what was run, its verdict, its notes, by whom and when |

The trail is append-only in practice: re-running a test adds a record rather than amending one, so a reviewer can see how a conclusion was reached and whether it changed. Results are attributable to a user and a point in time, and each is tied to the evidence it was produced from.

---

## 11. Reporting

Results are rendered into the engagement's own work paper formats rather than a platform-specific report, because the work paper is the auditable artefact and it usually has a prescribed shape.

- **Templated documents.** Word templates are populated with control identity, test description, result, evidence inventory and tester.
- **Work paper population.** Where an engagement provides a spreadsheet work paper, the platform fills its preparation, test plan, execution and conclusion sections, and accompanies it with a per-sample detail sheet carrying each item's parameters, result, remarks and the validation narrative, evidence and performer behind it.
- **Reviewer prompts preserved.** Fields the platform deliberately does not answer are marked for the reviewer rather than left silently blank.

---

## 12. Security and multi-tenancy

| Control | Implementation |
|---|---|
| Authentication | JWT access tokens with HTTP-only refresh cookies and silent renewal |
| Authorisation | Role hierarchy (Viewer, Auditor, Moderator, Admin) plus discrete permissions |
| Engagement scoping | Membership of an engagement is enforced on read and write; elevated roles bypass by design, everyone else does not |
| Client isolation | Every client's controls, evidence, knowledge base and configuration are scoped to that client |
| Secrets | Injected as environment configuration; never held in source or client data |
| Evidence storage | Environment-scoped containers, access mediated by the API rather than exposed directly |
| Rate limiting and logging | Middleware-level request throttling with structured request logs |

---

## 13. Extensibility model

The platform is designed so that the common changes are configuration, not engineering.

| Change | What it takes |
|---|---|
| Onboard a client | Point the platform at the client's data location: control definitions, evidence requirements, work paper templates, knowledge base |
| Add a control | Supply its definition; it appears in the repository, ready to attach to an engagement |
| Add a testing methodology | One corpus entry (criteria, tools, procedure), one agent definition, one output schema |
| Add a tool | Register it in the tool repository and reference it from the methodology |
| Extend a test at engagement level | Auditors define manual test steps with their own parameters and evidence requirement, executed and concluded alongside automated tests |
| Extend the knowledge graph | Add a markdown article with its metadata and links |

The consistent rule is that client-supplied information is matched on **content, not filename**, and missing configuration degrades to an empty result rather than an error. A partially configured engagement runs; it simply shows less.

---

## 14. Engineering quality

- **Layered services.** Endpoint → service → repository, with services owning transaction boundaries.
- **Typed throughout.** Pydantic schemas at the API boundary, typed models in the data layer, TypeScript in the client.
- **Schema migrations.** Every structural change ships as a migration; no implicit schema drift.
- **Automated tests.** Unit tests over services and pure logic, integration tests over API behaviour including permissions, isolation and negative paths.
- **Static gates.** Formatting, linting and type checking on both backend and frontend.

---

## 15. Current boundaries and roadmap

Stating the boundary is part of the approach.

| Area | Position today | Direction |
|---|---|---|
| Knowledge graph | Curated and navigable; informs methodology and people | Retrieval-backed: agents query the graph for methodology context at execution time |
| Methodology corpus | Maintained by engineering alongside the knowledge base | Editable by methodology owners through the interface, with versioning and approval |
| Model strategy | Task-appropriate models behind a provider-neutral layer | Per-category model selection, with cost and accuracy measured per methodology |
| Sampling | Engagement sampling methodology applied to size and select | Population-aware selection with stratification |
| Assurance of the assessor | Structured outputs, streamed execution, justifications | Systematic benchmarking of agent conclusions against reviewed outcomes |
| Human-in-the-loop | Review and override at conclusion | Targeted review queues driven by confidence and materiality |

---

## 16. Summary

VELORA treats control testing as an evidence-processing problem with a judgement layer on top, and builds accordingly.

Testing methodology is declared as data, and that declaration drives both classification and execution, so the two cannot diverge. Preparation, classification and evidence resolution are deterministic; language models are applied only to the interpretation of unstructured evidence, and are constrained by explicit procedures, tool rules and typed output schemas. Evidence is bound to the item it supports, conclusions are bound to the evidence that produced them, and any change to that evidence voids the conclusion rather than silently outliving it. Every run streams its own progress and leaves an attributable record behind.

Around that engine sits the audit workflow — engagements, controls, evidence, review and reporting — and behind it sits a curated knowledge graph that keeps the methodology explicit, reviewable and shared. The result is a platform that removes the mechanical half of control testing while making the remaining half easier to review, and that grows by configuration as new controls, methodologies and engagements arrive.
