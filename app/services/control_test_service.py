"""Control test service — update test config."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.repositories.control_test_repo import ControlTestRepo
# from app.services.agent_configuration import input_json
from app.schemas.control_test import ControlTestOut, ControlTestUpdate, CycleTestObjectiveOut
import os, logging, json
from dotenv import load_dotenv
import json
import os
import uuid
import structlog

# Agentic imports
from app.services.agent_configuration import ipe_workflow, cpt_workflow
from google.adk.sessions import InMemorySessionService
from google.adk import Runner

# Logging
logger = structlog.get_logger(__name__)

# Load environment variables
load_dotenv()

class ControlTestService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = ControlTestRepo(db)

    async def update_test(self, test_id: int, data: ControlTestUpdate) -> ControlTestOut:
        test = await self.repo.get_by_id(test_id)
        if not test:
            raise NotFoundException("Control test not found.")
        update_data = {k: v for k, v in data.model_dump().items() if v is not None}
        await self.repo.update(test, update_data)
        await self.db.commit()
        return ControlTestOut.model_validate(test)

    async def get_test(self, test_id: int) -> ControlTestOut:
        test = await self.repo.get_by_id(test_id)
        if not test:
            raise NotFoundException("Control test not found.")
        return ControlTestOut.model_validate(test)

    async def list_tests(self, config_control_id: int) -> list[ControlTestOut]:
        tests = await self.repo.get_by_config_control(config_control_id)
        return [ControlTestOut.model_validate(t) for t in tests]

    async def list_cycle_test_objectives(self, cycle_id: int) -> list[CycleTestObjectiveOut]:
        tests = await self.repo.get_cycle_tests(cycle_id)
        result = []
        for t in tests:
            cc = t.config_control
            ctrl = cc.control if cc else None
            result.append(CycleTestObjectiveOut(
                test_id=t.test_id,
                config_control_id=t.config_control_id,
                control_id=ctrl.control_id if ctrl else None,
                control_number=ctrl.control_number if ctrl else None,
                control_name=ctrl.control_name if ctrl else None,
                domain=ctrl.domain if ctrl else None,
                tests=t.tests,
                note=t.note,
                comments=t.comments,
                created_time=t.created_time,
                updated_time=t.updated_time,
            ))
        return result
    
    async def perform_test(self, payload , task_id:str): # Updated version (latest adk documentation)

        detailed_jsons_path = os.getenv("DETAILED_JSONS_PATH")

        # Shared session service for all runs
        session_service = InMemorySessionService()

        results = []

        for item in payload:

            try:

                control_id = item.get("controlID")
                is_cpt = item.get("CPT", False)

                print("LIVE ITEM:", item)
                print("LIVE TEST ID:", item.get("testID"))
                
                current_test_id = item.get("testID")

                test_metadata ={
                    "task_id":task_id,
                    "control_id": control_id,
                    "cycle_id": item.get("cycleID"),
                    "test_id": current_test_id,
                    "is_cpt": is_cpt
                }

                json_file_path = os.path.join(
                    detailed_jsons_path,
                    f"{control_id}.json"
                )

                # -----------------------------------------------------------------
                # Validate reference file
                # -----------------------------------------------------------------

                if not os.path.exists(json_file_path):

                    item["testing"] = {
                        "test_completion": False,
                        "test_result": "Fail",
                        "remarks": f"Reference file {control_id}.json not found."
                    }

                    results.append(item)
                    continue

                with open(json_file_path, "r", encoding="utf-8") as file:
                    detailed_json = json.load(file)

                validations_list = detailed_json.get("validations", [])

                mapped_test_description = next(
                    (
                        validation.get("validation_desc")
                        for validation in validations_list
                        if validation.get("test_id") == current_test_id
                    ),
                    None
                )

                # -----------------------------------------------------------------
                # Validation mapping failed
                # -----------------------------------------------------------------

                if not mapped_test_description:

                    item["testing"] = {
                        "test_completion": False,
                        "test_result": "Fail",
                        "remarks": (
                            f"No validation found for "
                            f"{current_test_id} in {control_id}.json"
                        )
                    }

                    results.append(item)
                    continue

                logger.info(
                    "validation_context_found",
                    control_id=control_id,
                    test_id=current_test_id
                )

                # -----------------------------------------------------------------
                # Workflow selection
                # -----------------------------------------------------------------

                workflow = cpt_workflow if is_cpt else ipe_workflow

                # -----------------------------------------------------------------
                # Session creation
                # -----------------------------------------------------------------

                session = await session_service.create_session(
                    app_name="control-testing",
                    user_id="system-user",
                    session_id=str(uuid.uuid4())
                )

                runner = Runner(
                    agent=workflow,
                    app_name="control-testing",
                    session_service=session_service
                )

                # -----------------------------------------------------------------
                # Execute ADK workflow
                # -----------------------------------------------------------------

                final_response = None

                from google.genai import types as genai_types
                new_message = genai_types.Content(
                    role="user",
                    parts=[genai_types.Part(text=f"Test Metadata: {test_metadata}\nTest Description: {mapped_test_description}")],
                )

                async for event in runner.run_async(
                    user_id="system-user",
                    session_id=session.id,
                    new_message=new_message,
                ):

                    logger.info(
                        "adk_event",
                        author=getattr(event, "author", None),
                        content=str(getattr(event, "content", None))
                    )

                    # Final response detection
                    if getattr(event, "is_final_response", lambda: False)():

                        final_response = event.content.parts[0].text

                # -----------------------------------------------------------------
                # No response handling
                # -----------------------------------------------------------------

                if not final_response:

                    item["testing"] = {
                        "test_completion": False,
                        "test_result": "Fail",
                        "remarks": "Workflow completed without a final response."
                    }

                    results.append(item)
                    continue

                # -----------------------------------------------------------------
                # Parse workflow response
                # -----------------------------------------------------------------

                try:
                    
                    print("\n========== AGENT OUTPUT ==========")
                    print(final_response)
                    print("==================================\n")

                    parsed_output = json.loads(final_response)
                    print("AGENT OUTPUT KEYS:", parsed_output.keys())
                    print("AGENT OUTPUT JSON:", json.dumps(parsed_output, indent=2))

                    item["testing"] = {
                        "test_completion": True,
                        "test_result": parsed_output.get("status", "Unknown"),
                        "remarks": parsed_output.get("evaluation_summary", ""),
                        "validation_metadata": parsed_output.get("validation_metadata", [])
                    }

                except json.JSONDecodeError:

                    print("\n========== RAW AGENT OUTPUT (NON-JSON) ==========")
                    print(final_response)
                    print("=================================================\n")

                    # Fallback if the agent returns non-JSON or malformed text
                    item["testing"] = {
                        "test_completion": True,
                        "test_result": "Unknown",
                        "remarks": final_response
                    }

                results.append(item)

            except Exception as e:

                logger.exception(
                    "control_test_failed",
                    error=str(e)
                )

                item["testing"] = {
                    "test_completion": False,
                    "test_result": "Fail",
                    "remarks": str(e)
                }

                results.append(item)

        return results