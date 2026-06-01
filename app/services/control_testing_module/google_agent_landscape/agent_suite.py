import os
from google.adk import Agent

# Import your landscape structural schemas
from app.services.control_testing_module.google_agent_landscape.schemas import (
    AgentWorkOrderInput,
    PriceChangeValidationOutput,
    EmailAnalysisOutput,
    RowLevelAnalysisOutput,
    SapImageValidationOutput,
    GenericValidationOutput
)
from app.services.control_testing_module.helper_scripts.methodology_mapper import get_methodology_for_category
from app.services.control_testing_module.google_agent_landscape.tools_repository import Tools
from app.services.control_testing_module.google_agent_landscape.tools_repository import *

# Dynamically fall back to the environment variable string exactly as required by your environment proxy setup
litellm_model = os.getenv("LITELLM_MODEL", "openai/gpt-4o-mini")

# =====================================================================
# GOOGLE ADK AGENT SUITE DEFINITIONS (FIXED SYNTAX PARAMETERS)
# =====================================================================

# Tools
tool_box = Tools()

# 1. Price Change Commentary Agent
default_CPT_PRICE_CHANGE_VALIDATION_agent = Agent(
    name="default_cpt_price_change_validation_agent",
    model=litellm_model,
    instruction=(
        f"You are the Default Price Change Commentary Alignment Agent.\n"
        f"Execute your analysis strictly following this framework:\n"
        f"{get_methodology_for_category('CPT_PRICE_CHANGE_VALIDATION')['methodology_instructions']}"
    ),
    input_schema=AgentWorkOrderInput,
    output_schema=PriceChangeValidationOutput,
    output_key="price_change_validation_output",
    tools=[
        tool_box.tools_registry["extract_price_change_entries_from_excel"],
        tool_box.tools_registry["parse_image_and_get_extracted_text"]
    ]
)

# 2. Email Sign-Off Analysis Agent
default_CPT_EMAIL_ANALYSIS_agent = Agent(
    name="default_cpt_email_analysis_agent",
    model=litellm_model,
    instruction=(
        f"You are the Default CPT Sign-Off and Compliance Email Analysis Agent.\n"
        f"Execute your checks strictly using this framework:\n"
        f"{get_methodology_for_category('CPT_EMAIL_ANALYSIS')['methodology_instructions']}"
    ),
    input_schema=AgentWorkOrderInput,
    output_schema=EmailAnalysisOutput,
    output_key="email_analysis_output",
    tools=[
        tool_box.tools_registry["analyse_email_evidence_directly_with_llm"]
    ]
)

# 3. Row-Level Validation Agent
default_ROW_LEVEL_ANALYSIS_agent = Agent(
    name="default_row_level_analysis_agent",
    model=litellm_model,
    instruction=(
        f"You are the Default Row-Level Validation Framework Agent.\n"
        f"Execute your cross-source reconciliations strictly using this framework:\n"
        f"{get_methodology_for_category('ROW_LEVEL_ANALYSIS')['methodology_instructions']}"
    ),
    input_schema=AgentWorkOrderInput,
    output_schema=RowLevelAnalysisOutput,
    output_key="row_level_analysis_output",
    tools=[
        tool_box.tools_registry["get_excel_details_for_row_level_analysis"],
        tool_box.tools_registry["extract_image_table_details_for_row_level_analysis"]
    ]

)

# 4. SAP GUI Visual Inspection Agent
default_IPE_SAP_IMAGE_VALIDATION_agent = Agent(
    name="default_ipe_sap_image_validation_agent",
    model=litellm_model,
    instruction=(
        f"You are the Default IPE SAP GUI Presentation Layer Structural Inspection Agent.\n"
        f"Extract and evaluate visual fields strictly using this framework:\n"
        f"{get_methodology_for_category('IPE_SAP_IMAGE_VALIDATION')['methodology_instructions']}"
    ),
    input_schema=AgentWorkOrderInput,
    output_schema=SapImageValidationOutput,
    output_key="sap_image_validation_output",
    tools=[
        tool_box.tools_registry["analyse_image_evidence_directly_with_llm"],
        tool_box.tools_registry["parse_image_and_get_extracted_text"],
        tool_box.tools_registry["analyse_image_evidence_for_tcode_with_llm"],
    ]
)

# 5. Generic Fallback Text Agent
default_GENERIC_agent = Agent(
    name="default_generic_agent",
    model=litellm_model,
    instruction=(
        f"You are the Default Generic Compliance Validation Agent.\n"
        f"Execute your verification loops using this framework:\n"
        f"{get_methodology_for_category('GENERIC')['methodology_instructions']}"
    ),
    input_schema=AgentWorkOrderInput,
    output_schema=GenericValidationOutput,
    output_key="generic_validation_output"
)