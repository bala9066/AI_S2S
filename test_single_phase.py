"""
Test Single Phase - Debug P1 to see why it's not generating outputs
"""

import asyncio
import json
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from agents.requirements_agent import RequirementsAgent
from database.models import Base, ProjectDB


async def test_p1():
    """Test P1 with detailed logging."""

    # Setup
    engine = create_engine("sqlite:///test_single_phase.db")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    # Clean up any existing test project
    existing = session.query(ProjectDB).filter_by(name="Test P1 Debug").first()
    if existing:
        session.delete(existing)
        session.commit()

    # Create test project
    output_dir = Path("output/test_p1_debug")
    if output_dir.exists():
        import shutil
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    project = ProjectDB(
        name="Test P1 Debug",
        description="Debug P1 execution",
        design_type="digital",
        output_dir=str(output_dir),
    )
    session.add(project)
    session.commit()
    session.refresh(project)

    print("=" * 60)
    print("TESTING P1 - Requirements Capture")
    print("=" * 60)
    print(f"Project ID: {project.id}")
    print(f"Output Dir: {output_dir}")
    print()

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

    user_input = "Create an LED blinker circuit using STM32 microcontroller. The LED should blink at 1Hz."

    print(f"User Input: {user_input}")
    print()

    # Execute P1
    agent = RequirementsAgent()

    print("Calling LLM...")
    print("-" * 60)

    result = await agent.execute(project_context, user_input)

    print("-" * 60)
    print()
    print("RESULT:")
    print(json.dumps(result, indent=2, default=str))
    print()

    # Check files
    print("FILES GENERATED:")
    for file in output_dir.rglob("*"):
        if file.is_file():
            print(f"  {file.relative_to(output_dir)} ({file.stat().st_size} bytes)")

    print()
    print("=" * 60)

    session.close()
    engine.dispose()


if __name__ == "__main__":
    asyncio.run(test_p1())
