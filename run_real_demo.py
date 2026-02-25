"""
Real Demo Pipeline - Actually Generates Files
This demo provides comprehensive input to generate actual project files
"""

import asyncio
import json
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from agents.orchestrator import OrchestratorAgent
from database.models import Base, ProjectDB


async def run_real_demo():
    """Run a real demo that generates actual files."""

    # Setup
    engine = create_engine("sqlite:///real_demo.db")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    # Clean up any existing demo project
    existing = session.query(ProjectDB).filter_by(name="Real Demo LED Blinker").first()
    if existing:
        session.delete(existing)
        session.commit()

    # Create test project
    output_dir = Path("output/real_demo_led_blinker")
    # Clean output directory
    if output_dir.exists():
        import shutil
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    project = ProjectDB(
        name="Real Demo LED Blinker",
        description="Simple LED blinking circuit with real file generation",
        design_type="digital",
        output_dir=str(output_dir),
    )
    session.add(project)
    session.commit()
    session.refresh(project)

    print("=" * 60)
    print("REAL HARDWARE PIPELINE DEMO - LED Blinker Project")
    print("=" * 60)
    print(f"Project ID: {project.id}")
    print(f"Output Directory: {output_dir.absolute()}")
    print()
    print("[WARNING] This will make REAL LLM API calls!")
    print("    Press Ctrl+C to cancel if you don't want to use API credits")
    print()

    import time
    for i in range(3, 0, -1):
        print(f"Starting in {i}...", flush=True)
        await asyncio.sleep(1)

    print("\n" + "="*60)
    print("EXECUTING REAL PIPELINE WITH LLM CALLS")
    print("="*60 + "\n")

    # Use real orchestrator (no mocks)
    orchestrator = OrchestratorAgent()

    # Comprehensive input to avoid clarifying questions
    comprehensive_input = """
Create an LED blinker circuit with these specifications:

**Hardware:**
- STM32F103C8T6 microcontroller (LQFP48 package)
- Single green LED (Vf=2.1V, If=10mA)
- 330 ohm current-limiting resistor
- Power: 3.3V from USB

**Requirements:**
- LED blinks at 1Hz (500ms on, 500ms off)
- GPIO PA0 controls LED
- System clock: 72MHz
- Commercial temperature range (0-70°C)
- RoHS compliant

**Compliance:**
- REACH compliant
- RoHS compliant
- No FCC/CE needed (low frequency)

**Software:**
- C code with HAL
- MISRA-C compliant
- Include main.c, GPIO config, delay function
- Unit tests for GPIO toggle

Please proceed directly with generating all requirements without asking clarifying questions.
"""

    # Execute all phases
    results = await orchestrator.execute_all(
        project_id=project.id,
        initial_input=comprehensive_input,
        session=session,
    )

    # Show results
    print("\n" + "="*60)
    print("PIPELINE COMPLETE - RESULTS SUMMARY")
    print("="*60)

    for phase, result in results.items():
        status = "[OK] COMPLETE" if result.get("phase_complete") else "[!!] INCOMPLETE"
        outputs = result.get("outputs", {})
        phase_agent = orchestrator._get_agent(phase)
        print(f"\n{phase} - {phase_agent.phase_name}: {status}")
        if outputs:
            for filename in list(outputs.keys())[:5]:
                print(f"    [FILE] {filename}")

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
    print(f"GENERATED FILES IN: {output_dir.absolute()}")
    print(f"{'='*60}")

    all_files = list(output_dir.rglob("*"))
    files = [f for f in all_files if f.is_file()]

    if not files:
        print("  No files generated! Check the logs above for errors.")
    else:
        for file_path in sorted(files):
            size = file_path.stat().st_size
            rel_path = file_path.relative_to(output_dir)
            print(f"  [FILE] {rel_path} ({size} bytes)")

    # Show sample content from key files
    print(f"\n{'='*60}")
    print(f"SAMPLE FILE CONTENTS")
    print(f"{'='*60}")

    key_files = [
        "HRS_Real_Demo_LED_Blinker.md",
        "glr_specification.md",
        "SRS_Real_Demo_LED_Blinker.md",
        "SDD_Real_Demo_LED_Blinker.md",
        "compliance_report.md",
        "netlist.json",
    ]

    for filename in key_files:
        filepath = output_dir / filename
        if filepath.exists():
            content = filepath.read_text(encoding="utf-8")
            lines = content.split('\n')
            preview = '\n'.join(lines[:15])
            print(f"\n--- {filename} (first 15 lines) ---")
            print(preview)
            if len(lines) > 15:
                print(f"... ({len(lines) - 15} more lines)")

    # Check for code files
    src_dir = output_dir / "src"
    if src_dir.exists():
        print(f"\n--- Generated Code Files (src/) ---")
        for code_file in sorted(src_dir.rglob("*")):
            if code_file.is_file():
                rel_path = code_file.relative_to(output_dir)
                size = code_file.stat().st_size
                print(f"  {rel_path} ({size} bytes)")

    # Cleanup
    session.close()
    engine.dispose()

    print(f"\n{'='*60}")
    print("Real demo complete!")
    print(f"All files saved to: {output_dir.absolute()}")
    print("="*60)


if __name__ == "__main__":
    try:
        asyncio.run(run_real_demo())
    except KeyboardInterrupt:
        print("\n\nDemo cancelled by user.")
    except Exception as e:
        print(f"\n\nError: {e}")
        import traceback
        traceback.print_exc()
