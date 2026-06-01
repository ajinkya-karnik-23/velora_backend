# app/services/control_testing_module/helper_scripts/payload_preprocessor.py

import os
import json
import logging
from typing import Dict, Any
from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger("control_testing_module")

def preprocess_incoming_payload(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Looks up the actual validation description from localized JSON configuration files
    based on control_id and testID, injecting it directly into the execution state payload.
    """
    # 1. Normalize and extract incoming key parameters a
    control_id = item.get("control_id") or item.get("controlID")
    current_test_id = item.get("test_id") or item.get("testID")
    cycle_id = item.get("cycle_id") or item.get("cycleID")
    is_cpt = item.get("is_cpt") or item.get("CPT", False)

    logger.info(f"⚡ [Preprocessor] Resolving metadata for Control: {control_id} | Test ID: {current_test_id}")

    # 2. Extract configuration path from system environment variables
    detailed_jsons_path = os.getenv("DETAILED_JSONS_PATH")
    if not detailed_jsons_path:
        error_msg = "DETAILED_JSONS_PATH environment variable is missing from your .env settings configuration."
        logger.error(error_msg)
        raise ValueError(error_msg)

    json_file_path = os.path.join(detailed_jsons_path, f"{control_id}.json")

    # 3. Validate presence of the required mapping file
    if not os.path.exists(json_file_path):
        error_msg = f"Reference target description file '{control_id}.json' not found at location: {json_file_path}"
        logger.error(error_msg)
        raise FileNotFoundError(error_msg)

    # 4. Open and read structural content arrays from the target reference JSON file
    try:
        with open(json_file_path, "r", encoding="utf-8") as file:
            detailed_json = json.load(file)
    except json.JSONDecodeError as parse_err:
        logger.error(f"Failed to compile JSON structure inside {json_file_path}: {parse_err}")
        raise parse_err

    validations_list = detailed_json.get("validations", [])

    # 5. Extract the matching validation description using your list search heuristic
    mapped_test_description = next(
        (
            validation.get("validation_desc")
            for validation in validations_list
            if str(validation.get("test_id")) == str(current_test_id)
        ),
        None
    )

    if not mapped_test_description:
        error_msg = f"No validation_desc match found inside {control_id}.json for target test_id: '{current_test_id}'"
        logger.error(error_msg)
        raise KeyError(error_msg)

    # 6. Build a standardized operational payload copy for the LangGraph pipeline
    processed_payload = {
        "control_id": control_id,
        "cycle_id": int(cycle_id) if cycle_id is not None else 0,
        "test_id": int(current_test_id) if current_test_id is not None else "Not found",
        "test_description": mapped_test_description,
        # Preserve file listings passed down from endpoint queries
        "evidence_filenames": item.get("evidence_filenames", [])
    }

    logger.info("✅ [Preprocessor] High-fidelity validation description parsed and bound to workflow state successfully.")
    return processed_payload