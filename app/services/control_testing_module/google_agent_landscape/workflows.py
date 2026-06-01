# app/services/control_testing_module/google_agent_landscape/workflows.py

import os
import logging
from typing import Dict, Any, List

# Official Google ADK Primitives
from google.adk.agents import SequentialAgent, LlmAgent
from google.genai.types import GenerateContentConfig

# Cross-Service Internal Module Imports
from app.services.control_testing_module.helper_scripts.methodology_mapper import get_methodology_for_category
from app.services.control_testing_module.google_agent_landscape.tools_repository import tools_registry

logger = logging.getLogger("control_testing_module")

# =====================================================================
# 1. THE 4 REUSABLE SYSTEM AGENTS (SHARED ACROSS ALL WORKFLOWS)
# =====================================================================

def create_parsing_agent(bound_tools: List[Any]) -> LlmAgent:
    """Agent 1: Extracts and structures raw text data from files using specific tools."""
    agent_tools = [tools_registry.get("tool_name_1"), tools_registry.get("tool_name_2")]
    return LlmAgent(
        name="Data_Extraction_Agent",
        model="gemini-2.5-flash",
        instruction="You are a data extraction specialist. Your job is to run file parsing tools and extract clean, relevant text records.",
        tools=bound_tools,
        generate_content_config=GenerateContentConfig(temperature=0.0)
    )

def create_reconciliation_agent() -> LlmAgent:
    """Agent 2: Cross-references extracted parameters against targets line-by-line."""
    return LlmAgent(
        name="Data_Reconciliation_Agent",
        model="gemini-2.5-flash",
        instruction="You are a cross-referencing expert. Match extracted file parameters line-by-line against baseline targets.",
        generate_content_config=GenerateContentConfig(temperature=0.0)
    )

def create_assessment_agent(custom_instructions: str) -> LlmAgent:
    """Agent 3: Evaluates findings against the strict methodology compliance rules."""
    return LlmAgent(
        name="Compliance_Assessment_Agent",
        model="gemini-2.5-flash",
        instruction=custom_instructions, # Injected dynamically on the fly
        generate_content_config=GenerateContentConfig(temperature=0.0)
    )

def create_reporting_agent() -> LlmAgent:
    """Agent 4: Compiles the final detailed structured audit report."""
    return LlmAgent(
        name="Audit_Reporting_Agent",
        model="gemini-2.5-flash",
        instruction="Formulate a definitive Pass/Fail judgment with explicit, transparent evidence justifications.",
        generate_content_config=GenerateContentConfig(temperature=0.0)
    )

# =====================================================================
# 2. THE DYNAMIC COMPILER LOGIC (STITCHING GRAPH OUTPUT + PLAYBOOK)
# =====================================================================

def compile_runner_workflow(test_category: str, graph_evidence_paths: List[str]) -> SequentialAgent:
    """
    Takes the G01 graph outputs and category mapping details to dynamically
    generate custom instructions for the core reusable agent chain.
    """
    logger.info(f"🧱 [Workflows Engine] Compiling ADK runner for: {test_category}")

    # A. Fetch details from the central methodology module mapper
    methodology_package = get_methodology_for_category(test_category)
    title = methodology_package.get("title", "Standard Audit Workflow")
    methodology_instructions = methodology_package.get("methodology_instructions", "")
    expected_tools = methodology_package.get("expected_tools", [])

    # B. Map string configurations to actual tools from our tools_repository
    bound_tools = [tools_registry[t] for t in expected_tools if t in tools_registry]

    # C. STITCH TOGETHER METHODOLOGY + GRAPH OUTPUT FOR THE ASSESSMENT INSTRUCTION
    custom_auditor_instruction = (
        f"You are a Senior Compliance Testing Automation Auditor operating under the playbook: '{title}'.\n\n"
        f"=== EXPLICIT TESTING PROCEDURES TO FOLLOW ===\n"
        f"{methodology_instructions}\n\n"
        f"=== TARGET FILES ALREADY ISOLATED BY THE GRAPH ===\n"
        f"Analyze these specific file targets: {graph_evidence_paths}\n\n"
        f"CRITICAL RULE: Rely strictly on actual tool data. Never speculate or assume records."
    )

    # D. Instantiate your 4 core reusable agents, passing the dynamic rules where needed
    parser = create_parsing_agent(bound_tools)
    reconciler = create_reconciliation_agent()
    assessment_auditor = create_assessment_agent(custom_auditor_instruction)
    reporter = create_reporting_agent()

    # E. Nest them into a unified, sequential workflow pipeline assembly line
    compiled_workflow = SequentialAgent(
        name=f"{test_category}_Pipeline_Workflow",
        sub_agents=[parser, reconciler, assessment_auditor, reporter]
    )

    return compiled_workflow