# app/services/control_testing_module/lang_graphs/A01_analyse_payload_graph.py

import os
from typing import Dict, Any
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
import logging
import re

logger = logging.getLogger("control_testing_module")

from app.services.control_testing_module.lang_graphs.schemas import (
    G01_graph_state,
    InterpreterOutput,
    EvidenceGathererOutput,
)
from app.services.control_testing_module.helper_scripts.methodology_mapper import (
    TEST_METHODOLOGY_CORPUS,
)


async def interpreter_node(state: G01_graph_state) -> Dict[str, Any]:
    """
    Parses test description targets via structured JSON schemas bound
    to fully dynamic corpus keys and operational classification criteria guidance.
    """
    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.0
    ).with_structured_output(
        InterpreterOutput,
        method="json_schema"
    )

    # Programmatically compile the strict category guidelines directly from mapper records
    category_bullet_points = ""

    for key, data in TEST_METHODOLOGY_CORPUS.items():
        criteria = data.get(
            "classification_criteria",
            "Standard auditing procedures apply."
        )

        category_bullet_points += (
            f"- {key}:\n"
            f"  GUIDELINE: {criteria}\n\n"
        )

    prompt = (
        f"You are a compliance classification engine.\n"
        f"Analyze and categorize this specific test description requirement:\n"
        f"\"\"\"{state.test_description}\"\"\"\n\n"
        f"Map this target description strictly into one of these available "
        f"system keys by applying their strict guidelines:\n\n"
        f"{category_bullet_points}"
        f"Select the key that matches the operational intent perfectly. "
        f"If no specialized guidelines apply, default to 'GENERIC'."
    )

    result = await llm.ainvoke([HumanMessage(content=prompt)])

    return {"interpreter_result": result}


async def evidence_gatherer_node(state: G01_graph_state) -> Dict[str, Any]:
    """
    Dynamically extracts evidence filenames directly mentioned within the
    test description text, validates their existence, and returns
    relative storage paths.
    """

    # Project root (CIQ_Backend)
    CURRENT_FILE_PATH = os.path.abspath(__file__)

    ROOT_DIR = os.path.abspath(
        os.path.join(
            os.path.dirname(CURRENT_FILE_PATH),
            "../../../.."
        )
    )
    
    found_evidence = []

    cycle_str = str(state.cycle_id)
    control_str = str(state.control_id)
    test_str = str(state.test_id)

    # Extract filenames from description
    filename_pattern = r"[\w\-]+\.(?:xlsx|xls|jpg|jpeg|png|pdf|csv)"

    extracted_filenames = re.findall(
        filename_pattern,
        state.test_description,
        re.IGNORECASE
    )

    # Deduplicate while preserving order
    unique_filenames = list(dict.fromkeys(extracted_filenames))

    logger.info(
        f"🔎 [Evidence Gatherer] Extracted targets from description: "
        f"{unique_filenames}"
    )

    for filename in unique_filenames:

        # Example: 1/CTRL0020207
        from app.core.local_storage import _container_name
        a = _container_name()
        relative_dir = os.path.join(
            a,
            cycle_str,
            control_str
        )

        # Example: 120_screenshot3.jpg
        prefixed_filename = f"{test_str}_{filename}"

        # Pathing fix for downstream ctm module
        # Fix - make paths seperate for nodes 
        relative_path = os.path.join(
            # "./storage",
            relative_dir,
            prefixed_filename
        )
        # Fix - making path seperate for search
        relative_path_for_search = os.path.join(
            "./storage",
            relative_dir,
            prefixed_filename
        )

        # Absolute path only for filesystem validation
        # absolute_path = os.path.join(
        #     ROOT_DIR,
        #     relative_path
        # )

        # if os.path.isfile(absolute_path):
        if os.path.isfile(relative_path_for_search):
            logger.info(
                f"✅ [Evidence Gatherer] Found verified relative path: "
                f"{relative_path_for_search}"
            )
            # # Store relative path instead of absolute path
            found_evidence.append(relative_path)
            
        # if os.path.isfile(absolute_path):
        #     logger.info(
        #          f"✅ [Evidence Gatherer] Found verified absolute path: "
        #               f"{absolute_path}"
        #             )
        #     # TEMPORARY: Store absolute path for downstream testing
        #     found_evidence.append(absolute_path)

        else:
            logger.warning(
                f"⚠️ [Evidence Gatherer] Identified description target "
                f"'{prefixed_filename}' but it does not exist at: "
                f"{relative_path}"
            )

    output = EvidenceGathererOutput(
        status=len(found_evidence) > 0,
        file_paths=found_evidence
    )

    return {"evidence_result": output}


# =====================================================================
# COMPILE CONTROL TREE GRAPH
# =====================================================================

builder = StateGraph(G01_graph_state)

builder.add_node("interpreter", interpreter_node)
builder.add_node("evidence_gatherer", evidence_gatherer_node)

# Fork concurrently out of START boundary lines
builder.add_edge(START, "interpreter")
builder.add_edge(START, "evidence_gatherer")

# Recombine and terminate graph processing streams cleanly
builder.add_edge("interpreter", END)
builder.add_edge("evidence_gatherer", END)

graph = builder.compile()