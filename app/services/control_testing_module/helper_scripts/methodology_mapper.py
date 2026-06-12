# app/services/control_testing_module/helper_scripts/methodology_mapper.py

from typing import Dict, Any

# Always mention expected tools here for reference, but the actual execution of these tools is determined by the agent instruction templates in the agent suite definitions
# expected tools here need to be mentioned and mapped to the tools_registry again for reference 
TEST_METHODOLOGY_CORPUS: Dict[str, Dict[str, Any]] = {
    "CPT_PRICE_CHANGE_VALIDATION": {
        "title": "CPT Price Change Commentary Alignment Audit",
        "expected_tools": ["extract_price_change_entries_from_excel", "parse_image_and_get_extracted_text"],
        "classification_criteria": "Use this category ONLY when the description explicitly mentions auditing price change commentary, verifying that pricing modifications have associated commentary or annotations, or checking supply chain commentary for price modifications. The evidence is typically an Excel workbook containing price change records with commentary columns. Do NOT use this category simply because the description mentions a SAP condition type name (e.g. ZL01, ZF01) — condition type names also appear in IPE SAP screenshot tests; the distinguishing factor here is the presence of commentary/annotation validation against pricing records.",
        "methodology_instructions": """
        CRITICAL COMPLIANCE TESTING PROCEDURE:
        1. Use the tool 'extract_price_change_entries_from_excel' to extract structured price change entries from the workbook.
        2. The tool will automatically identify:
        - condition codes
        - item numbers
        - product names
        - price movement comments
        3. Validate that each detected entry contains:
        - an item number
        - a product name
        - a detected price movement comment
        4. If:
        - comment_present = true
            -> treat the entry as compliant
        - comment_present = false
            -> add the item into flagged_anomalies
        5. Multiple entries may exist under multiple condition codes.
        6. Populate:
        - total_price_modifications_found
        - uncommented_variants_count
        - flagged_anomalies
        - compliance_status
        - audit_justification
        7. compliance_status should be:
        true ONLY when all detected entries contain comments.
        8. If the control description references email sign-offs or approvals,
        DO NOT validate email evidence in this node.
        Mention the dependency in audit_justification only.
        9. Do not repeatedly invoke workbook extraction tools.
        Each workbook should only be processed once unless tool execution fails.
        10. After receiving the structured extraction output,
            return the final structured schema response immediately.
        """
    },
    "CPT_EMAIL_ANALYSIS": {
        "title": "CPT Sign-Off and Compliance Email Analysis",
        "expected_tools": ["analyse_email_evidence_directly_with_llm"],
        "classification_criteria": "Use this category when the description explicitly requests verification of stakeholder approvals, explicit sign-offs, email communications, review logs, or specific corporate timeline deadlines like Working Day metrics (e.g., WD15).",
        "methodology_instructions": """
        CRITICAL COMPLIANCE TESTING PROCEDURE:
        1. Parse the communication header, timestamp records, and text body using the 'analyse_email_evidence' tool.
        2. Validate the evidence contents dynamically against the precise operational thresholds demanded in the test description.
        3. Identify and verify critical structural markers:
           - Executive Sign-Offs: Check for explicit confirmation words or approval strings from key stakeholders on core data changes.
           - Specific Milestones/Deadlines: Isolate explicit corporate calendar markers or tracking windows (e.g., 'WD15' / Working Day 15).
        4. Pass/Fail Decision Criteria: The test achieves a 'Pass' status ONLY if the required sign-offs and structural windows matching the test criteria are actively confirmed within the email body context.
        """
    },
    "ROW_LEVEL_ANALYSIS": {
        "title": "Row-Level Validation Framework",
        "expected_tools": ["get_excel_details_for_row_level_analysis", "extract_image_table_details_for_row_level_analysis", "analyse_multiple_images_with_llm"],
        "classification_criteria": "Use this category when the description instructs to compare, match, or reconcile tabular records, spreadsheet rows, or line items between two distinct sources (such as an image table and an Excel sheet). This includes counting data rows, retrieving first/last rows, validating total row counts, confirming complete data transmission/completeness between evidence files, OR counting rows across multiple screenshots that match a specific column value or criterion (e.g. 'count rows where CnTy = ZF01 across all images'). Use this category for any multi-image row-counting task even if SAP condition codes like ZF01 or ZL01 are mentioned — the distinguishing factor is that the task is about counting or reconciling rows, not validating SAP GUI field parameters.",
        "methodology_instructions": """
        CRITICAL COMPLIANCE TESTING PROCEDURE:

        STEP 0 — READ THE TEST DESCRIPTION FIRST
        Read the test_description carefully before calling any tool. Identify:
        a) Whether the count is a TOTAL row count (count all rows) or a FILTERED row count
           (count only rows where a specific column contains a specific value).
        b) Whether evidence is image-based, spreadsheet-based, or both.

        TOOL SELECTION RULES — follow these before calling any tool:
        - Spreadsheet evidence → call 'get_excel_details_for_row_level_analysis' once per file.
        - Image evidence (any count task, filtered or total) → call
          'analyse_multiple_images_with_llm' ONCE, passing ALL image paths from
          evidence_paths as a list and writing a precise agent_user_prompt describing
          exactly what to count or verify. The tool embeds every image in one multimodal
          LLM request so the model sees them all simultaneously — no per-image iteration.
          Do NOT call this tool more than once.
        - Do NOT use 'extract_image_table_details_for_row_level_analysis' when the task
          requires filtering rows by a column value — it returns total row counts only and
          cannot filter by column value.

        HARD LOOP-PREVENTION RULE — non-negotiable:
        Make at most ONE tool call for all image evidence combined. After receiving the
        tool response, compile the final verdict immediately from your context without
        any further tool calls. Never retry a tool call for images.
        """
    },
    "IPE_SAP_IMAGE_VALIDATION": {
        "title": "IPE SAP GUI Presentation Layer Structural Inspection",
        "expected_tools": ["analyse_image_evidence_directly_with_llm", "parse_image_and_get_extracted_text", "analyse_image_evidence_for_tcode_with_llm"],
        "classification_criteria": "Use this category when verifying specific SAP GUI interface parameters or system attributes directly visible in a screenshot or image file. This includes: Sales Organisation, Condition Type (e.g. ZL01, ZF01, or any other SAP condition code), Validity Ranges/Dates, Type of Report, Transaction T-Codes, or bottom status ribbons. If the description names a single image file (e.g. IPE_3.jpg) and asks to check SAP field values like Condition Type, Sales Organisation, or Validity Range, always use this category. Do NOT use this if the primary task is counting rows across multiple screenshots, matching data row numbers, filtering rows by a column value, or validating commentary on price change records — those belong in ROW_LEVEL_ANALYSIS. The presence of a SAP condition code (ZF01, ZL01, ZA01) in the description alone is NOT sufficient to use this category if the task is a row count or row filter operation.",
        "methodology_instructions": """
        CRITICAL COMPLIANCE TESTING PROCEDURE:
        ══════════════════════════════════════════════════════════
        STEP 0 — READ THE TEST DESCRIPTION FIRST (MANDATORY)
        ══════════════════════════════════════════════════════════
        Before calling any tool, read the test_description in the work order.
        Identify the EXACT set of fields you are required to validate.
        This set — and ONLY this set — defines your compliance checklist.

        ══════════════════════════════════════════════════════════
        FIELD SCOPING RULES — NON-NEGOTIABLE
        ══════════════════════════════════════════════════════════
        1. Validate ONLY the fields explicitly named in the test_description.
           Do not validate any other field, regardless of what you see in the image.
        2. SAP screenshots contain many system-generated fields that are NOT part
           of the compliance check — for example: 'Created By', 'Changed By',
           'Created On', 'Last Changed By', 'Change Date', 'Last Changed On',
           'Processed By', 'Entered By'. These fields MUST be completely ignored
           unless the test_description explicitly names them.
        3. `interface_discrepancies_found` must be set to True ONLY when a field
           that IS in your compliance checklist fails validation. A field that is
           visible in the screenshot but NOT in the checklist can never cause
           `interface_discrepancies_found` to be True.
        4. compliance_status = False (FAIL) ONLY when a required field from the
           test_description is missing, ambiguous, or has an unexpected value.
           Fields outside the test_description checklist cannot cause a FAIL.

        ══════════════════════════════════════════════════════════
        EXTRACTION PROCEDURE (apply only to required fields)
        ══════════════════════════════════════════════════════════
        1. Process the visual evidence using OCR and spatial coordinate extractors.
        2. For each field that IS in your checklist, use the following spatial
           heuristics to locate it — these are extraction guides, not a mandatory
           scan list:
           - Sales Organisation: value in the main view pane. Example: GB10.
           - Condition Type: the alphanumeric code (e.g. ZA01, ZL01, ZF01) in the
             input cell immediately to the right of the 'Condition type' label row
             inside the SAP Selections panel. Extract the raw code exactly as it
             appears. CRITICAL: this is an image extraction step — you MUST read
             the value from the screenshot, never substitute the expected value
             from test_description. If you see any alphanumeric code in that cell,
             that is the extracted Condition Type — record it regardless of whether
             it matches the expected value. A blank or empty condition_type in the
             output is never acceptable when the label row is visible.
           - Validity Range: start/end dates adjacent to the label. Example: 01.10.2023 – 31.10.2023.
           - Type of Report: categorisation string adjacent to the label (e.g. Classical Report, ALV).
           - Transaction Code (T-Code): alphanumeric code, e.g. ZV231213 (8 chars).
             Check the main view pane first; if not found there, check the bottom-right
             system status ribbon of the SAP GUI window. Finding it in EITHER location
             counts as full confirmation — the ribbon is a valid and authoritative
             location for T-Code display in SAP.
           - Fiscal Year: year value in the evidence. Example: 2023.
        3. Parse the image with parse_image_and_get_extracted_text and look for
           the required field values in the extracted text.

        CONFIRMATION IS CONCLUSIVE — NON-NEGOTIABLE:
        Once a required field's value is found and matches the expected value via
        ANY tool call (including the T-Code fallback tool), that field is CONFIRMED.
        A confirmed field CANNOT be re-questioned for visibility or presentation
        in any subsequent reasoning step. Do not contradict a confirmation.

        T-CODE FALLBACK RULE (applies only when T-Code is a required field):
        If T-Code is in the checklist and you could not confirm it using
        analyse_image_evidence_directly_with_llm or parse_image_and_get_extracted_text,
        call analyse_image_evidence_for_tcode_with_llm EXACTLY ONCE.
        If that tool confirms the T-Code value, treat T-Code as PASSED — do not
        introduce any additional "visibility" or "presentation" check afterward.
        If it returns empty or unrecognised, mark T-Code as UNCONFIRMED and proceed
        immediately to generate the final structured output — do NOT call any tool
        again. Do NOT retry the fallback tool a second time under any circumstances.

        ══════════════════════════════════════════════════════════
        VERDICT RULES
        ══════════════════════════════════════════════════════════
        - compliance_status = True  → every required field is confirmed (found and
          matches the expected value, via any tool call).
        - compliance_status = False → at least one required field could not be
          confirmed by ANY available tool, or its extracted value does not match
          the expected value from the test_description.
        - A field is UNCONFIRMED only when all relevant tools have been exhausted
          and the value was still not found or did not match. Ambiguity introduced
          after a successful confirmation does NOT constitute an unconfirmed field.
        - Any field outside the test_description checklist has ZERO effect on
          the verdict in either direction.

        CONDITION TYPE — ANTI-HALLUCINATION RULE (non-negotiable):
        Before producing the final structured output, review the text returned
        by every tool call you have already made and locate any alphanumeric code
        adjacent to the words "Condition type" or "Condition Type".
        Set condition_type to that exact extracted code.
        Do NOT call any additional tool to find it — use only what prior tool
        calls have already returned. Do NOT copy the expected value from
        test_description into this field; only use values read from tool output.
        If after reviewing all prior tool output no condition type code is found,
        set condition_type to 'NOT_FOUND' and mark compliance_status False.
        A blank or empty string is never acceptable for this field."""
    },
    "GENERIC": {
        "title": "Standard Textual Control Validation Framework",
        "expected_tools": ["extract_text_from_document"],
        "classification_criteria": "Fallback category. Use this only if the description is standard line-by-line text verification or matching basic textual documents, and does not align with any specialized rules above.",
        "methodology_instructions": """
        CRITICAL COMPLIANCE TESTING PROCEDURE:
        1. Access the available raw evidence files (spreadsheets, logs, text extracts, or PDF documents).
        2. Execute a direct line-by-line verification comparing the key attributes found in the text against the control targets.
        3. Isolate transactional identifiers, user timestamps, or financial totals to confirm structural alignment.
        4. If all parameters extracted explicitly match the target criteria, issue a 'Pass' status; otherwise, document the specific variant anomalies.
        """
    }
}

def get_methodology_for_category(category_name: str) -> Dict[str, Any]:
    normalized_key = str(category_name).upper().strip()
    return TEST_METHODOLOGY_CORPUS.get(normalized_key, TEST_METHODOLOGY_CORPUS["GENERIC"])