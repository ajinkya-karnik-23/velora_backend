# SSE Event Reference — Control Testing Pipeline

Source: `app/services/control_testing_module/sse_pipeline.py`

---

## Wire Format

Every message on the stream is a standard SSE text frame:

```
data: <json>\n\n
```

The JSON envelope is always:

```jsonc
{
  "type":      "<event_type>",   // string — identifies the event
  "timestamp": 1716000000.123,   // float — Unix epoch seconds (server time)
  "data":      { ... }           // object — event-specific payload (documented below)
}
```

---

## Available Pipelines

| Generator | Endpoint use-case | Phases covered |
|---|---|---|
| `stream_g01_pipeline` | G01 analysis only | Init → Preprocessing → G01 Graph |
| `stream_full_pipeline` | End-to-end | Init → Preprocessing → G01 Graph → Work Order → Agent Execution → Result |

---

## Event Catalogue

Events are listed in emission order for the **full pipeline**. The G01-only pipeline emits a subset — marked in each event's header.

---

### Phase 1 — Initialisation

#### `pipeline_start`
> Emitted by: both pipelines

| Field | Type | Description |
|---|---|---|
| `task_id` | `string` | UUID for this pipeline run. **Present only in `stream_full_pipeline`.** |
| `control_id` | `string` | Forwarded from the incoming trigger. |
| `cycle_id` | `string` | Forwarded from the incoming trigger. |
| `test_id` | `string` | Forwarded from the incoming trigger. |
| `message` | `string` | Human-readable status line. |

```json
{
  "type": "pipeline_start",
  "timestamp": 1716000000.0,
  "data": {
    "task_id":    "d3f1a2b3-...",
    "control_id": "CTRL-042",
    "cycle_id":   "CYC-2026-Q1",
    "test_id":    "99",
    "message":    "Control testing pipeline accepted. Trigger validated and execution context initialised."
  }
}
```

---

### Phase 2 — Preprocessing

#### `preprocessing_start`
> Emitted by: both pipelines

| Field | Type | Description |
|---|---|---|
| `message` | `string` | Human-readable status line. |

```json
{
  "type": "preprocessing_start",
  "data": {
    "message": "Resolving the detailed test specification from the control registry. Binding the full validation description to the execution payload."
  }
}
```

---

#### `preprocessing_complete`
> Emitted by: both pipelines

| Field | Type | Description |
|---|---|---|
| `control_id` | `string` | Resolved control identifier. |
| `cycle_id` | `string` | Resolved cycle identifier. |
| `test_id` | `integer` | Resolved test identifier (cast to int). |
| `test_description` | `string` | Full validation description loaded from the registry. |
| `evidence_filenames` | `string[]` | Pre-listed evidence filenames extracted from the payload. |
| `message` | `string` | Summary including character count and evidence file count. |

```json
{
  "type": "preprocessing_complete",
  "data": {
    "control_id":         "CTRL-042",
    "cycle_id":           "CYC-2026-Q1",
    "test_id":            99,
    "test_description":   "Verify that all price change entries have authorised commentary...",
    "evidence_filenames": ["price_changes.xlsx", "sign_off_email.png"],
    "message":            "Test specification loaded. 412 character validation context bound. 2 pre-listed evidence file(s) in scope."
  }
}
```

---

### Phase 3 — G01 LangGraph

#### `graph_start`
> Emitted by: both pipelines

Carries the full static G01 topology so the frontend can render the graph before any node fires.

| Field | Type | Description |
|---|---|---|
| `graph_id` | `string` | Always `"G01_analyse_payload"`. |
| `nodes` | `Node[]` | Static node list (see below). |
| `edges` | `Edge[]` | Static edge list (see below). |
| `message` | `string` | Human-readable status line. |

**Node shape:** `{ "id": string, "label": string }`

**Edge shape:** `{ "from": string, "to": string }`

**Fixed G01 topology:**

```
Nodes:
  __start__        → START
  interpreter      → Interpreter
  evidence_gatherer → Evidence Gatherer
  __end__          → END

Edges:
  __start__        → interpreter
  __start__        → evidence_gatherer
  interpreter      → __end__
  evidence_gatherer → __end__
```

Both `interpreter` and `evidence_gatherer` run in **parallel** (both branch from `__start__`).

```json
{
  "type": "graph_start",
  "data": {
    "graph_id": "G01_analyse_payload",
    "nodes": [
      { "id": "__start__",         "label": "START" },
      { "id": "interpreter",       "label": "Interpreter" },
      { "id": "evidence_gatherer", "label": "Evidence Gatherer" },
      { "id": "__end__",           "label": "END" }
    ],
    "edges": [
      { "from": "__start__",        "to": "interpreter" },
      { "from": "__start__",        "to": "evidence_gatherer" },
      { "from": "interpreter",      "to": "__end__" },
      { "from": "evidence_gatherer","to": "__end__" }
    ],
    "message": "Launching G01 parallel analysis graph. Interpreter and Evidence Gatherer nodes executing simultaneously."
  }
}
```

---

#### `node_start`
> Emitted by: both pipelines — fires once per node, on `on_chain_start`

| Field | Type | Description |
|---|---|---|
| `node` | `string` | `"interpreter"` or `"evidence_gatherer"` |
| `message` | `string` | Node-specific status line. **Only present in `stream_full_pipeline`.** |

Node messages:
- `interpreter` → `"Classifying the test description against the methodology corpus. LLM inference in progress."`
- `evidence_gatherer` → `"Scanning the test description for referenced evidence filenames. Validating file presence on disk."`

```json
{
  "type": "node_start",
  "data": {
    "node":    "interpreter",
    "message": "Classifying the test description against the methodology corpus. LLM inference in progress."
  }
}
```

---

#### `node_complete` — interpreter
> Emitted by: both pipelines — fires on `on_chain_end` for the `interpreter` node

| Field | Type | Description |
|---|---|---|
| `node` | `string` | Always `"interpreter"`. |
| `result` | `object` | Pydantic model dump of `interpreter_result`. Key fields: `test_type` (string), `target_parameters` (array). |
| `message` | `string` | Includes classified `test_type` and parameter count. **Only in `stream_full_pipeline`.** |

```json
{
  "type": "node_complete",
  "data": {
    "node": "interpreter",
    "result": {
      "test_type": "CPT_PRICE_CHANGE_VALIDATION",
      "target_parameters": ["commentary_present", "authoriser_name"]
    },
    "message": "Test classified as 'CPT_PRICE_CHANGE_VALIDATION'. 2 target compliance parameter(s) extracted."
  }
}
```

---

#### `methodology_resolved`
> Emitted by: both pipelines — always immediately follows `node_complete` for `interpreter`

| Field | Type | Description |
|---|---|---|
| `category` | `string` | Test type string from interpreter (e.g. `"CPT_PRICE_CHANGE_VALIDATION"`). |
| `title` | `string` | Human-readable methodology playbook title. |
| `expected_tools` | `string[]` | Tool names the agent is expected to invoke for this category. |
| `classification_criteria` | `string` | Criteria used to classify this test type. |
| `methodology_instructions` | `string` | Full methodology instruction text for the agent. |
| `message` | `string` | Includes playbook title and tool count. **Only in `stream_full_pipeline`.** |

```json
{
  "type": "methodology_resolved",
  "data": {
    "category":                 "CPT_PRICE_CHANGE_VALIDATION",
    "title":                    "Price Change Commentary Validation",
    "expected_tools":           ["extract_price_change_entries", "extract_text_from_image"],
    "classification_criteria":  "...",
    "methodology_instructions": "...",
    "message":                  "Methodology playbook 'Price Change Commentary Validation' activated. 2 compliance tool(s) assigned to this execution."
  }
}
```

---

#### `node_complete` — evidence_gatherer
> Emitted by: both pipelines — fires on `on_chain_end` for the `evidence_gatherer` node

| Field | Type | Description |
|---|---|---|
| `node` | `string` | Always `"evidence_gatherer"`. |
| `result` | `object` | Pydantic model dump of `evidence_result`. Key field: `file_paths` (string[]). |
| `message` | `string` | File count summary. **Only in `stream_full_pipeline`.** |

```json
{
  "type": "node_complete",
  "data": {
    "node": "evidence_gatherer",
    "result": {
      "file_paths": ["/evidence/price_changes.xlsx", "/evidence/sign_off_email.png"]
    },
    "message": "2 evidence file(s) verified and queued for agent analysis."
  }
}
```

---

#### `graph_complete`
> Emitted by: both pipelines

| Field | Type | Description |
|---|---|---|
| `status` | `string` | Always `"success"` on the happy path. |
| `nodes_executed` | `string[]` | Sorted list of node IDs that fired (subset of `{"interpreter", "evidence_gatherer"}`). |
| `message` | `string` | Completion summary. **Only in `stream_full_pipeline`.** |

```json
{
  "type": "graph_complete",
  "data": {
    "status":         "success",
    "nodes_executed": ["evidence_gatherer", "interpreter"],
    "message":        "Analysis graph complete. Test category and evidence inventory finalised. Ready for agent dispatch."
  }
}
```

---

### Phase 4 — Work Order Compilation *(full pipeline only)*

#### `work_order_compiled`

| Field | Type | Description |
|---|---|---|
| `task_id` | `string` | Pipeline UUID. |
| `test_category` | `string` | Category string resolved from interpreter. |
| `evidence_count` | `integer` | Number of evidence file paths included in the dispatch. |
| `message` | `string` | Human-readable summary. |

The compiled work order (sent to the agent as its first message) contains:

```jsonc
{
  "task_id":          "...",
  "test_id":          99,
  "control_id":       "CTRL-042",
  "cycle_id":         "CYC-2026-Q1",
  "test_category":    "CPT_PRICE_CHANGE_VALIDATION",
  "test_description": "...",
  "evidence_paths":   ["/evidence/price_changes.xlsx"]
}
```

```json
{
  "type": "work_order_compiled",
  "data": {
    "task_id":        "d3f1a2b3-...",
    "test_category":  "CPT_PRICE_CHANGE_VALIDATION",
    "evidence_count": 2,
    "message":        "Work order packaged for 'CPT_PRICE_CHANGE_VALIDATION' compliance agent. 2 evidence file(s) included in the dispatch."
  }
}
```

---

### Phase 5 — Agent Routing *(full pipeline only)*

#### `agent_selected`

| Field | Type | Description |
|---|---|---|
| `agent_name` | `string` | Internal ADK agent name (snake_case). |
| `agent_label` | `string` | Human-readable agent label. |
| `test_category` | `string` | Category that drove the routing decision. |
| `message` | `string` | Routing summary. |

**Category → Agent routing table:**

| `test_category` | `agent_name` | `agent_label` |
|---|---|---|
| `CPT_PRICE_CHANGE_VALIDATION` | `default_cpt_price_change_validation_agent` | Price Change Commentary Validation Agent |
| `CPT_EMAIL_ANALYSIS` | `default_cpt_email_analysis_agent` | CPT Email Sign-Off Analysis Agent |
| `ROW_LEVEL_ANALYSIS` | `default_row_level_analysis_agent` | Row-Level Reconciliation Agent |
| `IPE_SAP_IMAGE_VALIDATION` | `default_ipe_sap_image_validation_agent` | IPE SAP GUI Visual Inspection Agent |
| *(any other / GENERIC)* | `default_generic_agent` | Generic Compliance Validation Agent |

```json
{
  "type": "agent_selected",
  "data": {
    "agent_name":    "default_cpt_price_change_validation_agent",
    "agent_label":   "Price Change Commentary Validation Agent",
    "test_category": "CPT_PRICE_CHANGE_VALIDATION",
    "message":       "'Price Change Commentary Validation Agent' selected as the compliance execution engine. Category routing: 'CPT_PRICE_CHANGE_VALIDATION'."
  }
}
```

---

### Phase 6 — ADK Agent Execution *(full pipeline only)*

#### `agent_session_created`

| Field | Type | Description |
|---|---|---|
| `session_id` | `string` | UUID of the `InMemorySessionService` session created for this run. |
| `message` | `string` | Human-readable status line. |

```json
{
  "type": "agent_session_created",
  "data": {
    "session_id": "a1b2c3d4-...",
    "message":    "Secure agent execution session initialised. Ingesting work order into the agentic layer."
  }
}
```

---

#### `agent_start`

| Field | Type | Description |
|---|---|---|
| `agent_name` | `string` | Internal ADK agent name. |
| `agent_label` | `string` | Human-readable agent label. |
| `message` | `string` | Human-readable status line. |

```json
{
  "type": "agent_start",
  "data": {
    "agent_name":  "default_cpt_price_change_validation_agent",
    "agent_label": "Price Change Commentary Validation Agent",
    "message":     "'Price Change Commentary Validation Agent' is now processing the work order. Tool invocations will be streamed as they occur."
  }
}
```

---

#### `tool_call`
> Repeating — one event per tool invocation dispatched by the agent

| Field | Type | Description |
|---|---|---|
| `tool_name` | `string` | Python function name (ADK `__name__`). |
| `call_number` | `integer` | Monotonically incrementing counter (1-indexed) across the entire agent run. |
| `message` | `string` | 1-liner description of what the tool is doing. |

**Tool name → display message registry:**

| `tool_name` | Display message |
|---|---|
| `extract_price_change_entries` | Scanning Excel workbook for price change condition blocks and commentary annotations |
| `extract_text_from_image` | Extracting structured field text and OCR content from image evidence |
| `analyse_email_evidence` | Analysing email screenshot for stakeholder sign-offs, approval markers, and timeline indicators |
| `analyse_image_evidence` | Inspecting SAP compliance screenshot for interface field values and structural configurations |
| `get_excel_table_shape` | Reading Excel spreadsheet row count, column structure, and boundary row data |
| `extract_table_structure_from_image` | Parsing image table layout to count data rows and capture boundary record content |
| `parse_excel_raw` | Performing high-fidelity raw structural extraction of spreadsheet contents for reconciliation |
| *(unknown tool)* | `"Executing tool '<tool_name>'"` |

```json
{
  "type": "tool_call",
  "data": {
    "tool_name":   "extract_price_change_entries",
    "call_number": 1,
    "message":     "Scanning Excel workbook for price change condition blocks and commentary annotations"
  }
}
```

---

#### `tool_result`
> Repeating — one event per tool response returned to the agent

| Field | Type | Description |
|---|---|---|
| `tool_name` | `string` | Python function name matching the prior `tool_call`. |
| `message` | `string` | Completion confirmation including the tool's display label. |

```json
{
  "type": "tool_result",
  "data": {
    "tool_name": "extract_price_change_entries",
    "message":   "'Scanning Excel workbook for price change condition blocks and commentary annotations' — extraction complete. Results handed off to the agent for compliance analysis."
  }
}
```

---

### Phase 7 — Result *(full pipeline only)*

#### `agent_complete`

The agent's final response is expected to be a JSON string with the shape:

```jsonc
{
  "compliance_status":   true | false,   // boolean
  "audit_justification": "..."           // string
}
```

If parsing fails, `audit_justification` is set to the first 300 characters of the raw response and `compliance_status` stays `null`.

| Field | Type | Description |
|---|---|---|
| `agent_name` | `string` | Internal ADK agent name. |
| `compliance_status` | `boolean \| null` | `true` = pass, `false` = fail, `null` = could not parse. |
| `verdict` | `string` | `"PASS"`, `"FAIL"`, or `"INCONCLUSIVE"`. |
| `audit_justification` | `string` | Explanation text from the agent. |
| `tool_calls_made` | `integer` | Total number of tool calls made during the agent run. |
| `message` | `string` | Summary including verdict and tool call count. |

```json
{
  "type": "agent_complete",
  "data": {
    "agent_name":          "default_cpt_price_change_validation_agent",
    "compliance_status":   true,
    "verdict":             "PASS",
    "audit_justification": "All price change entries have authorised commentary present...",
    "tool_calls_made":     3,
    "message":             "Agent concluded with verdict: PASS. 3 tool invocation(s) executed during the compliance analysis."
  }
}
```

---

#### `pipeline_complete`

| Field | Type | Description |
|---|---|---|
| `task_id` | `string` | Pipeline UUID echoed back. |
| `execution_time_ms` | `integer` | Wall-clock duration of the entire pipeline in milliseconds. |
| `compliance_status` | `boolean \| null` | Final compliance determination. |
| `verdict` | `string` | `"PASS"`, `"FAIL"`, or `"INCONCLUSIVE"`. |
| `message` | `string` | Completion summary including duration and verdict. |

```json
{
  "type": "pipeline_complete",
  "data": {
    "task_id":            "d3f1a2b3-...",
    "execution_time_ms":  14230,
    "compliance_status":  true,
    "verdict":            "PASS",
    "message":            "Control testing pipeline finished in 14230ms. Final verdict: PASS."
  }
}
```

---

### Error Events

An `error` event can be emitted at any phase. The stream **terminates** immediately after an error (the generator returns).

| Field | Type | Description |
|---|---|---|
| `phase` | `string` | Which phase failed: `"preprocessing"`, `"graph_execution"`, or `"agent_execution"`. |
| `message` | `string` | Exception message string. |

```json
{
  "type": "error",
  "data": {
    "phase":   "graph_execution",
    "message": "Connection to LLM timed out after 30s."
  }
}
```

---

## Complete Event Sequence Summary

### G01-only pipeline (`stream_g01_pipeline`)

```
pipeline_start
preprocessing_start
preprocessing_complete
graph_start
  node_start              (interpreter)
  node_start              (evidence_gatherer)
  node_complete           (interpreter)
  methodology_resolved
  node_complete           (evidence_gatherer)
graph_complete
```

### Full pipeline (`stream_full_pipeline`)

```
pipeline_start
preprocessing_start
preprocessing_complete
graph_start
  node_start              (interpreter)
  node_start              (evidence_gatherer)
  node_complete           (interpreter)
  methodology_resolved
  node_complete           (evidence_gatherer)
graph_complete
work_order_compiled
agent_selected
agent_session_created
agent_start
  tool_call               (×N — one per tool dispatch)
  tool_result             (×N — one per tool response)
agent_complete
pipeline_complete
```

> `node_start` events for `interpreter` and `evidence_gatherer` may arrive in either order — both nodes run in parallel. `methodology_resolved` always arrives immediately after `node_complete(interpreter)`.

---

## Verdict Logic

```
compliance_status == true   →  verdict = "PASS"
compliance_status == false  →  verdict = "FAIL"
compliance_status == null   →  verdict = "INCONCLUSIVE"
```

`compliance_status` comes directly from the agent's JSON output field `compliance_status`. If the agent returns non-JSON or the field is absent, it is `null`.
