"""
Interactive Pipeline - Conversational Mode
Run this to interact with the AI agents as they ask clarifying questions
"""

import asyncio
import json
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from agents.orchestrator import OrchestratorAgent
from database.models import Base, ProjectDB


async def run_interactive():
    """Run interactive pipeline where you can answer agent questions."""

    # Setup
    engine = create_engine("sqlite:///interactive.db")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    # Clean up any existing project
    existing = session.query(ProjectDB).filter_by(name="Interactive LED Blinker").first()
    if existing:
        session.delete(existing)
        session.commit()

    # Create project
    output_dir = Path("output/interactive_led_blinker")
    if output_dir.exists():
        import shutil
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    project = ProjectDB(
        name="Interactive LED Blinker",
        description="Interactive demo with conversational AI",
        design_type="digital",
        output_dir=str(output_dir),
    )
    session.add(project)
    session.commit()
    session.refresh(project)

    print("=" * 70)
    print("INTERACTIVE HARDWARE PIPELINE")
    print("=" * 70)
    print(f"Project: {project.name}")
    print(f"Output: {output_dir.absolute()}")
    print()
    print("MODE: CONVERSATIONAL")
    print("The AI will ask you questions. Provide detailed answers.")
    print("Type 'done' when you want to proceed to generation.")
    print("Type 'quit' to exit.")
    print()
    print("=" * 70)
    print()

    # Get initial user input
    print("Describe your hardware project:")
    initial_input = input("> ").strip()

    if not initial_input or initial_input.lower() == 'quit':
        print("Exiting.")
        session.close()
        engine.dispose()
        return

    print()
    print("=" * 70)
    print("STARTING PHASE 1: Requirements Capture")
    print("=" * 70)
    print()

    # Initialize orchestrator
    orchestrator = OrchestratorAgent()

    # Build project context
    project_context = {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "design_type": project.design_type,
        "output_dir": str(output_dir),
        "current_phase": "P1",
        "phase_statuses": {},
    }

    # Run P1 interactively
    agent = orchestrator._get_agent("P1")
    user_input = initial_input
    conversation_turn = 0
    max_turns = 10  # Prevent infinite loops

    while conversation_turn < max_turns:
        conversation_turn += 1
        print(f"\n--- Turn {conversation_turn} ---")

        # Execute agent
        result = await agent.execute(project_context, user_input)

        # Check if phase is complete
        if result.get("phase_complete"):
            print("\n" + "=" * 70)
            print("[PHASE 1 COMPLETE]")
            print("=" * 70)
            print("\nGenerated files:")
            for filename in result.get("outputs", {}):
                print(f"  - {filename}")

            # Update project in database
            project.current_phase = "P2"
            statuses = dict(project.phase_statuses) if project.phase_statuses else {}
            statuses["P1"] = {
                "status": "completed",
                "completed_at": asyncio.get_event_loop().time()
            }
            project.phase_statuses = statuses
            session.commit()

            break

        # Show agent response
        response = result.get("response", "")
        print(f"\nAI: {response}")

        # Check if there were tool outputs
        outputs = result.get("outputs", {})
        if outputs:
            print("\n[Files generated so far:]")
            for filename in outputs:
                print(f"  - {filename}")

        # Get user input
        print()
        user_input = input("You> ").strip()

        if user_input.lower() == 'quit':
            print("\nExiting interactive mode.")
            session.close()
            engine.dispose()
            return

        if user_input.lower() == 'done':
            print("\nRequesting final generation...")
            user_input = "Please generate the complete requirements now with all the information provided."

    # Continue with remaining phases (automated)
    print("\n" + "=" * 70)
    print("CONTINUING WITH REMAINING PHASES (P2-P8c)")
    print("=" * 70)
    print("\nThese phases will run automatically...")
    print()

    # Execute remaining phases
    remaining_phases = ["P2", "P3", "P4", "P6", "P8a", "P8b", "P8c"]

    for phase in remaining_phases:
        print(f"\n--- PHASE {phase} ---")
        agent = orchestrator._get_agent(phase)

        result = await agent.execute(project_context, f"Continue to {phase}")

        status = "[OK]" if result.get("phase_complete") else "[!!]"
        print(f"{status} {agent.phase_name}")

        if result.get("outputs"):
            for filename in list(result.get("outputs", {}).keys())[:3]:
                print(f"  - {filename}")

        # Update project
        statuses = dict(project.phase_statuses) if project.phase_statuses else {}
        statuses[phase] = {
            "status": "completed" if result.get("phase_complete") else "incomplete",
            "completed_at": asyncio.get_event_loop().time()
        }
        project.phase_statuses = statuses
        project.current_phase = phase
        session.commit()

    # Show final results
    print("\n" + "=" * 70)
    print("PIPELINE COMPLETE")
    print("=" * 70)

    session.refresh(project)

    print(f"\nFinal Phase: {project.current_phase}")
    print("\nPhase History:")
    for phase, status_data in project.phase_statuses.items():
        status = status_data.get("status", "unknown")
        print(f"  {phase}: {status}")

    # Show generated files
    print(f"\n{'='*70}")
    print(f"GENERATED FILES")
    print(f"{'='*70}")

    all_files = list(output_dir.rglob("*"))
    files = [f for f in all_files if f.is_file()]

    if not files:
        print("  No files generated.")
    else:
        for file_path in sorted(files):
            size = file_path.stat().st_size
            rel_path = file_path.relative_to(output_dir)
            print(f"  {rel_path} ({size} bytes)")

    print(f"\n{'='*70}")
    print(f"All files saved to: {output_dir.absolute()}")
    print(f"{'='*70}")

    session.close()
    engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(run_interactive())
    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
    except Exception as e:
        print(f"\n\nError: {e}")
        import traceback
        traceback.print_exc()
