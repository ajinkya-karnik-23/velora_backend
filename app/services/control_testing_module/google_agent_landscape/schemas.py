from typing import List, Dict, Any, Optional
from pydantic import BaseModel, ConfigDict, Field

# =====================================================================
# UNIFIED AGENT LANDSCAPE INPUT SCHEMA
# =====================================================================

class AgentWorkOrderInput(BaseModel):
    """
    Standardized immutable work-order payload passed into every
    specialized compliance testing agent.
    """

    test_id: int = Field(
        description=(
            "Unique identifier of the audit test execution."
        )
    )

    control_id: str = Field(
        description=(
            "Corporate control identifier associated with the audit test "
            "(example: CTRL0020526)."
        )
    )

    cycle_id: int = Field(
        description=(
            "Identifier of the audit cycle or testing period "
            "under which the evidence is being validated."
        )
    )

    test_category: str = Field(
        description=(
            "Dynamic test classification used to route execution "
            "to the correct compliance validation agent."
        )
    )

    test_description: str = Field(
        description=(
            "Complete baseline testing instructions and compliance "
            "requirements that the agent must validate."
        )
    )

    evidence_paths: List[str] = Field(
        description=(
            "List of evidence file paths available for analysis. "
            "Paths are relative to the configured local storage directory."
        )
    )


# =====================================================================
# AGENT-SPECIFIC STRUCTURED OUTPUT SCHEMAS
# =====================================================================

class StrictBaseModel(BaseModel):
    """
    Strict schema base model that forbids unexpected fields
    in structured LLM outputs.
    """
    model_config = ConfigDict(extra='forbid')


class FlaggedAnomaly(StrictBaseModel):

    variant_id: str = Field(
        description=(
            "Unique identifier, item number, or row reference "
            "associated with the detected anomaly."
        )
    )

    issue_type: str = Field(
        description=(
            "Short categorical label describing the anomaly type "
            "(example: Missing Comment, Price Mismatch, Invalid Structure)."
        )
    )

    description: str = Field(
        description=(
            "Detailed explanation of the anomaly detected during validation."
        )
    )

    expected_price: Optional[float] = Field(
        default=None,
        description=(
            "Expected baseline price identified from the audit logic "
            "or source evidence, if applicable."
        )
    )

    actual_price: Optional[float] = Field(
        default=None,
        description=(
            "Actual extracted price detected in the evidence, "
            "if applicable."
        )
    )


class PriceChangeValidationOutput(StrictBaseModel):

    compliance_status: bool = Field(
        description=(
            "True when all detected price change entries contain "
            "valid commentary and no material anomalies exist."
        )
    )

    audited_spreadsheet: str = Field(
        description=(
            "Relative path or filename of the Excel workbook "
            "analyzed during validation."
        )
    )

    total_price_modifications_found: int = Field(
        description=(
            "Total number of detected 3-line price change blocks "
            "This will be found in the 'detected_price_change_blocks' key of the output given by the 'extract_price_change_entries' tool."
        )
    )

    uncommented_variants_count: int = Field(
        description=(
            "Number of detected price change entries where "
            "the expected comment or justification was missing."
        )
    )

    flagged_anomalies: List[FlaggedAnomaly] = Field(
        default_factory=list,
        description=(
            "Structured list of all anomalies, mismatches, "
            "or incomplete records detected during analysis."
        )
    )

    audit_justification: str = Field(
        description=(
            "A comprehensive paragraph that must cover two parts. "
            "Part 1 — Individual line items: for each price change entry reviewed, "
            "state the condition code, item number, whether a valid comment was present, "
            "and any anomaly detected. "
            "Part 2 — Overall conclusion: a single clear statement declaring whether the "
            "control passed or failed, citing the total number of entries reviewed, "
            "how many were compliant, and the primary reason for the verdict. "
            "Write in plain professional prose — no bullet points or headers."
        )
    )


class EmailAnalysisOutput(StrictBaseModel):

    compliance_status: bool = Field(
        description=(
            "True when the required stakeholder approvals and "
            "timeline conditions are successfully verified."
        )
    )

    stakeholder_approvals_verified: List[str] = Field(
        description=(
            "List of stakeholder names, roles, or email identities "
            "whose approvals or acknowledgements were confirmed."
        )
    )

    timeline_deadline_met: bool = Field(
        description=(
            "True when the evidence confirms that the review "
            "or approval activity occurred before the required deadline."
        )
    )

    audit_justification: str = Field(
        description=(
            "A comprehensive paragraph covering two parts. "
            "Part 1 — Individual findings: for each stakeholder approval or timeline "
            "condition checked, state what was verified, what was found in the evidence, "
            "and whether it satisfied the requirement. "
            "Part 2 — Overall conclusion: a single clear statement declaring pass or fail, "
            "referencing which approvals were confirmed, whether the deadline was met, "
            "and the primary reason for the verdict. "
            "Write in plain professional prose — no bullet points or headers."
        )
    )


class RowLevelAnalysisOutput(StrictBaseModel):
    """
    Structured output schema for row-level reconciliation
    and cross-source comparison validations.
    """

    compliance_status: bool = Field(
        description=(
            "True when row-level reconciliation checks pass successfully."
        )
    )

    source_row_count: int = Field(
        description=(
            "Total number of rows identified in the source dataset."
        )
    )

    target_row_count: int = Field(
        description=(
            "Total number of rows identified in the target dataset."
        )
    )

    row_counts_match: bool = Field(
        description=(
            "True when the source and target datasets contain "
            "matching row counts."
        )
    )

    first_row_aligned: bool = Field(
        description=(
            "True when the first compared rows match correctly "
            "between the datasets."
        )
    )

    last_row_aligned: bool = Field(
        description=(
            "True when the last compared rows match correctly "
            "between the datasets."
        )
    )

    discrepancy_details: Optional[str] = Field(
        default=None,
        description=(
            "Optional explanation describing detected row-level "
            "mismatches or reconciliation failures."
        )
    )

    audit_justification: str = Field(
        description=(
            "A comprehensive paragraph covering two parts. "
            "Part 1 — Individual findings: state the source row count, target row count, "
            "whether the first and last rows aligned, and any specific row-level discrepancies found. "
            "Part 2 — Overall conclusion: a single clear statement declaring pass or fail, "
            "citing the counts compared, what matched or mismatched, and the primary reason for the verdict. "
            "Write in plain professional prose — no bullet points or headers."
        )
    )


class SapImageValidationOutput(StrictBaseModel):
    """
    Structured output schema for SAP GUI image
    and screenshot validation workflows.
    """

    compliance_status: bool = Field(
        description=(
            "True when all expected SAP interface fields "
            "and values are successfully validated."
        )
    )

    extracted_t_code: str = Field(
        description=(
            "SAP transaction code extracted from the image evidence."
        )
    )

    sales_organisation: str = Field(
        description=(
            "Sales organisation value extracted from the SAP screen."
        )
    )

    condition_type: str = Field(
        description=(
            "The EXACT condition type code read directly from the SAP Selections panel "
            "in the image — the alphanumeric value (e.g. ZA01, ZL01, ZF01) that appears "
            "in the cell immediately to the right of the 'Condition type' label row. "
            "This is a RAW EXTRACTION field: populate it with what the image shows, "
            "never with the expected value copied from test_description. "
            "If the label row is visible and contains a code, that code must appear here — "
            "this field must NOT be left blank or set to an empty string. "
            "Only set to 'NOT_FOUND' if the 'Condition type' label row is genuinely "
            "absent from the screenshot after all tool calls have been exhausted."
        )
    )

    validity_range: str = Field(
        description=(
            "Validity period or date range identified in the SAP evidence."
        )
    )

    interface_discrepancies_found: bool = Field(
        description=(
            "True when missing fields, visual inconsistencies, "
            "or unexpected SAP interface deviations are detected."
        )
    )

    audit_justification: str = Field(
        description=(
            "A comprehensive paragraph covering two parts. "
            "Part 1 — Individual field findings: for EACH field explicitly named in the "
            "test_description (and only those fields — do not mention any others), "
            "state the expected value, the actual extracted value, and whether it matched. "
            "Part 2 — Overall conclusion: a single clear statement declaring pass or fail, "
            "listing only the required fields that were confirmed or failed, and the primary "
            "reason for the verdict. Do NOT mention fields that were not in the test_description. "
            "Write in plain professional prose — no bullet points or headers."
        )
    )


class GenericValidationOutput(StrictBaseModel):
    """
    Generic fallback structured output schema used for
    non-specialized compliance validation workflows.
    """

    compliance_status: bool = Field(
        description=(
            "True when the generic validation checks complete successfully."
        )
    )

    files_processed: List[str] = Field(
        description=(
            "List of evidence files analyzed during the validation process."
        )
    )

    matched_attributes_count: int = Field(
        description=(
            "Total number of attributes, parameters, or fields "
            "successfully matched against the validation criteria."
        )
    )

    audit_justification: str = Field(
        description=(
            "A comprehensive paragraph covering two parts. "
            "Part 1 — Individual findings: for each attribute, parameter, or line item verified, "
            "state what was checked, what was found in the evidence, and whether it matched. "
            "Part 2 — Overall conclusion: a single clear statement declaring pass or fail, "
            "citing the total attributes reviewed, how many matched, and the primary reason for the verdict. "
            "Write in plain professional prose — no bullet points or headers."
        )
    )