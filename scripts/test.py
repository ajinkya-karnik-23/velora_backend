import pandas as pd, os
import logging
logger = logging.getLogger("control_testing_module")

from typing import List, Optional, Dict, Any

def extract_price_change_entries(file_paths: List[str]) -> List[dict]:

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

    Input:
        file_paths (List[str])
            List of Excel workbook paths.

    Returns:
        List[dict]

    Output Structure:
        [
            {
                "file": "94_cpt.xlsx",

                "condition_codes_found": [
                    "ZF01",
                    "ZA01"
                ],

                "detected_price_change_blocks": [
                    {
                        "condition_code": "ZF01",
                        "item_number": "100010417",
                        "product_name": "IMFINZI INJ 500MG VI 1X10ML GB",
                        "comment": "Imfinzi 500mg moving from £1556.05 to £1013"
                    }
                ],

                "extraction_status": "completed"
            }
        ]

    Notes:
    - The tool scans all sheets and columns automatically.
    - The tool does not depend on fixed workbook layouts.
    - Call this tool only once per workbook.
    - The returned extraction is authoritative for downstream validation.
    """

    import re

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
                "file": evidence_path,
                "error": "File not found"
            })

            continue

        try:

            excel_file = pd.ExcelFile(full_path)

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
                    keep_default_na=False
                )

                # Scan every column independently
                for col_idx in range(df.shape[1]):

                    column_values = [
                        str(v).strip()
                        for v in df.iloc[:, col_idx].tolist()
                    ]

                    current_condition = None

                    # detect condition code in column
                    for value in column_values:

                        for condition in known_condition_codes:

                            if condition.lower() in value.lower():

                                current_condition = condition

                                if (
                                    condition
                                    not in workbook_entities[
                                        "condition_codes_found"
                                    ]
                                ):
                                    workbook_entities[
                                        "condition_codes_found"
                                    ].append(condition)

                    # scan vertically for 3-line blocks
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

                            workbook_entities[
                                "detected_price_change_blocks"
                            ].append({
                                "condition_code": current_condition,
                                "item_number": item_number,
                                "product_name": product_name,
                                "comment": comment
                            })

            # ==========================================================
            # ANALYTICS CALCULATION
            # ==========================================================

            detected_blocks = workbook_entities[
                "detected_price_change_blocks"
            ]

            total_price_modifications_found = len(detected_blocks)

            uncommented_variants = [
                block
                for block in detected_blocks
                if (
                    not block.get("comment")
                    or not str(block.get("comment")).strip()
                )
            ]

            uncommented_variants_count = len(uncommented_variants)

            unique_condition_codes_with_changes = list({
                block.get("condition_code")
                for block in detected_blocks
                if block.get("condition_code")
            })

            workbook_entities["analytics"] = {
                "total_price_modifications_found":
                    total_price_modifications_found,

                "uncommented_variants_count":
                    uncommented_variants_count,

                "unique_condition_codes_with_changes":
                    unique_condition_codes_with_changes,

                "all_variants_have_comments":
                    uncommented_variants_count == 0,

                "compliance_status":
                    uncommented_variants_count == 0
            }

            extracted_entries.append(workbook_entities)

        except Exception as exc:

            logger.exception(
                f"[Price Entry Extractor] Failed processing: {full_path}"
            )

            extracted_entries.append({
                "file": os.path.basename(full_path),
                "error": str(exc)
            })

    return extracted_entries


output = extract_price_change_entries(
    file_paths=[
        '/Users/ajinkyakarnik/Desktop/Apps/control-IQ/control iQ backend -05-2026/CIQ_Backend/storage/4/CTRL0020526/94_cpt.xlsx'
    ]
)

import json
print(json.dumps(output, indent=4))