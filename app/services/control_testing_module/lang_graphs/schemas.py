# app/services/control_testing_module/lang_graphs/schemas.py

from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, create_model

# Import the actual corpus dictionary to inspect its operational keys dynamically
from app.services.control_testing_module.helper_scripts.methodology_mapper import TEST_METHODOLOGY_CORPUS

# 1. Base schemas that remain static
class EvidenceGathererOutput(BaseModel):
    status: bool
    file_paths: List[str]

class FinalAuditReport(BaseModel):
    control_id: str
    compliance_status: bool = Field(description="True if actual evidence satisfies target rules, False otherwise.")
    audit_justification: str = Field(description="Detailed sentence explaining why it passed or failed based on methodology.")


# 2. DYNAMIC MODEL CREATION FOR THE INTERPRETER NODE
# Extract keys at runtime directly from your corpus registry
corpus_keys = list(TEST_METHODOLOGY_CORPUS.keys())

# Create a valid typing Literal evaluation boundary from your array slice strings
DynamicLiteral = Literal[tuple(corpus_keys)]  # type: ignore

# Use Pydantic's core engine factory to assemble the model with the dynamic choice array safely
InterpreterOutput = create_model(
    "InterpreterOutput",
    status=(bool, Field(..., description="The classification generation pipeline health status flag.")),
    test_type=(DynamicLiteral, Field(..., description="The precise classification category matching the structural methodology corpus keys.")),
    target_parameters=(List[str], Field(..., description="Key transactional parameters, fields, or configurations isolated from the description text.")),
    __base__=BaseModel # Ensures it explicitly inherits all classic Pydantic BaseModel attributes
)


# 3. Core Graph State Blueprint Container
class G01_graph_state(BaseModel):
    test_description: str
    evidence_filenames: List[str]
    control_id: str
    cycle_id: int
    test_id: int
    
    # These refer perfectly to our dynamically and statically compiled tracking frameworks
    interpreter_result: Optional[InterpreterOutput] = None # type: ignore
    evidence_result: Optional[EvidenceGathererOutput] = None
    final_report: Optional[FinalAuditReport] = None