import os
import asyncio
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END

# Import the methodology mapper module we created above
from methodology_mapper import get_methodology_for_category

load_dotenv()
os.environ["LANGCHAIN_CALLBACKS_BACKGROUND"] = "false"

# =====================================================================
# 1. DEFINE Pydantic STATE SCHEMAS
# =====================================================================

class InterpreterOutput(BaseModel):
    status: bool
    test_type: str
    target_parameters: List[str]

class EvidenceGathererOutput(BaseModel):
    status: bool
    file_paths: List[str]

class FinalAuditReport(BaseModel):
    control_id: str
    compliance_status: bool = Field(description="True if actual evidence completely satisfies target rules, False otherwise.")
    audit_justification: str = Field(description="Detailed sentence explaining why it passed or failed based on methodology.")

# The Master State of our Graph
class GraphState(BaseModel):
    test_description: str
    evidence_filenames: List[str]
    control_id: str
    cycle_id: int
    
    # Parallel storage variables
    interpreter_result: Optional[InterpreterOutput] = None
    evidence_result: Optional[EvidenceGathererOutput] = None
    
    # Final Result
    final_report: Optional[FinalAuditReport] = None

# =====================================================================
# 2. DEFINE SYSTEM SIMULATION TOOLS
# =====================================================================

def mock_read_excel_tool(paths: List[str]) -> str:
    """Simulates an Excel tool pulling values from a spreadsheet log file."""
    # In a live script, this would use pandas/openpyxl to read state.evidence_result.file_paths
    return "EXTRACTED LOG ROW: T-Code=ZV231213 | Org=GB10 | Cond=ZL01 | Dates=01.10.2023 to 31.10.2023"

# =====================================================================
# 3. GRAPH NODES (WORKERS)
# =====================================================================

async def interpreter_node(state: GraphState) -> Dict[str, Any]:
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.0).with_structured_output(
        InterpreterOutput, method="json_schema"
    )
    prompt = f"Analyze and categorize this test: {state.test_description}"
    result = await llm.ainvoke([HumanMessage(content=prompt)])
    return {"interpreter_result": result}

async def evidence_gatherer_node(state: GraphState) -> Dict[str, Any]:
    # Simulates gathering and mapping files to active file system arrays
    base_prefix = f"{state.cycle_id}/{state.control_id}"
    resolved = [f"{base_prefix}/{name}" for name in state.evidence_filenames]
    return {"evidence_result": EvidenceGathererOutput(status=True, file_paths=resolved)}


async def methodology_worker_node(state: GraphState) -> Dict[str, Any]:
    """
    Downstream Worker Node: Fetches granular rules from the mapper,
    executes relevant system tools, and builds the final structured audit sheet.
    """
    print(f"\n[Worker Node] Dynamic Routing Activated!")
    
    # 1. Fetch our precise methodology corpus using our helper file
    detected_category = state.interpreter_result.test_type
    methodology_package = get_methodology_for_category(detected_category)
    
    print(f"[Worker Node] Loading Playbook: '{methodology_package['title']}'")
    
    # 2. Dynamic Tool Workflow Execution Loop
    extracted_evidence_dump = ""
    if "read_excel_sheet_structure" in methodology_package["expected_tools"]:
        print("[Worker Node Executing Tool] --> Running mock_read_excel_tool on target files...")
        extracted_evidence_dump = mock_read_excel_tool(state.evidence_result.file_paths)
    
    # 3. Pass Crisp Data + Methodology Corpus to the Auditor LLM
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.0).with_structured_output(
        FinalAuditReport, method="json_schema"
    )
    
    audit_prompt = f"""
    You are an expert financial compliance compliance auditor. Review the case using this strict playbook.
    
    === REQUIRED TESTING METHODOLOGY PLAYBOOK ===
    {methodology_package['methodology_instructions']}
    
    === BASELINE TARGETS TO LOOK FOR ===
    Control Identification: {state.control_id}
    Target Match Parameters: {state.interpreter_result.target_parameters}
    
    === ACTUAL EXTRACTED FILE DATA EVIDENCE ===
    {extracted_evidence_dump}
    
    Generate your structured audit schema.
    """
    
    report_output = await llm.ainvoke([HumanMessage(content=audit_prompt)])
    return {"final_report": report_output}

# =====================================================================
# 4. BUILD THE REFACTORED GRAPH ARCHITECTURE
# =====================================================================

builder = StateGraph(GraphState)

# Define our three specialized nodes
builder.add_node("interpreter", interpreter_node)
builder.add_node("evidence_gatherer", evidence_gatherer_node)
builder.add_node("methodology_worker", methodology_worker_node)

# Step A: Fan-Out Parallel Split at START
builder.add_edge(START, "interpreter")
builder.add_edge(START, "evidence_gatherer")

# Step B: Recombine Parallel Split into our downstream methodology worker node
builder.add_edge("interpreter", "methodology_worker")
builder.add_edge("evidence_gatherer", "methodology_worker")

# Step C: Complete the workflow pipeline loop
builder.add_edge("methodology_worker", END)

graph = builder.compile()

# =====================================================================
# 5. EXECUTION ENTRYPOINT RUNNER
# =====================================================================

async def run_pipeline():
    initial_payload = {
        "control_id": "CTRL0020526",
        "cycle_id": 4,
        "test_description": "In 526m_IPE1.jpg \n1) T-Code = ZV231213 \n2) Sales Organisation = GB10\n3) Condition Type = ZL01",
        "evidence_filenames": ["88_IPE_3.xlsx"]
    }
    
    print("🚀 Running Control-iQ-V2 Granular Playbook Pipeline...")
    final_state = await graph.ainvoke(initial_payload)
    
    print("\n🏁 FINAL AUDIT ARCHIVE SUMMARY:")
    print("=" * 60)
    print(f"Compliance Status: {final_state['final_report'].compliance_status}")
    print(f"Audit Justification: {final_state['final_report'].audit_justification}")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(run_pipeline())