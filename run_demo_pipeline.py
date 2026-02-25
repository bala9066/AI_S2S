"""
Demo Pipeline Execution - Shows phase-by-phase outputs
Run this to see the full pipeline in action
"""

import asyncio
import json
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from agents.orchestrator import OrchestratorAgent
from database.models import Base, ProjectDB


async def run_demo():
    """Run a demo pipeline with mocked LLM calls."""

    # Setup
    engine = create_engine("sqlite:///demo_pipeline.db")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    # Create test project
    output_dir = Path("output/demo_led_blinker")
    output_dir.mkdir(parents=True, exist_ok=True)

    project = ProjectDB(
        name="Demo LED Blinker",
        description="Simple LED blinking circuit",
        design_type="digital",
        output_dir=str(output_dir),
    )
    session.add(project)
    session.commit()
    session.refresh(project)

    print("=" * 60)
    print("DEMO HARDWARE PIPELINE - LED Blinker Project")
    print("=" * 60)
    print(f"Project ID: {project.id}")
    print(f"Output Directory: {output_dir}")
    print()

    # Setup orchestrator with mocked responses
    orchestrator = OrchestratorAgent()

    # Mock responses for each phase
    mock_responses = {
        "P1": {
            "content": "",
            "tool_calls": [{
                "id": "tool-1",
                "name": "generate_requirements",
                "input": {
                    "project_summary": "LED blinker using STM32 microcontroller",
                    "requirements": [
                        {"req_id": "REQ-001", "category": "functional", "title": "LED Control", "description": "Blink LED at 1Hz", "priority": "shall"},
                        {"req_id": "REQ-002", "category": "functional", "title": "Power", "description": "3.3V supply", "priority": "shall"},
                    ],
                    "design_parameters": {"voltage": "3.3V", "current": "10mA"},
                    "block_diagram_mermaid": "graph TD\nMCU[STM32]-->R[330Ω]\nR-->LED[LED]",
                    "architecture_mermaid": "graph LR\nPower[3.3V]-->MCU",
                    "component_recommendations": [
                        {"function": "MCU", "primary_part": "STM32F103C8T6", "primary_manufacturer": "ST", "primary_description": "ARM Cortex-M3"}
                    ],
                }
            }],
            "model_used": "claude-opus-4-6",
            "stop_reason": "end_turn",
            "usage": {},
        },
        "P2": {"content": "# HRS\n\nHardware Requirements for LED Blinker", "tool_calls": [], "model_used": "claude-opus-4-6", "stop_reason": "end_turn", "usage": {}},
        "P3": {"content": "# Compliance\n\nAll components are RoHS compliant", "tool_calls": [], "model_used": "claude-opus-4-6", "stop_reason": "end_turn", "usage": {}},
        "P4": {
            "content": "",
            "tool_calls": [{
                "id": "tool-4",
                "name": "generate_netlist",
                "input": {
                    "nodes": [
                        {"instance_id": "U1", "part_number": "STM32F103C8T6", "component_name": "MCU"},
                        {"instance_id": "R1", "part_number": "330", "component_name": "Resistor"},
                        {"instance_id": "D1", "part_number": "LED_GREEN", "component_name": "LED"},
                    ],
                    "edges": [
                        {"net_name": "PA0", "from_instance": "U1", "from_pin": "PA0", "to_instance": "R1", "to_pin": "1", "signal_type": "digital"},
                        {"net_name": "LED_K", "from_instance": "R1", "from_pin": "2", "to_instance": "D1", "to_pin": "A", "signal_type": "digital"},
                    ],
                    "power_nets": ["VDD"],
                    "ground_nets": ["VSS"],
                    "mermaid_diagram": "graph TD\nU1-->|PA0|R1\nR1-->|LED_K|D1",
                    "validation_notes": [],
                }
            }],
            "model_used": "claude-opus-4-6",
            "stop_reason": "end_turn",
            "usage": {},
        },
        "P6": {"content": "# GLR\n\nI/O Requirements:\n- PA0: Output to LED", "tool_calls": [], "model_used": "claude-opus-4-6", "stop_reason": "end_turn", "usage": {}},
        "P8a": {"content": "# SRS\n\nSoftware Requirements for LED control", "tool_calls": [], "model_used": "claude-opus-4-6", "stop_reason": "end_turn", "usage": {}},
        "P8b": {"content": "# SDD\n\nSoftware Design Document", "tool_calls": [], "model_used": "claude-opus-4-6", "stop_reason": "end_turn", "usage": {}},
        "P8c": {"content": "```c\nint main(void) {\n  while(1) {\n    GPIO_Toggle();\n    delay(500);\n  }\n}\n```", "tool_calls": [], "model_used": "claude-opus-4-6", "stop_reason": "end_turn", "usage": {}},
    }

    # Mock agent execute for each phase
    executed_phases = []

    # Factory function to properly capture phase in closure
    def make_mock_execute(phase, agent, responses):
        async def mock_execute(project_context, user_input):
            print(f"\n{'='*20}")
            print(f"PHASE {phase}: {agent.phase_name}")
            print(f"{'='*20}")

            executed_phases.append(phase)

            # Return mock response
            return responses.get(phase, {"content": "Done"})
        return mock_execute

    for phase in ["P1", "P2", "P3", "P4", "P6", "P8a", "P8b", "P8c"]:
        agent = orchestrator._get_agent(phase)
        agent.execute = make_mock_execute(phase, agent, mock_responses)

    # Execute all phases
    print("\n" + "="*60)
    print("EXECUTING PIPELINE...")
    print("="*60 + "\n")

    results = await orchestrator.execute_all(
        project_id=project.id,
        initial_input="Create an LED blinker circuit",
        session=session,
    )

    # Show results
    print("\n" + "="*60)
    print("PIPELINE COMPLETE - RESULTS SUMMARY")
    print("="*60)

    for phase, result in results.items():
        status = "[OK] COMPLETE" if result.get("phase_complete") else "[!!] INCOMPLETE"
        outputs = result.get("outputs", {})
        # Get phase name from the agent
        phase_agent = orchestrator._get_agent(phase)
        print(f"\n{phase} - {phase_agent.phase_name}: {status}")
        if outputs:
            for filename in list(outputs.keys())[:3]:  # Show first 3 files
                content_preview = outputs[filename][:50].replace('\n', ' ')
                print(f"    [FILE] {filename}: {content_preview}...")

    # Show database state
    session.refresh(project)
    print(f"\n\n{'='*60}")
    print(f"DATABASE STATE")
    print(f"{'='*60}")
    print(f"Final Phase: {project.current_phase}")
    print(f"\nPhase History:")
    for phase, status_data in project.phase_statuses.items():
        status = status_data.get("status", "unknown")
        completed_at = status_data.get("completed_at", "N/A")
        print(f"  {phase}: {status} (completed: {completed_at})")

    # Show generated files
    print(f"\n{'='*60}")
    print(f"GENERATED FILES")
    print(f"{'='*60}")
    for file_path in sorted(output_dir.rglob("*")):
        if file_path.is_file():
            size = file_path.stat().st_size
            print(f"  [FILE] {file_path.relative_to(output_dir)} ({size} bytes)")

    # Cleanup
    session.close()
    engine.dispose()

    print(f"\n{'='*60}")
    print("Demo complete! Check output/demo_led_blinker/ for generated files")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(run_demo())
