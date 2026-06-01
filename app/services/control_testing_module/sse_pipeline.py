"""
SSE streaming pipeline for the control testing module.

Provides two generators:
  - stream_g01_pipeline   : G01 LangGraph analysis only (preprocessing + graph)
  - stream_full_pipeline  : End-to-end (preprocessing → graph → work order → ADK agent)

Agent definitions in agent_suite.py and business logic in run_module.py are untouched.
Event types and their display metadata live in status_manifest.json alongside this module.
"""

import json
import time
import uuid
import logging
from typing import Any, AsyncGenerator, Dict

from google.adk import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types

import app.services.control_testing_module.google_agent_landscape.agent_suite as suite
from app.services.control_testing_module.helper_scripts.methodology_mapper import (
    get_methodology_for_category,
)
from app.services.control_testing_module.helper_scripts.payload_preprocessor import (
    preprocess_incoming_payload,
)
from app.services.control_testing_module.lang_graphs.G01_analyse_payload import graph

logger = logging.getLogger("control_testing_module")


# ─────────────────────────────────────────────────────────────────────────────
# LABEL REGISTRIES  (mirrors status_manifest.json for server-side logging)
# ─────────────────────────────────────────────────────────────────────────────

# Human-readable label per specialised agent (keyed by agent.name)
_AGENT_LABELS: Dict[str, str] = {
    "default_cpt_price_change_validation_agent": "Price Change Commentary Validation Agent",
    "default_cpt_email_analysis_agent":          "CPT Email Sign-Off Analysis Agent",
    "default_row_level_analysis_agent":           "Row-Level Reconciliation Agent",
    "default_ipe_sap_image_validation_agent":     "IPE SAP GUI Visual Inspection Agent",
    "default_generic_agent":                      "Generic Compliance Validation Agent",
}

# 1-liner status per tool call (keyed by Python method __name__ — what ADK uses)
_TOOL_LABELS: Dict[str, str] = {
    "extract_price_change_entries":        "Scanning Excel workbook for price change condition blocks and commentary annotations",
    "extract_text_from_image":             "Extracting structured field text and OCR content from image evidence",
    "analyse_email_evidence":              "Analysing email screenshot for stakeholder sign-offs, approval markers, and timeline indicators",
    "analyse_image_evidence":              "Inspecting SAP compliance screenshot for interface field values and structural configurations",
    "get_excel_table_shape":               "Reading Excel spreadsheet row count, column structure, and boundary row data",
    "extract_table_structure_from_image":  "Parsing image table layout to count data rows and capture boundary record content",
    "parse_excel_raw":                     "Performing high-fidelity raw structural extraction of spreadsheet contents for reconciliation",
}

# Category → agent instance (mirrors routing in run_module.py exactly)
def _resolve_agent(category: str) -> Any:
    routing = {
        "CPT_PRICE_CHANGE_VALIDATION": suite.default_CPT_PRICE_CHANGE_VALIDATION_agent,
        "CPT_EMAIL_ANALYSIS":          suite.default_CPT_EMAIL_ANALYSIS_agent,
        "ROW_LEVEL_ANALYSIS":          suite.default_ROW_LEVEL_ANALYSIS_agent,
        "IPE_SAP_IMAGE_VALIDATION":    suite.default_IPE_SAP_IMAGE_VALIDATION_agent,
    }
    return routing.get(category, suite.default_GENERIC_agent)


# Static G01 topology — sent once so the frontend can draw the graph structure upfront
_G01_TOPOLOGY: Dict[str, Any] = {
    "graph_id": "G01_analyse_payload",
    "nodes": [
        {"id": "__start__",        "label": "START"},
        {"id": "interpreter",      "label": "Interpreter"},
        {"id": "evidence_gatherer","label": "Evidence Gatherer"},
        {"id": "__end__",          "label": "END"},
    ],
    "edges": [
        {"from": "__start__",        "to": "interpreter"},
        {"from": "__start__",        "to": "evidence_gatherer"},
        {"from": "interpreter",      "to": "__end__"},
        {"from": "evidence_gatherer","to": "__end__"},
    ],
}

_LANGGRAPH_NODE_NAMES = {"interpreter", "evidence_gatherer"}


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _emit(event_type: str, data: Dict[str, Any]) -> str:
    """Formats a single SSE message: data: <json>\\n\\n"""
    payload = json.dumps(
        {"type": event_type, "timestamp": time.time(), "data": data},
        default=str,
    )
    return f"data: {payload}\n\n"


def _to_dict(obj: Any) -> Any:
    if obj is None:
        return None
    return obj.model_dump() if hasattr(obj, "model_dump") else obj


def _extract_text(content: Any) -> str:
    """Pull the first text part out of a genai Content object."""
    try:
        for part in content.parts:
            if hasattr(part, "text") and part.text:
                return part.text
    except Exception:
        pass
    return ""



# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC GENERATOR 1 — G01 only  (existing endpoint, unchanged behaviour)
# ─────────────────────────────────────────────────────────────────────────────

async def stream_g01_pipeline(
    incoming_trigger: Dict[str, Any],
) -> AsyncGenerator[str, None]:
    """
    Yields SSE events for the G01 analysis phase only.
    Stops after graph_complete — ADK agent is not included.
    """
    yield _emit("pipeline_start", {
        "control_id": incoming_trigger.get("control_id"),
        "cycle_id":   incoming_trigger.get("cycle_id"),
        "test_id":    incoming_trigger.get("test_id"),
        "message":    "Control testing pipeline accepted and initialised.",
    })

    # Preprocessing
    try:
        processed_payload = preprocess_incoming_payload(incoming_trigger)
        processed_payload["test_id"] = int(incoming_trigger.get("test_id", 0))
    except Exception as exc:
        logger.error(f"[SSE/G01] Preprocessing failed: {exc}")
        yield _emit("error", {"phase": "preprocessing", "message": str(exc)})
        return

    description_len = len(processed_payload.get("test_description", ""))
    yield _emit("preprocessing_start", {
        "message": "Resolving test configuration from the control registry.",
    })
    yield _emit("preprocessing_complete", {
        "control_id":         processed_payload["control_id"],
        "cycle_id":           processed_payload["cycle_id"],
        "test_id":            processed_payload["test_id"],
        "test_description":   processed_payload["test_description"],
        "evidence_filenames": processed_payload.get("evidence_filenames", []),
        "message": f"Test specification loaded. {description_len} character validation context bound.",
    })

    # G01 graph
    yield _emit("graph_start", {
        **_G01_TOPOLOGY,
        "message": "Launching G01 parallel analysis graph.",
    })

    nodes_started: set = set()

    try:
        async for event in graph.astream_events(processed_payload, version="v2"):
            kind: str = event.get("event", "")
            node: str = event.get("name", "")

            if kind == "on_chain_start" and node in _LANGGRAPH_NODE_NAMES:
                if node not in nodes_started:
                    nodes_started.add(node)
                    yield _emit("node_start", {"node": node})

            elif kind == "on_chain_end" and node == "interpreter":
                output = event.get("data", {}).get("output", {})
                result = _to_dict(output.get("interpreter_result")) or {}
                test_type = result.get("test_type", "GENERIC")
                yield _emit("node_complete", {"node": "interpreter", "result": result})

                methodology = get_methodology_for_category(test_type)
                yield _emit("methodology_resolved", {
                    "category":                 test_type,
                    "title":                    methodology.get("title"),
                    "expected_tools":           methodology.get("expected_tools", []),
                    "classification_criteria":  methodology.get("classification_criteria"),
                    "methodology_instructions": methodology.get("methodology_instructions"),
                })

            elif kind == "on_chain_end" and node == "evidence_gatherer":
                output = event.get("data", {}).get("output", {})
                result = _to_dict(output.get("evidence_result")) or {}
                yield _emit("node_complete", {"node": "evidence_gatherer", "result": result})

    except Exception as exc:
        logger.error(f"[SSE/G01] Graph error: {exc}")
        yield _emit("error", {"phase": "graph_execution", "message": str(exc)})
        return

    yield _emit("graph_complete", {
        "status":         "success",
        "nodes_executed": sorted(nodes_started),
    })


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC GENERATOR 2 — Full end-to-end pipeline
# ─────────────────────────────────────────────────────────────────────────────

async def stream_full_pipeline(
    incoming_trigger: Dict[str, Any],
    task_id: str | None = None,
) -> AsyncGenerator[str, None]:
    """
    Yields SSE events for the complete control testing pipeline:
      preprocessing → G01 graph → work order → ADK agent execution.
    """
    if task_id is None:
        task_id = str(uuid.uuid4())

    pipeline_start_time = time.time()

    # ── PHASE 1: Init ────────────────────────────────────────────────────────
    yield _emit("pipeline_start", {
        "task_id":    task_id,
        "control_id": incoming_trigger.get("control_id"),
        "cycle_id":   incoming_trigger.get("cycle_id"),
        "test_id":    incoming_trigger.get("test_id"),
        "message":    "Control testing pipeline accepted. Trigger validated and execution context initialised.",
    })

    # ── PHASE 2: Preprocessing ───────────────────────────────────────────────
    yield _emit("preprocessing_start", {
        "message": (
            "Resolving the detailed test specification from the control registry. "
            "Binding the full validation description to the execution payload."
        ),
    })

    try:
        processed_payload = preprocess_incoming_payload(incoming_trigger)
        processed_payload["test_id"] = int(incoming_trigger.get("test_id", 0))
    except Exception as exc:
        logger.error(f"[SSE/Full] Preprocessing failed: {exc}")
        yield _emit("error", {"phase": "preprocessing", "message": str(exc)})
        return

    description_len = len(processed_payload.get("test_description", ""))
    evidence_count  = len(processed_payload.get("evidence_filenames", []))

    yield _emit("preprocessing_complete", {
        "control_id":         processed_payload["control_id"],
        "cycle_id":           processed_payload["cycle_id"],
        "test_id":            processed_payload["test_id"],
        "test_description":   processed_payload["test_description"],
        "evidence_filenames": processed_payload.get("evidence_filenames", []),
        "message": (
            f"Test specification loaded. "
            f"{description_len} character validation context bound. "
            f"{evidence_count} pre-listed evidence file(s) in scope."
        ),
    })

    # ── PHASE 3: G01 LangGraph ───────────────────────────────────────────────
    yield _emit("graph_start", {
        **_G01_TOPOLOGY,
        "message": (
            "Launching G01 parallel analysis graph. "
            "Interpreter and Evidence Gatherer nodes executing simultaneously."
        ),
    })

    nodes_started: set = set()
    interpreter_result: Dict[str, Any] = {}
    evidence_result:    Dict[str, Any] = {}

    try:
        async for event in graph.astream_events(processed_payload, version="v2"):
            kind: str = event.get("event", "")
            node: str = event.get("name", "")

            if kind == "on_chain_start" and node in _LANGGRAPH_NODE_NAMES:
                if node not in nodes_started:
                    nodes_started.add(node)
                    node_messages = {
                        "interpreter":       "Classifying the test description against the methodology corpus. LLM inference in progress.",
                        "evidence_gatherer": "Scanning the test description for referenced evidence filenames. Validating file presence on disk.",
                    }
                    yield _emit("node_start", {
                        "node":    node,
                        "message": node_messages.get(node, "Node starting."),
                    })

            elif kind == "on_chain_end" and node == "interpreter":
                output = event.get("data", {}).get("output", {})
                interpreter_result = _to_dict(output.get("interpreter_result")) or {}
                test_type     = interpreter_result.get("test_type", "GENERIC")
                target_params = interpreter_result.get("target_parameters", [])

                yield _emit("node_complete", {
                    "node":    "interpreter",
                    "result":  interpreter_result,
                    "message": (
                        f"Test classified as '{test_type}'. "
                        f"{len(target_params)} target compliance parameter(s) extracted."
                    ),
                })

                methodology = get_methodology_for_category(test_type)
                tool_count  = len(methodology.get("expected_tools", []))
                yield _emit("methodology_resolved", {
                    "category":                test_type,
                    "title":                   methodology.get("title"),
                    "expected_tools":          methodology.get("expected_tools", []),
                    "classification_criteria": methodology.get("classification_criteria"),
                    "methodology_instructions":methodology.get("methodology_instructions"),
                    "message": (
                        f"Methodology playbook '{methodology.get('title')}' activated. "
                        f"{tool_count} compliance tool(s) assigned to this execution."
                    ),
                })

            elif kind == "on_chain_end" and node == "evidence_gatherer":
                output = event.get("data", {}).get("output", {})
                evidence_result = _to_dict(output.get("evidence_result")) or {}
                found = len(evidence_result.get("file_paths", []))

                yield _emit("node_complete", {
                    "node":    "evidence_gatherer",
                    "result":  evidence_result,
                    "message": (
                        f"{found} evidence file(s) verified and queued for agent analysis."
                        if found > 0
                        else "No directly referenced evidence files located. Agent will operate on available context."
                    ),
                })

    except Exception as exc:
        logger.error(f"[SSE/Full] Graph error: {exc}")
        yield _emit("error", {"phase": "graph_execution", "message": str(exc)})
        return

    yield _emit("graph_complete", {
        "status":         "success",
        "nodes_executed": sorted(nodes_started),
        "message": (
            "Analysis graph complete. "
            "Test category and evidence inventory finalised. Ready for agent dispatch."
        ),
    })

    # ── PHASE 4: Work order compilation ──────────────────────────────────────
    test_category  = interpreter_result.get("test_type", "GENERIC")
    evidence_paths = evidence_result.get("file_paths", [])

    work_order = {
        "task_id":          task_id,
        "test_id":          processed_payload["test_id"],
        "control_id":       processed_payload["control_id"],
        "cycle_id":         processed_payload["cycle_id"],
        "test_category":    test_category,
        "test_description": processed_payload["test_description"],
        "evidence_paths":   evidence_paths,
    }

    yield _emit("work_order_compiled", {
        "task_id":       task_id,
        "test_category": test_category,
        "evidence_count": len(evidence_paths),
        "message": (
            f"Work order packaged for '{test_category}' compliance agent. "
            f"{len(evidence_paths)} evidence file(s) included in the dispatch."
        ),
    })

    # ── PHASE 5: Agent routing ────────────────────────────────────────────────
    target_agent = _resolve_agent(test_category)
    agent_label  = _AGENT_LABELS.get(target_agent.name, target_agent.name)

    yield _emit("agent_selected", {
        "agent_name":    target_agent.name,
        "agent_label":   agent_label,
        "test_category": test_category,
        "message": (
            f"'{agent_label}' selected as the compliance execution engine. "
            f"Category routing: '{test_category}'."
        ),
    })

    # ── PHASE 6: ADK session & execution ─────────────────────────────────────
    session_service = InMemorySessionService()
    session = await session_service.create_session(
        app_name="control-testing",
        user_id="system-user",
        session_id=str(uuid.uuid4()),
    )

    yield _emit("agent_session_created", {
        "session_id": session.id,
        "message":    "Secure agent execution session initialised. Ingesting work order into the agentic layer.",
    })

    runner = Runner(
        agent=target_agent,
        app_name="control-testing",
        session_service=session_service,
    )

    new_message = genai_types.Content(
        role="user",
        parts=[genai_types.Part(text=json.dumps(work_order))],
    )

    yield _emit("agent_start", {
        "agent_name":  target_agent.name,
        "agent_label": agent_label,
        "message": (
            f"'{agent_label}' is now processing the work order. "
            "Tool invocations will be streamed as they occur."
        ),
    })

    final_response_text: str | None = None
    tool_call_count = 0

    try:
        async for event in runner.run_async(
            user_id="system-user",
            session_id=session.id,
            new_message=new_message,
        ):
            # Tool dispatched by the agent
            fn_calls = (
                event.get_function_calls()
                if hasattr(event, "get_function_calls")
                else []
            )
            for fc in (fn_calls or []):
                tool_call_count += 1
                tool_label = _TOOL_LABELS.get(fc.name, f"Executing tool '{fc.name}'")
                yield _emit("tool_call", {
                    "tool_name":   fc.name,
                    "call_number": tool_call_count,
                    "message":     tool_label,
                })

            # Tool result returned to agent
            fn_responses = (
                event.get_function_responses()
                if hasattr(event, "get_function_responses")
                else []
            )
            for fr in (fn_responses or []):
                tool_label = _TOOL_LABELS.get(fr.name, fr.name)
                yield _emit("tool_result", {
                    "tool_name": fr.name,
                    "message": (
                        f"'{tool_label}' — extraction complete. "
                        "Results handed off to the agent for compliance analysis."
                    ),
                })

            # Final agent response
            if getattr(event, "is_final_response", lambda: False)():
                final_response_text = _extract_text(event.content)

    except Exception as exc:
        logger.error(f"[SSE/Full] ADK execution error: {exc}")
        yield _emit("error", {"phase": "agent_execution", "message": str(exc)})
        return

    # ── PHASE 7: Result & pipeline complete ──────────────────────────────────
    execution_time_ms = int((time.time() - pipeline_start_time) * 1000)
    compliance_status = None
    audit_justification: str = ""

    if final_response_text:
        try:
            parsed = json.loads(final_response_text)
            compliance_status   = parsed.get("compliance_status")
            audit_justification = parsed.get("audit_justification", "")
        except Exception:
            audit_justification = final_response_text[:300]

    verdict = (
        "PASS" if compliance_status is True
        else "FAIL" if compliance_status is False
        else "INCONCLUSIVE"
    )

    print("\n" + "=" * 60)
    print(f"  COMPLIANCE VERDICT : {verdict}")
    print(f"  TASK ID            : {task_id}")
    print(f"  EXECUTION TIME     : {execution_time_ms}ms")
    print(f"  JUSTIFICATION      : {audit_justification[:300]}")
    print("=" * 60 + "\n")

    yield _emit("agent_complete", {
        "agent_name":         target_agent.name,
        "compliance_status":  compliance_status,
        "verdict":            verdict,
        "audit_justification": audit_justification,
        "tool_calls_made":    tool_call_count,
        "message": (
            f"Agent concluded with verdict: {verdict}. "
            f"{tool_call_count} tool invocation(s) executed during the compliance analysis."
        ),
    })

    yield _emit("pipeline_complete", {
        "task_id":            task_id,
        "execution_time_ms":  execution_time_ms,
        "compliance_status":  compliance_status,
        "verdict":            verdict,
        "message": (
            f"Control testing pipeline finished in {execution_time_ms}ms. "
            f"Final verdict: {verdict}."
        ),
    })
