# app/services/control_testing_module/google_agent_landscape/tools_repository.py

from typing import List, Dict, Callable, Union
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
import logging
logger = logging.getLogger("control_testing_module")

# -----------------------------------------------------------------
# 1. ATOMIC ADK COMPLIANCE TOOLS IMPLEMENTATIONS
# -----------------------------------------------------------------
# app/services/control_testing_module/google_agent_landscape/tools_repository.py

import os
import json
import base64
import mimetypes
import logging
from typing import List, Dict, Callable, Union, Optional, Any
from dotenv import load_dotenv
import litellm
import pandas as pd

logger = logging.getLogger("control_testing_module")

class Tools:
    def __init__(self) -> None:
        """Initializes the consolidated compliance tool landscape."""
        pass

    def analyse_email_evidence(self, evidence_path: Union[str, List[str]], agent_user_prompt: str = "") -> str:
        """
        Ingests screenshot image of an email, converts it into a high-fidelity data URL, 
        and leverages a vision-capable LLM to analyze headers, timestamps, approval signatures, 
        and thread context as dictated by the agent's user request.

        Args:
            evidence_path: Relative path to the Excel file.
            agent_user_prompt: User prompt dynamically given by the agent as per requirement

        Returns:
            The llm response. (response.choices[0].message.content)

        """
        base_path = os.getenv("LOCAL_STORAGE_PATH", "./storage")
        
        # Handle both individual path strings or single-element list inputs gracefully
        if isinstance(evidence_path, list):
            if not evidence_path:
                return "Error: Provided file paths array list is empty."
            evidence_path = evidence_path[0]

        full_path = os.path.join(base_path, str(evidence_path).strip())
        logger.info(f"📧 [Email Tool] Opening image snapshot record path: {full_path}")

        # 1. Structural File Integrity Boundaries
        if not os.path.exists(full_path):
            return f"Error: File not found at target location: {full_path}"

        if full_path.lower().endswith(('.xlsx', '.xls', '.csv')):
            return "Error: Cannot extract communication text from binary tabular data files. Use spreadsheet tools instead."

        try:
            # 2. Extract and validate MIME type encoding footprints
            mime_type, _ = mimetypes.guess_type(full_path)
            if mime_type is None or not mime_type.startswith('image/'):
                return f"Error: File type '{mime_type}' is not a valid image/screenshot format."

            # 3. Read file and encode binary stream to base64
            with open(full_path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode("utf-8")

            data_url = f"data:{mime_type};base64,{encoded_string}"

            # 4. Define explicit internal tool environment boundaries
            system_instruction = (
                "You are an expert Forensic Email Evidence Analyst. Your objective is to extract audit points "
                "from email communication screenshot threads (Outlook, Gmail, Teams, etc.). "
                "Pay absolute attention to crucial corporate tracking indicators:\n"
                "  - Sender / Recipient fields (look for domain anomalies or external addresses)\n"
                "  - Explicit Timestamps and dates (verify if communication fits inside target windows)\n"
                "  - Clear sign-off phrases, approvals, financial periods (eg. WD15 etc.), text agreements, and sign-off names\n\n"
                "Focus exclusively on objective text visible within the screenshot chrome window bounds. "
                "Do not interpret implicit permissions or guess data outside the visible layout frame." \
                "Only analyze the content that is explicitly visible in the image. Do not make assumptions about email content that is not clearly shown in the screenshot."
                "Return information of whats asked. If the user prompt is empty, just extract all relevant structural details without trying to infer intent."
            )

            # Fallback prompt if the calling agent provides an empty instruction turn
            final_user_query = agent_user_prompt if agent_user_prompt.strip() else "Extract all structural details from this email confirmation."

            # 5. Execute vision inference pass via LiteLLM
            response = litellm.completion(
                model=os.getenv("LITELLM_MODEL"),
                messages=[
                    {
                        "role": "system",
                        "content": system_instruction
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": final_user_query},
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ],
                    }
                ],
            )
            
            return response.choices[0].message.content

        except Exception as e:
            logger.error(f"❌ [Email Tool] Vision tracking lookup failed: {e}", exc_info=True)
            return f"Tool Execution Failure: {str(e)}. Stop trying to analyze this file with this tool."
        
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
            ext = os.path.splitext(full_path)[1].lower()
            engine = "openpyxl" if ext == ".xlsx" else "xlrd" if ext == ".xls" else "openpyxl"
            df = pd.read_excel(full_path, engine=engine)
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

        Extracts structural data metrics from an enterprise UI screenshot using a vision LLM.

        This tool visually filters out application chrome elements (such as menu bars, 
        toolbars, headers, separators, and status bars) to isolate, count, and capture 
        the boundary data rows of an embedded data table.

        Args:
            evidence_path (str): Relative file system path to the screenshot image 
                artifact (e.g., SAP or Oracle interface capture) stored inside the 
                local storage boundary.

        Returns:
            dict: A structured response dictionary containing the extraction status and metrics.
                - success (bool): True if parsing completed successfully, False otherwise.
                - file_path (str, optional): The resolved absolute or full local path to the file.
                - table_detected (bool, optional): True if one or more actual data rows were identified.
                - table_row_count (int, optional): Total number of valid data record rows counted.
                - first_row (str, optional): Verbatim text string of the first visible data row.
                - last_row (str, optional): Verbatim text string of the last visible data row.
                - detection_confidence (str, optional): VLM self-reported assessment ("high" or "low").
                - error (str, optional): Breakdown message explaining the failure if success is False.
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

    def parse_excel_raw(self, file_paths: List[str]) -> List[str]:
        """
        Produces a high-fidelity structural representation of the workbook.
        Preserves empty rows, empty cells, and exact spreadsheet ordering. 
        Used to get the semantic understanding of the sheet.


        """

        base_path = os.getenv("LOCAL_STORAGE_PATH", "./storage")

        if isinstance(file_paths, str):
            file_paths = [file_paths]

        combined_reports = []

        for evidence_path in file_paths:

            full_path = os.path.join(base_path, str(evidence_path).strip())

            logger.info(f"📊 [Excel Raw Parser] Processing: {full_path}")

            if not os.path.exists(full_path):
                combined_reports.append(
                    f"FILE ERROR: Missing spreadsheet at path: {full_path}"
                )
                continue

            try:
                ext = os.path.splitext(full_path)[1].lower()
                engine = "openpyxl" if ext == ".xlsx" else "xlrd" if ext == ".xls" else "openpyxl"
                excel_file = pd.ExcelFile(full_path, engine=engine)

                workbook_report = [
                    f"### RAW SPREADSHEET ARCHIVE: {os.path.basename(full_path)}"
                ]

                for sheet in excel_file.sheet_names:

                    df = pd.read_excel(
                        full_path,
                        sheet_name=sheet,
                        dtype=str,
                        keep_default_na=False,
                        engine=engine,
                    )

                    workbook_report.append(
                        f"\nWorksheet: '{sheet}' | Shape: {df.shape[0]} Rows x {df.shape[1]} Columns"
                    )

                    headers = []

                    for idx, col in enumerate(df.columns):

                        col_name = str(col).strip()

                        if col_name.startswith("Unnamed:") or col_name == "":
                            headers.append(f"Column_{idx}[EMPTY]")
                        else:
                            headers.append(col_name)

                    workbook_report.append(
                        "Columns:\n  [ " + " | ".join(headers) + " ]"
                    )

                    workbook_report.append("\nRow Ledger:")

                    for row_idx, row in df.iterrows():

                        row_values = []

                        for value in row.values:

                            value_str = str(value).strip()

                            if value_str == "" or value_str.lower() == "nan":
                                row_values.append("[EMPTY]")
                            else:
                                row_values.append(value_str)

                        workbook_report.append(
                            f"Row {row_idx + 1}: " + " | ".join(row_values)
                        )

                combined_reports.append("\n".join(workbook_report))

            except Exception as exc:

                logger.exception(
                    f"[Excel Raw Parser] Failed processing: {full_path}"
                )

                combined_reports.append(
                    f"EXTRACTION FAILURE for {os.path.basename(full_path)}: {str(exc)}"
                )

        return combined_reports
    
    
    def extract_price_change_entries(self, file_paths: List[str]) -> Union[dict, str]:
        """
        Extracts structured price change blocks from Excel workbooks.

        Detects vertical 3-line pricing patterns:
            [ITEM NUMBER]
            [PRODUCT NAME]
            [COMMENT]

        Example:
            100010417
            IMFINZI INJ 500MG VI 1X10ML GB
            Imfinzi 500mg moving from £1556.05 to £1013

        Also detects pricing condition codes:
        - ZL01
        - ZF01
        - ZA01
        - ZF01 Hierarchy

        Args:
            file_paths (List[str]): List of Excel workbook relative paths.

        Returns:
            dict or str: The computed analytics dictionary, or "this excel was empty" 
                         if no valid pricing modifications were located.
        """
        import re
        import os
        import pandas as pd

        base_path = os.getenv("LOCAL_STORAGE_PATH", "./storage")

        if isinstance(file_paths, str):
            file_paths = [file_paths]

        extracted_entries = []
        item_pattern = re.compile(r"^\d{7,12}$")

        known_condition_codes = [
            "ZL01",
            "ZF01",
            "ZA01",
            "ZF01 Hierarchy"
        ]

        for evidence_path in file_paths:
            full_path = os.path.join(base_path, str(evidence_path).strip())
            logger.info(f"📈 [Price Entry Extractor] Processing: {full_path}")

            if not os.path.exists(full_path):
                extracted_entries.append({
                    "file": full_path,
                    "error": "File not found"
                })
                continue

            try:
                ext = os.path.splitext(full_path)[1].lower()
                engine = "openpyxl" if ext == ".xlsx" else "xlrd" if ext == ".xls" else "openpyxl"
                excel_file = pd.ExcelFile(full_path, engine=engine)
                workbook_entities = {
                    "file": os.path.basename(full_path),
                    "condition_codes_found": [],
                    "detected_price_change_blocks": [],
                    "analytics": {},
                    "extraction_status": "completed"
                }

                for sheet in excel_file.sheet_names:
                    df = pd.read_excel(
                        full_path,
                        sheet_name=sheet,
                        header=None,
                        dtype=str,
                        keep_default_na=False,
                        engine=engine,
                    )

                    # Scan every column independently
                    for col_idx in range(df.shape[1]):
                        column_values = [
                            str(v).strip()
                            for v in df.iloc[:, col_idx].tolist()
                        ]

                        current_condition = None

                        # Detect condition code in column
                        for value in column_values:
                            for condition in known_condition_codes:
                                if condition.lower() in value.lower():
                                    current_condition = condition
                                    if condition not in workbook_entities["condition_codes_found"]:
                                        workbook_entities["condition_codes_found"].append(condition)

                        # Scan vertically for 3-line blocks
                        for row_idx in range(len(column_values)):
                            current_value = column_values[row_idx]

                            if item_pattern.match(current_value):
                                item_number = current_value
                                product_name = (
                                    column_values[row_idx + 1]
                                    if row_idx + 1 < len(column_values)
                                    else None
                                )
                                comment = (
                                    column_values[row_idx + 2]
                                    if row_idx + 2 < len(column_values)
                                    else None
                                )

                                workbook_entities["detected_price_change_blocks"].append({
                                    "condition_code": current_condition,
                                    "item_number": item_number,
                                    "product_name": product_name,
                                    "comment": comment
                                })

                # ==========================================================
                # ANALYTICS CALCULATION
                # ==========================================================
                detected_blocks = workbook_entities["detected_price_change_blocks"]
                total_price_modifications_found = len(detected_blocks)

                uncommented_variants = [
                    block for block in detected_blocks
                    if not block.get("comment") or not str(block.get("comment")).strip()
                ]
                uncommented_variants_count = len(uncommented_variants)

                unique_condition_codes_with_changes = list({
                    block.get("condition_code")
                    for block in detected_blocks
                    if block.get("condition_code")
                })

                workbook_entities["analytics"] = {
                    "total_price_modifications_found": total_price_modifications_found,
                    "uncommented_variants_count": uncommented_variants_count,
                    "unique_condition_codes_with_changes": unique_condition_codes_with_changes,
                    "all_variants_have_comments": uncommented_variants_count == 0,
                    "compliance_status": uncommented_variants_count == 0
                }

                extracted_entries.append(workbook_entities)

            except Exception as exc:
                logger.exception(f"[Price Entry Extractor] Failed processing: {full_path}")
                extracted_entries.append({
                    "file": os.path.basename(full_path),
                    "error": str(exc)
                })

        # ==========================================================
        # STRUCTURAL EVALUATION & RETURN MATCH
        # ==========================================================
        if not extracted_entries:
            return "this excel was empty"

        # Safe dictionary lookup for the primary target file
        first_file_analytics = extracted_entries[0].get("analytics", {})
        
        # Verify if any actual modifications were added to the metric tracking matrix
        if first_file_analytics.get("total_price_modifications_found", 0) == 0:
         return "this excel was empty"

        return first_file_analytics
    
    def extract_text_from_image(self, evidence_path: str) -> str:
        """Reads an image from local storage and extracts OCR text using a vision model."""
        base_path = os.getenv("LOCAL_STORAGE_PATH", "./storage")
        full_path = os.path.join(base_path, evidence_path)

        if not os.path.exists(full_path):
            return f"Error: File not found at {full_path}"

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
                                "text": "Extract all visible text from this image using OCR. Return only the raw text without any explanation or formatting.",
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
         return f"Tool Execution Failure: {str(e)}. Stop trying to read this file with this tool."
        
    def analyse_image_evidence(self, evidence_path: Union[str, List[str]], agent_user_prompt: str = "") -> str:
        """
        Ingests a compliance image screenshot, converts it into a high-fidelity base64 data URL, 
        and leverages a vision-capable LLM acting as a Compliance Officer to audit corporate 
        tracking parameters, layouts, and data points as specified by the agent's prompt.
        """
        base_path = os.getenv("LOCAL_STORAGE_PATH", "./storage")
        
        if isinstance(evidence_path, list):
            if not evidence_path:
                return "Error: Provided file paths array list is empty."
            evidence_path = evidence_path[0]

        full_path = os.path.join(base_path, str(evidence_path).strip())
        logger.info(f"🔍 [Image Compliance Tool] Opening snapshot record path: {full_path}")

        if not os.path.exists(full_path):
            return f"Error: File not found at target location: {full_path}"

        if full_path.lower().endswith(('.xlsx', '.xls', '.csv')):
            return "Error: Cannot run visual compliance checks on binary tabular datasets. Use spreadsheet tools instead."

        try:
            mime_type, _ = mimetypes.guess_type(full_path)
            if mime_type is None or not mime_type.startswith('image/'):
                return f"Error: File type '{mime_type}' is not a valid image/screenshot format."

            with open(full_path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode("utf-8")

            data_url = f"data:{mime_type};base64,{encoded_string}"

            system_instruction = """You are an expert Corporate Compliance and Audit Officer. Your objective is to meticulously examine evidence screenshots, interface panels, and system logs to verify adherence to internal controls, regulatory policies, and operational workflows. Pay strict attention to administrative markers, timestamps, active transaction attributes, user permissions, and configuration details. Focus exclusively on objective, visible data contained within the screenshot bounds. Do not extrapolate information, interpret implicit authorization markers, or assume actions that are not explicitly shown in the interface image. Report what is explicitly verified. If the user query is left blank, perform a baseline structural extraction of all compliance-relevant elements."""

            final_user_query = agent_user_prompt if agent_user_prompt.strip() else "Perform a comprehensive compliance audit extraction on this image. CRITICAL EXTRACTION TASK: 1) 1. Search the entire screenshot for SAP transaction codes.2) 4. If no T-Code is visible, explicitly state "


            # if the final user query (given by the agent has a mention of the tcode, then I want to append this prompt with addition information. I need fuzzy match for the same, or regex)
            
            response = litellm.completion(
                model=os.getenv("LITELLM_MODEL"),
                messages=[
                    {
                        "role": "system",
                        "content": system_instruction
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": final_user_query},
                            {"type": "image_url", "image_url": {"url": data_url}},
                            # add a base64 reference image of the image at path: data/detailed_jsons/references/T-Code Reference.png as part of the prompt only if T code is mentioned in the agent query
                        ],
                    }
                ],
            )
            
            return response.choices[0].message.content

        except Exception as e:
            logger.error(f"❌ [Image Compliance Tool] Visual lookup failed: {e}", exc_info=True)
            return f"Tool Execution Failure: {str(e)}. Stop trying to analyze this file with this tool."

    def analyse_image_evidence_for_tcode(
            self,
            evidence_path: Union[str, List[str]],
            agent_user_prompt: str = ""
        ) -> str:
            """
            Ingests a compliance image screenshot, converts it into a high-fidelity
            base64 data URL, and leverages a vision-capable LLM acting as a
            Compliance Officer to audit corporate tracking parameters, layouts,
            and data points as specified by the agent's prompt.

            Additional Enhancement:
            -----------------------
            If the agent prompt contains a SAP T-Code reference (example: VA01,
            SU01, FB60, ME23N etc.), the tool automatically injects a reference
            image into the multimodal prompt to help the model understand and
            validate SAP transaction code layouts/screens.
            """

            import os
            import re
            import base64
            import mimetypes

            base_path = os.getenv("LOCAL_STORAGE_PATH", "./storage")

            if isinstance(evidence_path, list):
                if not evidence_path:
                    return "Error: Provided file paths array list is empty."
                evidence_path = evidence_path[0]

            full_path = os.path.join(base_path, str(evidence_path).strip())

            logger.info(
                f"🔍 [Image Compliance Tool] Opening snapshot record path: {full_path}"
            )

            if not os.path.exists(full_path):
                return f"Error: File not found at target location: {full_path}"

            if full_path.lower().endswith((".xlsx", ".xls", ".csv")):
                return (
                    "Error: Cannot run visual compliance checks on binary "
                    "tabular datasets. Use spreadsheet tools instead."
                )

            try:
                mime_type, _ = mimetypes.guess_type(full_path)

                if mime_type is None or not mime_type.startswith("image/"):
                    return (
                        f"Error: File type '{mime_type}' "
                        f"is not a valid image/screenshot format."
                    )

                # ---------------------------------------------------------
                # Encode primary evidence image
                # ---------------------------------------------------------
                with open(full_path, "rb") as image_file:
                    encoded_string = base64.b64encode(
                        image_file.read()
                    ).decode("utf-8")

                data_url = f"data:{mime_type};base64,{encoded_string}"

                system_instruction = """
SPECIAL SAP T-CODE EXTRACTION RULES:

SAP transaction codes may appear in:
- the top command field
- the screen title
- the bottom-left status bar
- the bottom-right status ribbon
- navigation breadcrumbs
- transaction entry boxes

A valid SAP T-Code usually:
- starts with Z, Y, VA, ME, FB, XK, SU etc.
- contains uppercase letters + digits
- examples:
  VA01
  SU01
  ME23N
  FB60
  XK03
  ZV231213

You MUST explicitly search the ENTIRE screenshot for possible T-Codes.

If multiple codes are visible:
- prioritize the bottom SAP ribbon
- then command field
- then title bar

If a likely T-Code is found:
- return it explicitly
- include exact screen location where it was found
- include confidence level
   
    """

                final_user_query = (
                    agent_user_prompt.strip()
                    if agent_user_prompt.strip()
                    else "Perform a comprehensive compliance audit extraction on this image."
                )

                # ---------------------------------------------------------
                # Detect SAP T-Code Mention
                # ---------------------------------------------------------
                #
                # Examples detected:
                # SU01
                # VA01
                # ME23N
                # FB60
                # XK03
                # tcode VA01
                # transaction code SU01
                #
                # Flexible regex with fuzzy phrasing support.
                # ---------------------------------------------------------

                tcode_pattern = re.compile(
                r"""
                (?:
                    t[\-\s]?code |
                    transaction\s?code |
                    tcodes? |
                    transaction
                )?
                \s*
                [:\-]?
                \s*
                \b
                ([A-Z]{1,5}\d{2,10}[A-Z]?)
                \b
                """,
                re.IGNORECASE | re.VERBOSE,
            )

                detected_tcodes = tcode_pattern.findall(final_user_query)

                logger.info(
                    f"🧾 [Image Compliance Tool] Detected T-Codes: {detected_tcodes}"
                )

                # ---------------------------------------------------------
                # Construct multimodal user content
                # ---------------------------------------------------------

                user_content = [
                    {
                        "type": "text",
                        "text": final_user_query
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": data_url
                        },
                    },
                ]

                # ---------------------------------------------------------
                # Inject Reference Image if T-Code Mentioned
                # ---------------------------------------------------------

                if detected_tcodes:

                    reference_image_path = (
                        "data/detailed_jsons/references/T-Code Reference.png"
                    )

                    if os.path.exists(reference_image_path):

                        ref_mime_type, _ = mimetypes.guess_type(
                            reference_image_path
                        )

                        with open(reference_image_path, "rb") as ref_file:
                            ref_encoded = base64.b64encode(
                                ref_file.read()
                            ).decode("utf-8")

                        ref_data_url = (
                            f"data:{ref_mime_type};base64,{ref_encoded}"
                        )

                        logger.info(
                            "📌 [Image Compliance Tool] "
                            "Injecting SAP T-Code reference image."
                        )

                        user_content.append(
                            {
                                "type": "text",
                                "text": (
                                    "Reference SAP T-Code guidance image "
                                    "provided below. Use it ONLY as supporting "
                                    "layout/context information for validating "
                                    "the uploaded evidence screenshot for finding and validating the T-Code."
                                ),
                            }
                        )

                        user_content.append(
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": ref_data_url
                                },
                            }
                        )

                    else:
                        logger.warning(
                            "⚠️ [Image Compliance Tool] "
                            "T-Code reference image not found."
                        )

                # ---------------------------------------------------------
                # LLM Call
                # ---------------------------------------------------------

                response = litellm.completion(
                    model=os.getenv("LITELLM_MODEL"),
                    messages=[
                        {
                            "role": "system",
                            "content": system_instruction,
                        },
                        {
                            "role": "user",
                            "content": user_content,
                        },
                    ],
                )

                return response.choices[0].message.content

            except Exception as e:
                logger.error(
                    f"❌ [Image Compliance Tool] Visual lookup failed: {e}",
                    exc_info=True,
                )

                return (
                    f"Tool Execution Failure: {str(e)}. "
                    f"Stop trying to analyze this file with this tool."
                )



      

    def remove_duplicates_from_log(self, file_paths: List[str]) -> str:
        """Cleans duplicated operational footprints out of raw log outputs."""
        return f"[ADK Log Tool] Deduplicated transaction entries from: {file_paths}"

    @property
    def tools_registry(self) -> Dict[str, Callable]:
        """
        Maintains structural compatibility with registry lookups, mapping 
        methodology string identifiers directly to the instance methods.
        """
        return {
            # "parse_excel_and_get_extracted_text": self.parse_excel,
            "parse_excel_raw": self.parse_excel_raw,
            "extract_price_change_entries_from_excel": self.extract_price_change_entries,
            "parse_image_and_get_extracted_text": self.extract_text_from_image,
            "analyse_email_evidence_directly_with_llm": self.analyse_email_evidence,
            "analyse_image_evidence_directly_with_llm": self.analyse_image_evidence,
            "analyse_image_evidence_for_tcode_with_llm": self.analyse_image_evidence_for_tcode,
            "get_excel_details_for_row_level_analysis": self.get_excel_table_shape,
            "extract_image_table_details_for_row_level_analysis": self.extract_table_structure_from_image
        }