"""
Interactive Pipeline v2 - Simple & Reliable
Creates a real project with comprehensive input to avoid conversation loops
"""

import asyncio
import json
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from agents.orchestrator import OrchestratorAgent
from database.models import Base, ProjectDB


async def run_interactive_v2():
    """Run interactive demo with comprehensive input."""

    # Setup
    engine = create_engine("sqlite:///interactive_v2.db")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    # Clean up
    existing = session.query(ProjectDB).filter_by(name="Interactive V2 LED Blinker").first()
    if existing:
        session.delete(existing)
        session.commit()

    # Create project
    output_dir = Path("output/interactive_v2_led_blinker")
    if output_dir.exists():
        import shutil
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    project = ProjectDB(
        name="Interactive V2 LED Blinker",
        description="Interactive demo V2 with comprehensive input",
        design_type="digital",
        output_dir=str(output_dir),
    )
    session.add(project)
    session.commit()
    session.refresh(project)

    print("=" * 70)
    print("INTERACTIVE PIPELINE V2 - LED Blinker")
    print("=" * 70)
    print(f"Project: {project.name}")
    print(f"Output: {output_dir.absolute()}")
    print()
    print("This will make REAL LLM API calls.")
    print("Please wait while the system generates all files...")
    print()

    # Comprehensive input to avoid clarifying questions
    comprehensive_input = """
I need a complete LED blinker design. Here are ALL the specifications:

**Microcontroller:**
- STM32F103C8T6 (ARM Cortex-M3, 72MHz, LQFP48 package)
- 64KB Flash, 20KB RAM
- 3.3V supply

**LED:**
- Green LED, Vf=2.1V at If=10mA
- Single indicator LED
- Connected to GPIO PA0

**Resistor:**
- 330 ohm current-limiting resistor
- 1/4W, 5% tolerance

**Power:**
- 3.3V from USB via LDO regulator
- 5V USB input, AMS1117-3.3 LDO

**Requirements:**
- LED blink rate: 1Hz (500ms on, 500ms off)
- System clock: 72MHz using external 8MHz crystal
- GPIO push-pull output
- Active high configuration

**Environment:**
- Commercial temperature range (0-70°C)
- Indoor use, no special environmental protection needed

**Compliance:**
- RoHS compliant (all components)
- REACH compliant
- No FCC/CE needed (low frequency, battery operated)

**Software:**
- C code using HAL drivers
- MISRA-C 2012 compliant
- Main function with infinite loop
- GPIO initialization
- Delay function using SysTick
- Doxygen comments

**Deliverables Needed:**
1. Hardware Requirements Specification (HRS)
2. Compliance report (RoHS, REACH)
3. Circuit netlist with connections
4. GPIO and Register Layout (GLR)
5. Software Requirements Specification (SRS)
6. Software Design Document (SDD)
7. Production-ready C code with HAL
8. Code review report

Please proceed DIRECTLY to generating all outputs WITHOUT asking any more questions. All requirements are fully specified above.
"""

    print("Starting pipeline execution...")
    print()

    # Initialize orchestrator
    orchestrator = OrchestratorAgent()

    # Execute all phases
    results = await orchestrator.execute_all(
        project_id=project.id,
        initial_input=comprehensive_input,
        session=session,
    )

    # Show results
    print("\n" + "=" * 70)
    print("PIPELINE COMPLETE - RESULTS")
    print("=" * 70)

    for phase, result in results.items():
        status = "[OK]" if result.get("phase_complete") else "[!!]"
        outputs = result.get("outputs", {})
        phase_agent = orchestrator._get_agent(phase)
        print(f"\n{status} {phase} - {phase_agent.phase_name}")
        if outputs:
            for filename in list(outputs.keys())[:3]:
                print(f"    - {filename}")

    # Show database state
    session.refresh(project)
    print(f"\n{'='*70}")
    print(f"DATABASE STATE")
    print(f"{'='*70}")
    print(f"Final Phase: {project.current_phase}")
    print(f"\nPhase History:")
    for phase, status_data in project.phase_statuses.items():
        status = status_data.get("status", "unknown")
        completed_at = status_data.get("completed_at", "N/A")
        print(f"  {phase}: {status}")

    # Show generated files
    print(f"\n{'='*70}")
    print(f"GENERATED FILES")
    print(f"{'='*70}")

    all_files = list(output_dir.rglob("*"))
    files = [f for f in all_files if f.is_file()]

    if not files:
        print("  No files generated!")
    else:
        for file_path in sorted(files):
            size = file_path.stat().st_size
            rel_path = file_path.relative_to(output_dir)
            print(f"  {rel_path} ({size} bytes)")

    # Show content of key files
    print(f"\n{'='*70}")
    print(f"FILE PREVIEWS")
    print(f"{'='*70}")

    key_files = [
        "requirements.md",
        "HRS_Interactive_V2_LED_Blinker.md",
        "glr_specification.md",
        "compliance_report.md",
        "netlist.json",
        "SRS_Interactive_V2_LED_Blinker.md",
        "SDD_Interactive_V2_LED_Blinker.md",
        "generated_code.md",
    ]

    for filename in key_files:
        filepath = output_dir / filename
        if filepath.exists():
            content = filepath.read_text(encoding="utf-8")
            lines = content.split('\n')
            preview = '\n'.join(lines[:20])
            print(f"\n--- {filename} ({len(lines)} lines, {filepath.stat().st_size} bytes) ---")
            print(preview)
            if len(lines) > 20:
                print(f"... ({len(lines) - 20} more lines)")

    # Check src directory
    src_dir = output_dir / "src"
    if src_dir.exists():
        print(f"\n--- Source Code Files (src/) ---")
        for code_file in sorted(src_dir.rglob("*")):
            if code_file.is_file():
                rel_path = code_file.relative_to(output_dir)
                size = code_file.stat().st_size
                print(f"  {rel_path} ({size} bytes)")

    print(f"\n{'='*70}")
    print(f"All files saved to: {output_dir.absolute()}")
    print(f"{'='*70}")

    session.close()
    engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(run_interactive_v2())
    except KeyboardInterrupt:
        print("\n\nInterrupted.")
    except Exception as e:
        print(f"\n\nError: {e}")
        import traceback
        traceback.print_exc()
