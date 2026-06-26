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
        SAP SCREENSHOT VALIDATION — keep this simple.

        NON-NEGOTIABLES:
        1. The test_description defines your checklist. Validate ONLY the fields it
           explicitly names — nothing else.
        2. Fields visible in the screenshot but NOT named in the test_description
           are OUT OF SCOPE. They can NEVER cause a FAIL or set
           interface_discrepancies_found. Ignore system-generated fields like
           'Created By', 'Changed By', 'Created On', 'Last Changed By' unless named.
        3. Read every value from the image. Never copy the expected value from the
           test_description into an extracted field.

        FIELDS IN SCOPE = exactly those listed in the test_description. Where to find them:
           - Sales Organisation: main view pane (e.g. GB10).
           - Condition Type: alphanumeric code in the cell right of the 'Condition type'
             label in the SAP Selections panel (e.g. ZA01, ZL01, ZF01).
           - Validity Range: start/end dates next to the label (e.g. 01.10.2023 – 31.10.2023).
           - Type of Report: string next to the label (e.g. Classical Report, ALV).
           - Transaction Code (T-Code): main view pane OR the bottom-right status
             ribbon — either location is authoritative (e.g. ZV231213).
           - Fiscal Year: year value in the evidence (e.g. 2023).

        TOOL-CALL BUDGET:
        - One evidence file → ONE tool call. Do not re-process the same image.
        - The ONLY exception: if the test_description requires BOTH OCR extraction
          AND LLM visual ingestion, call parse_image_and_get_extracted_text once AND
          analyse_image_evidence_directly_with_llm once (one call each).
        - T-Code only: if a required T-Code is not confirmed by the above, call
          analyse_image_evidence_for_tcode_with_llm EXACTLY ONCE as a fallback.
        - Never retry a tool. Once a field's value is found via any call, it is
          CONFIRMED — do not re-question it.

        REASONING RULES:
        - compliance_status = True  → every required field was found and its value
          matches the expected value.
        - compliance_status = False → a required field is missing, or its extracted
          value does not match the expected value.
        - Out-of-scope fields have ZERO effect on the verdict in either direction.
        - Do not introduce extra 'visibility' or 'presentation' checks after a
          confirmation. After tools are exhausted, emit the final output immediately."""
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