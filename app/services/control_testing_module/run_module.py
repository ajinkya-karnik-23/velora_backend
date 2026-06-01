import logging
import asyncio
import uuid
import json
import time

from typing import Dict, Any

from google.adk.sessions import InMemorySessionService
from google.adk import Runner
from google.genai import types as genai_types

from app.db.session import AsyncSessionLocal
from app.models.control_test_result import ControlTestResult

from app.services.control_testing_module.lang_graphs.G01_analyse_payload import graph

from app.services.control_testing_module.helper_scripts.payload_preprocessor import (
    preprocess_incoming_payload,
)

import app.services.control_testing_module.google_agent_landscape.agent_suite as suite

logger = logging.getLogger("control_testing_module")


async def execute_module_pipeline(
    incoming_trigger: Dict[str, Any],
    task_id: str
):

    start = time.time()

    logger.info(
        f"Control Testing Started: "
        f"{incoming_trigger.get('control_id')}"
    )

    # STEP 1 — PREPROCESS
    processed_payload = preprocess_incoming_payload(
        incoming_trigger
    )

    processed_payload["test_id"] = int(
        incoming_trigger.get("test_id", 0)
    )

    # STEP 2 — GRAPH
    graph_final_state = await graph.ainvoke(
        processed_payload
    )

    interpreter_data = graph_final_state.get(
        "interpreter_result"
    )

    evidence_data = graph_final_state.get(
        "evidence_result"
    )

    # STEP 3 — WORK ORDER
    compiled_work_order_dict = {
        "task_id": task_id,
        "test_id": processed_payload["test_id"],
        "control_id": processed_payload["control_id"],
        "cycle_id": processed_payload["cycle_id"],
        "test_category": (
            interpreter_data.test_type
            if interpreter_data
            else "GENERIC"
        ),
        "test_description":
            processed_payload["test_description"],

        "evidence_paths": (
            evidence_data.file_paths
            if evidence_data
            else []
        )
    }

    # STEP 4 — ROUTING
    category = compiled_work_order_dict["test_category"]

    if category == "CPT_PRICE_CHANGE_VALIDATION":
        target_adk_agent = suite.default_CPT_PRICE_CHANGE_VALIDATION_agent

    elif category == "CPT_EMAIL_ANALYSIS":
        target_adk_agent = suite.default_CPT_EMAIL_ANALYSIS_agent

    elif category == "ROW_LEVEL_ANALYSIS":
        target_adk_agent = suite.default_ROW_LEVEL_ANALYSIS_agent

    elif category == "IPE_SAP_IMAGE_VALIDATION":
        target_adk_agent = suite.default_IPE_SAP_IMAGE_VALIDATION_agent

    else:
        target_adk_agent = suite.default_GENERIC_agent

    # STEP 5 — SESSION
    session_service = InMemorySessionService()

    session = await session_service.create_session(
        app_name="control-testing",
        user_id="system-user",
        session_id=str(uuid.uuid4())
    )

    runner = Runner(
        agent=target_adk_agent,
        app_name="control-testing",
        session_service=session_service
    )

    # STEP 6 — EXECUTE
    new_message = genai_types.Content(
        role="user",
        parts=[
            genai_types.Part(
                text=json.dumps(compiled_work_order_dict)
            )
        ]
    )

    final_response = None

    async for event in runner.run_async(
        user_id="system-user",
        session_id=session.id,
        new_message=new_message,
    ):

        if getattr(event, "is_final_response", lambda: False)():
            final_response = event.content.parts[0].text

    # STEP 7 — SAVE
    execution_time_ms = int(
        (time.time() - start) * 1000
    )

    parsed_response = json.loads(final_response)

    try:

        async with AsyncSessionLocal() as db_session:

            db_entry = ControlTestResult(
                task_id=compiled_work_order_dict["task_id"],
                test_id=compiled_work_order_dict["test_id"],
                control_id=compiled_work_order_dict["control_id"],
                cycle_id=compiled_work_order_dict["cycle_id"],
                compliance_test=str(
                    parsed_response.get(
                        "compliance_status",
                        False
                    )
                ),
                execution_time_ms=execution_time_ms,
                audit_justification=parsed_response.get(
                    "audit_justification",
                    ""
                )
            )

            db_session.add(db_entry)

            await db_session.commit()

    except Exception as e:

        logger.exception(
            f"DB save failed: {str(e)}"
        )

    return {
        "task_id": task_id,
        "result": parsed_response
    }