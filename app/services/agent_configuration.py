import base64
import json
import os
import mimetypes
from dotenv import load_dotenv
import litellm
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional, Dict, Any
from google.adk import Agent, Runner
from google.adk.sessions import Session
from google.adk.agents import SequentialAgent

load_dotenv()
model=os.getenv("MODEL1")
litellm_model=os.getenv("LITELLM_MODEL")

##############################################################################################################################
# Agent roles and instructions

assessment_agent_instruction = """
ROLE:
You are a Senior Control Testing Auditor validating evidence completeness,
accuracy, and reconciliation in an AI-assisted audit pipeline.

PRIMARY OBJECTIVE:
Read the test description carefully. Classify the test type. Use the appropriate
tools. Produce a structured assessment.

=========================================================
STEP 1 — CLASSIFY THE TEST TYPE
=========================================================

TYPE A — FIELD VALIDATION
Indicators: specific field values to verify (T-Code, Company Code, Date, Cost Center, G/L Account).
Examples: "Validate Company Code UK10", "Verify T-Code FB03".

TYPE B — ROW COUNT RECONCILIATION
Indicators: comparing records between Excel and screenshot, completeness of export,
row count matching, first/last row verification.
Examples: "Compare IPE row count against Excel", "Verify completeness of SAP extract".

TYPE C — NUMERICAL RECONCILIATION
Indicators: totals, sums, balances, amounts.
Examples: "Compare sum of Amount in local currency", "Reconcile Net balance".

TYPE D — CPT MANUAL REVIEW
Indicators: CPT flag, approvals, sign-offs, reviewer names, email confirmations.
Examples: "Confirm review by Jerzy Pron", "Inspect email approvals".

=========================================================
STEP 2 — TOOL USAGE BY TEST TYPE
=========================================================

TYPE A:
- Call 'extract_text_from_image' on the screenshot.
- Extract and compare each specific field value named in the test description.

TYPE B:
- Call 'get_excel_table_shape' to get: table_row_count, first_row_values, last_row_values.
- Call 'extract_table_structure_from_image' to get: table_row_count, first_row, last_row.
- ALWAYS compare row counts — this is the minimum for any Type B test.
- ONLY compare first_row and last_row if the test description EXPLICITLY asks for them.
- Do NOT invent first/last row comparisons if only row count was requested.

TYPE C:
- Call 'extract_text_from_image' on the screenshot to extract numerical values.
- Extract the specific totals or sums named in the test description.

TYPE D:
- Call 'extract_text_from_image' on each referenced evidence file.
- Look for the specific names, roles, approval language, dates described in the test description.
- Verify each attribute listed independently.

=========================================================
CRITICAL FILE-TYPE TO TOOL MAPPING RULES
=========================================================
- Files ending in .xlsx or .xls are spreadsheets. You MUST ONLY use 'get_excel_table_shape' on them. NEVER call 'extract_text_from_image' on an Excel file.
- Files ending in .jpg, .jpeg, or .png are screenshots. You MUST use 'extract_text_from_image' or 'extract_table_structure_from_image' on them.
- If a tool returns an output containing "Error", do not run the same tool again. Mark the check as a Fail.

=========================================================
STEP 3 — DECISION LOGIC
=========================================================

PASS — ALL explicitly requested validations match.

FAIL — ANY of:
- Any explicitly requested value does not match.
- Row counts do not reconcile (Type B).
- A required field is not found in the evidence.
- A tool call returns success: false.
- detection_confidence is "low" from extract_table_structure_from_image.

=========================================================
STEP 4 — OUTPUT REQUIREMENTS
=========================================================

You MUST return exactly three fields:

STATUS:
- "Pass" or "Fail" only.

EVALUATION_SUMMARY:
- A single paragraph.
- Name every check performed, the expected value, and the actual value found.
- Explicitly use the words "matches" or "mismatch" for each check.
- Do not omit any check from the summary.

VALIDATION_METADATA:
A list of dicts. Use the structure appropriate for the test type.

Type A example:
[
  {"field_name": "Company Code", "expected_value": "UK10", "actual_value": "UK10", "match": true},
  {"field_name": "Date From", "expected_value": "01.01.2024", "actual_value": "01.01.2024", "match": true}
]

Type B — row count only (when test description does not mention first/last row):
[
  {"check": "row_count", "excel_rows": 3, "image_rows": 3, "match": true}
]

Type B — row count + first/last (only when test description explicitly requests it):
[
  {"check": "row_count", "excel_rows": 142, "image_rows": 142, "match": true},
  {"check": "first_row", "excel_first_row": "100245", "image_first_row": "100245", "match": true},
  {"check": "last_row", "excel_last_row": "100587", "image_last_row": "100587", "match": true}
]

Type C example:
[
  {"value_name": "Amount in local currency", "excel_value": "1234.56", "screenshot_value": "1234.56", "match": true}
]

Type D example:
[
  {"attribute": "Reviewer", "expected": "Jerzy Pron", "found": "Jerzy Pron", "verified": true},
  {"attribute": "Approval sign-off", "expected": "present", "found": "Signed off by Jerzy Pron on 15.03.2024", "verified": true}
]

=========================================================
CRITICAL RULES
=========================================================

- NEVER hallucinate values. Use "Not Found" if a value is absent.
- NEVER estimate row counts manually. Always use tool outputs for counts.
- NEVER perform first/last row comparisons unless the test description explicitly requests them.
- If a tool returns success: false, mark the test as Fail and explain.
- If detection_confidence is "low", mark as Fail.
- Use "matches" and "mismatch" consistently in evaluation_summary.
"""

evidence_gatherer_instruction = """
Given the test description, your task is to extract the names of the evidence required for testing. The test description may 
contain references to various pieces of evidence (e.g., 'screenshot1.jpeg', 'document2.pdf') that are necessary to perform 
the control test. Moreover, you should retrieve the paths of these evidence files from the evidence pool using the 'get_evidence' tool.
The output must be a JSON object with this structure:
{
  "evidence_names": ["List of evidence filenames extracted from the test description"],
  "evidence_paths": ["List of paths returned by the get_evidence tool"]
}
NOTE: When using the 'get_evidence' tool, you need to fetch the metadata for the test from the 'test_metadata' variable, which includes the control_id, cycle_id, test_id, and whether it's a CPT. Use this metadata to construct the correct paths for fetching evidence.
"""
cpt_interpretation_instruction = """
You are a CPT Interpretation Agent. Your task is to analyze the provided control test details and determine the relevant evidence needed for testing. 
        
        STEPS:
        1. Identify the filenames of the evidence required (e.g., 'screenshot1.jpeg') from the test description.
        2. Call the 'get_evidence' tool with these filenames to retrieve their validated paths.
        3. Formulate the final test steps.

        The output must be a JSON object with this structure:
        {
          "test_steps": "Summarized test steps here",
          "evidence_paths": ["List of paths returned by the get_evidence tool"]
        }
"""
##############################################################################################################################
# Tools
# ---------------------------------------------
class Tools:

    # def get_evidence(self, evidence_filenames: List[str]) -> List[str]:
    #     """
    #     Iterates through input filenames and returns a list of relative 
    #     paths formatted as 'landing_folder/filename'.
    #     """
    #     # TODO: Put this in .env and make it dynamic
    #     target_dir = f"ciq-evidence-{os.getenv('APP_ENV')}"
    #     base_path = os.getenv("LOCAL_STORAGE_PATH")  
        
    #     found_evidence = []
    #     for filename in evidence_filenames:
    #         full_path = os.path.join(base_path, target_dir, filename)
    #         # TODO: update logic for the new path
    #         if os.path.isfile(full_path):
    #             relative_path = f"{target_dir}/{filename}"
    #             found_evidence.append(relative_path)
    #         else:
    #             print(f"Warning: File {filename} not found in {base_path}")
    #     return found_evidence
    
    def get_evidence(
            self, 
            cycle_id: str, 
            control_number: str, 
            test_id: str, 
            evidence_filenames: List[str]
        ) -> List[str]:
        """
        Constructs & returns file paths for evidence based on the testing details.
        
        Args:
            cycle_id: The unique ID of the current test cycle (e.g., '4').
            control_number: The control identifier (e.g., 'CTRL0020526').
            test_id: The specific test ID used as a prefix (e.g., '88').
            
        Returns:
            A list of validated relative paths in the format 'cycle_id/control_number/test_id_filename'.
        """
        base_path = os.getenv("LOCAL_STORAGE_PATH", "./storage")
        found_evidence = []

        for filename in evidence_filenames:
            # Construct the path segment: cycle_id/control_number/test_id_filename
            # Example result: 4/CTRL0020526/88_sample_document.pdf
            relative_dir = os.path.join(cycle_id, control_number)
            prefixed_filename = f"{test_id}_{filename}"
            
            # Full path for system check
            full_path = os.path.join(base_path, relative_dir, prefixed_filename)
            
            if os.path.isfile(full_path):
                # Return the relative path as required by your frontend/storage logic
                relative_path = os.path.join(relative_dir, prefixed_filename)
                found_evidence.append(relative_path)
            else:
                print(f"Warning: File {prefixed_filename} not found in {relative_dir}")
                
        return found_evidence
    
    def extract_text_from_image(self, evidence_path: str) -> str:

        """Reads an image from local storage and extracts OCR text using a vision model."""
        base_path = os.getenv("LOCAL_STORAGE_PATH", "./storage")
        full_path = os.path.join(base_path, evidence_path)

        if not os.path.exists(full_path):
            return f"Error: File not found at {full_path}"

        # Check extension explicitly to prevent passing Excel binaries to Vision APIs
        if evidence_path.lower().endswith(('.xlsx', '.xls')):
            return "Error: Cannot extract text from an Excel file using an image tool. Use get_excel_table_shape instead."

        try:
            mime_type, _ = mimetypes.guess_type(full_path)
            if mime_type is None or not mime_type.startswith('image/'):
                return f"Error: File type {mime_type} is not a valid image format."

            with open(full_path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode("utf-8")

            data_url = f"data:{mime_type};base64,{encoded_string}"

            response = litellm.completion(
                model=os.getenv("LITELLM_MODEL"),
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Transcribe all text from this image. Specifically identify T-Codes, Company Codes, Dates, and any tabular data.",
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": data_url},
                            },
                        ],
                    }
                ],
            )
            return response.choices[0].message.content

        except Exception as e:
            # Instead of generic string returns that keep the agent guessing, 
            # return a definitive instruction structural message
            return f"Tool Execution Failure: {str(e)}. Stop trying to read this file with this tool."
      
    def get_excel_table_shape(self, evidence_path: str) -> dict:
        """
        Reads an Excel file from local storage and returns:
        - dataframe shape (rows = data rows only, header excluded)
        - number of data rows
        - column names
        - first_row_values: dict of {column: value} for the first data row
        - last_row_values:  dict of {column: value} for the last data row

        Args:
            evidence_path: Relative path to the Excel file.

        Returns:
            dict containing shape metadata and first/last row data.
        """

        base_path = os.getenv("LOCAL_STORAGE_PATH", "./storage")
        full_path = os.path.join(base_path, evidence_path)

        if not os.path.exists(full_path):
            return {
                "success": False,
                "error": f"File not found at {full_path}"
            }

        try:
            df = pd.read_excel(full_path)
            rows, cols = df.shape

            # str() wrapping handles pandas types (Timestamp, numpy int/float, NaN)
            first_row_values = (
                {col: str(val) for col, val in df.iloc[0].to_dict().items()}
                if rows > 0 else None
            )
            last_row_values = (
                {col: str(val) for col, val in df.iloc[-1].to_dict().items()}
                if rows > 0 else None
            )

            return {
                "success": True,
                "file_path": full_path,
                "shape": {
                    "rows": rows,
                    "columns": cols
                },
                "table_row_count": rows,
                "column_names": df.columns.tolist(),
                "first_row_values": first_row_values,
                "last_row_values": last_row_values,
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
        
    def extract_table_structure_from_image(self, evidence_path: str) -> dict:
        """
        Uses a vision LLM to count DATA rows in a screenshot and extract
        the first and last row content. Ignores SAP UI chrome elements
        (menu bars, toolbars, column headers, status bars, separator lines).
        """

        base_path = os.getenv("LOCAL_STORAGE_PATH", "./storage")
        full_path = os.path.join(base_path, evidence_path)

        if not os.path.exists(full_path):
            return {
                "success": False,
                "error": f"File not found at {full_path}"
            }

        try:
            mime_type, _ = mimetypes.guess_type(full_path)
            if mime_type is None:
                return {
                    "success": False,
                    "error": f"Unsupported or unknown image type for {full_path}"
                }

            with open(full_path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode("utf-8")

            data_url = f"data:{mime_type};base64,{encoded_string}"

            prompt = (
                "You are analyzing a SAP or enterprise UI screenshot that contains a data table. "
                "Count ONLY the actual DATA rows in the table. Do NOT count:\n"
                "  - The menu bar at the top of the screen\n"
                "  - Toolbars or icon rows\n"
                "  - The column header row (the row containing column names)\n"
                "  - Horizontal separator lines or dividers between UI sections\n"
                "  - The status bar at the bottom of the screen\n"
                "  - Any row that does not contain actual record data\n\n"
                "A DATA row is a row that contains a record with values in multiple columns "
                "(e.g. a document number, a date, an amount, a cost center, etc.).\n\n"
                "Return ONLY a valid JSON object with exactly these four keys:\n"
                "  \"row_count\": integer — number of data rows counted\n"
                "  \"first_row\": string — full text of the first data row, reading left to right\n"
                "  \"last_row\": string — full text of the last data row, reading left to right\n"
                "  \"confidence\": string — \"high\" or \"low\" based on how clearly the table is visible\n\n"
                "Do not include any explanation or prose. Return only the JSON object."
            )

            response = litellm.completion(
                model=os.getenv("LITELLM_MODEL"),
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ],
                    }
                ],
            )

            raw_content = response.choices[0].message.content.strip()

            # Strip markdown code fences if the model wraps JSON in them
            if raw_content.startswith("```"):
                raw_content = raw_content.split("```")[1]
                if raw_content.startswith("json"):
                    raw_content = raw_content[4:]
                raw_content = raw_content.strip()

            parsed = json.loads(raw_content)
            row_count = int(parsed.get("row_count", 0))

            return {
                "success": True,
                "file_path": full_path,
                "table_detected": row_count > 0,
                "table_row_count": row_count,
                "first_row": parsed.get("first_row"),
                "last_row": parsed.get("last_row"),
                "detection_confidence": parsed.get("confidence", "low"),
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Vision LLM table extraction failed: {str(e)}"
            }
    
##############################################################################################################################
# Agents

tool_box = Tools()

# 1 - "Evidence Gatherer Agent" : Extracts the names of the evidence required for testing from the test description and retrieves their paths from the evidence pool.

class EvidenceGathererAgentInputSchema(BaseModel):
    test_description: str

class EvidenceGathererAgentOutputSchema(BaseModel):
    evidence_names: List[str]
    evidence_paths: List[str]

def create_evidence_gatherer():
    return Agent(
        name="evidence_gatherer_agent",
        model=litellm_model,
        instruction=evidence_gatherer_instruction,
        tools=[tool_box.get_evidence],
        input_schema=EvidenceGathererAgentInputSchema,
        output_schema=EvidenceGathererAgentOutputSchema,
        output_key="evidence_gatherer_output"
    )



# ----------------------------------------------

# 2 - "Assessment Agent" : Evaluates the test results and determines pass/fail status based on the evidence and test steps.

class AssessmentAgentInputSchema(BaseModel):
    cycleID: str
    control_number: List[str]


class ValidationRecord(BaseModel):
    """
    A single validation check. Fields are Optional so the agent fills only
    what is relevant to the current test type, while the fixed schema satisfies
    OpenAI structured-output requirements (additionalProperties: false).
    """
    # This enforces "additionalProperties": false at the item level cleanly for Pydantic v2
    model_config = ConfigDict(extra="forbid")

    # Shared
    match: Optional[bool] = Field(default=None, description="True if check passed, False otherwise")

    # Type A — field validation
    field_name: Optional[str] = Field(default=None)
    expected_value: Optional[str] = Field(default=None)
    actual_value: Optional[str] = Field(default=None)

    # Type B — row count reconciliation
    check: Optional[str] = Field(default=None)
    excel_rows: Optional[int] = Field(default=None)
    image_rows: Optional[int] = Field(default=None)
    excel_first_row: Optional[str] = Field(default=None)
    image_first_row: Optional[str] = Field(default=None)
    excel_last_row: Optional[str] = Field(default=None)
    image_last_row: Optional[str] = Field(default=None)

    # Type C — numerical reconciliation
    value_name: Optional[str] = Field(default=None)
    excel_value: Optional[str] = Field(default=None)
    screenshot_value: Optional[str] = Field(default=None)

    # Type D — CPT manual review
    attribute: Optional[str] = Field(default=None)
    expected: Optional[str] = Field(default=None)
    found: Optional[str] = Field(default=None)
    verified: Optional[bool] = Field(default=None)


class AssessmentAgentOutputSchema(BaseModel):
    """
    Output schema for the assessment agent following explicit structural guidelines.
    """
    # This enforces "additionalProperties": false on the main response wrapper object
    model_config = ConfigDict(extra="forbid")

    status: str = Field(
        description="Overall test result. Must be exactly 'Pass' or 'Fail'."
    )
    evaluation_summary: str = Field(
        description=(
            "A single detailed paragraph describing every validation performed, "
            "the values found, and the outcome. Must explicitly state whether each "
            "check matched or mismatched."
        )
    )
    validation_metadata: List[ValidationRecord] = Field(
        description=(
            "Adaptive list of validation records. Fill only fields relevant to the "
            "test type — leave all others null. "
            "Type A: set field_name/expected_value/actual_value/match. "
            "Type B: set check/excel_rows/image_rows/match; add first_row/last_row "
            "records only if explicitly requested. "
            "Type C: set value_name/excel_value/screenshot_value/match. "
            "Type D: set attribute/expected/found/verified."
        )
    )

def create_assessment_agent():
    return Agent(
        name="assessment_agent",
        model=litellm_model,
        instruction=assessment_agent_instruction,
        input_schema=AssessmentAgentInputSchema,
        output_schema=AssessmentAgentOutputSchema,
        tools=[tool_box.extract_text_from_image, tool_box.get_excel_table_shape, tool_box.extract_table_structure_from_image],
        output_key="assessment_agent_output"
    )

# ----------------------------------------------

# 3 - "CPT Interpretation Agent" : Analyzes control test details and determines relevant evidence.

class CptInterpreterInputSchema(BaseModel):
    filenames: List[str]

class CptInterpreterOutputSchema(BaseModel):
    test_steps: str
    evidence_paths: List[str]

cpt_interpreter = Agent(
        name = "cpt_interpretation_agent",
        model = litellm_model,
        input_schema = CptInterpreterInputSchema,
        instruction = cpt_interpretation_instruction,
        tools=[tool_box.get_evidence], #TODO: Define and add tools if needed for CPT interpretation
        output_schema = CptInterpreterOutputSchema,
        output_key = "cpt_interpretation_output"
    )

##############################################################################################################################
# Workflows

ipe_workflow = SequentialAgent(
    name="IPE_Testing_Pipeline",
    sub_agents=[create_evidence_gatherer(), create_assessment_agent()]
)

cpt_workflow = SequentialAgent(
    name="Control_Testing_Pipeline",
    sub_agents=[cpt_interpreter, create_evidence_gatherer(), create_assessment_agent()]
)

#############################################################################################################################

# from the frontend
input_json = [
    {
      "clientID": "CLIENT_001",
      "engagementID": "ENG_2026_001",
      "cycleID": "CYCLE_001",
      "controlID": "CTRL0037345",
      "versionID": "VER_001",
      "testID": "T0001",
      "testDescription": "Validate input parameters for IPE1 GL 23040100: Company Code UK10, Date 01.01.2024 to 31.03.2024.",
      "evidencePath": "landing_folder/37345_IPE1.jpg",
      "evidenceID": "EVID_001",
      "CPT": False,
      "testing":{
        "test_completion": False,
        "test_result": None,
        "result_justification": None
      }
    },
    {
      "clientID": "CLIENT_001",
      "engagementID": "ENG_2026_001",
      "cycleID": "CYCLE_001",
      "controlID": "CTRL0037345",
      "versionID": "VER_001",
      "testID": "T0002",
      "testDescription": "Validate input parameters for IPE2 GL 23040100: Cost Center 9934, Date 01.01.2024 to 31.03.2024.",
      "evidencePath": "landing_folder/37345_IPE2.jpg",
      "evidenceID": "EVID_002",
      "CPT": False,
      "testing":{
        "test_completion": False,
        "test_result": None,
        "result_justification": None
      }      
    },
    {
      "clientID": "CLIENT_001",
      "engagementID": "ENG_2026_001",
      "cycleID": "CYCLE_001",
      "controlID": "CTRL0037345",
      "versionID": "VER_001",
      "testID": "T0003",
      "testDescription": "Compare IPE3 totals: Sum of 'Amount in local currency' from Excel vs SAP screenshot yellow panel.",
      "evidencePath": "landing_folder/37345_IPE3.jpg",
      "evidenceID": "EVID_003",
      "CPT": False,
      "testing":{
        "test_completion": False,
        "test_result": None,
        "result_justification": None
      }
    },
    {
      "clientID": "CLIENT_001",
      "engagementID": "ENG_2026_001",
      "cycleID": "CYCLE_001",
      "controlID": "CTRL0037345",
      "versionID": "VER_001",
      "testID": "T0004",
      "testDescription": "Validate input parameters for IPE4 GL 23020100: G/L 23020100, Company Code UK10, Date 01.01.2024 to 31.03.2024.",
      "evidencePath": "landing_folder/37345_IPE4.jpg",
      "evidenceID": "EVID_004",
      "CPT": False,
      "testing":{
        "test_completion": False,
        "test_result": None,
        "result_justification": None
      }
    },
    {
      "clientID": "CLIENT_001",
      "engagementID": "ENG_2026_001",
      "cycleID": "CYCLE_001",
      "controlID": "CTRL0037345",
      "versionID": "VER_001",
      "testID": "T0005",
      "testDescription": "Compare IPE5 totals: Sum of 'Amount in local currency' from Excel vs SAP screenshot yellow panel.",
      "evidencePath": "landing_folder/37345_IPE5.jpg",
      "evidenceID": "EVID_005",
      "CPT": False,
      "testing":{
        "test_completion": False,
        "test_result": None,
        "result_justification": None
      }
    },
    {
      "clientID": "CLIENT_001",
      "engagementID": "ENG_2026_001",
      "cycleID": "CYCLE_001",
      "controlID": "CTRL0037345",
      "versionID": "VER_001",
      "testID": "T0006",
      "testDescription": "Attribute A: Verify variance < $10M in CPT1.xlsx and confirmation of review by Jerzy Pron in CPT1.jpg.",
      "evidencePath": "landing_folder/37345_CPT1.jpg",
      "evidenceID": "EVID_006",
      "CPT": True,
      "testing":{
        "test_completion": False,
        "test_result": None,
        "result_justification": None
      }
    },
    {
      "clientID": "CLIENT_001",
      "engagementID": "ENG_2026_001",
      "cycleID": "CYCLE_001",
      "controlID": "CTRL0037345",
      "versionID": "VER_001",
      "testID": "T0007",
      "testDescription": "Attribute B: Reconcile 'Total Invoice' (Excel) with 'Net balance due to MSD' (CPT2a.jpg) and TradeAccruals (CPT2b.jpg).",
      "evidencePath": "landing_folder/37345_CPT2a.jpg",
      "evidenceID": "EVID_007",
      "CPT": True,
      "testing":{
        "test_completion": False,
        "test_result": None,
        "result_justification": None
      }
    },
    {
      "clientID": "CLIENT_001",
      "engagementID": "ENG_2026_001",
      "cycleID": "CYCLE_001",
      "controlID": "CTRL0037345",
      "versionID": "VER_001",
      "testID": "T0008",
      "testDescription": "Attribute C: Inspect email approvals for settlement from Train, Huan and Kara McNulty to Kudenga, Tonderai.",
      "evidencePath": "landing_folder/37345_CPT3a.jpg",
      "evidenceID": "EVID_008",
      "CPT": True,
      "testing":{
        "test_completion": False,
        "test_result": None,
        "result_justification": None
      }
    },
    {
      "clientID": "CLIENT_001",
      "engagementID": "ENG_2026_001",
      "cycleID": "CYCLE_001",
      "controlID": "CTRL0037345",
      "versionID": "VER_001",
      "testID": "T0009",
      "testDescription": "Attribute D: Reconcile Debit Amount from CPT4a.jpg with Net Balance and bank details (Beneficiary/IBAN) in CPT2a.jpg.",
      "evidencePath": "landing_folder/37345_CPT4a.jpg",
      "evidenceID": "EVID_009",
      "CPT": True,
      "testing":{
        "test_completion": False,
        "test_result": None,
        "result_justification": None
      }
    }
]

# postman>
# [
#   {
#     "clientID": "CLIENT_001",
#     "engagementID": "ENG_2026_001",
#     "cycleID": "CYCLE_001",
#     "controlID": "CTRL0037345",
#     "versionID": "VER_001",
#     "testID": "T0001",
#     "testDescription": "Validate input parameters for IPE1 GL 23040100: Company Code UK10, Date 01.01.2024 to 31.03.2024.",
#     "evidencePath": "37345_IPE1.jpg",
#     "evidenceID": "EVID_001",
#     "CPT": false,
#     "testing": {
#       "test_completion": false,
#       "test_result": null,
#       "result_justification": null
#     }
#   },
#   {
#     "testID": "T0002",
#     "testDescription": "Validate input parameters for IPE2 GL 23040100: Cost Center 9934, Date 01.01.2024 to 31.03.2024.",
#     "evidencePath": "37345_IPE2.jpg",
#     "CPT": false,
#     "testing": { "test_completion": false, "test_result": null, "result_justification": null }
#   }
# ]