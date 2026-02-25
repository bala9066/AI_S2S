"""
Where to View Outputs - Quick Guide
Shows all locations where you can view test results and generated files
"""

from pathlib import Path


def show_output_locations():
    print("=" * 70)
    print("WHERE TO VIEW OUTPUTS - HARDWARE PIPELINE AI SYSTEM")
    print("=" * 70)

    base = Path.cwd()

    locations = {
        "HTML Coverage Report": base / "htmlcov" / "index.html",
        "JSON Coverage Data": base / "coverage.json",
        "Test Database": base / "test_pipeline.db",
        "Demo Database": base / "demo_pipeline.db",
        "Demo Project Output": base / "output" / "demo_led_blinker",
        "Real Demo Output": base / "output" / "real_demo_led_blinker",
    }

    print("\n[OUTPUT FILES]")
    print("-" * 70)

    for name, path in locations.items():
        exists = "[OK]" if path.exists() else "[--]"
        print(f"\n  [{exists}] {name}")
        print(f"      Path: {path}")

        if path.exists() and path.is_file():
            size = path.stat().st_size
            print(f"      Size: {size:,} bytes")
        elif path.exists() and path.is_dir():
            files = list(path.rglob("*"))
            file_count = len([f for f in files if f.is_file()])
            print(f"      Files: {file_count} files")

    print("\n" + "=" * 70)
    print("HOW TO VIEW:")
    print("=" * 70)

    print("""
1. HTML COVERAGE REPORT (Recommended):
   - Open: htmlcov/index.html
   - Shows: Line-by-line coverage, colored code, missed lines
   - Interactive: Click files to see details

2. JSON COVERAGE:
   - Open: coverage.json
   - Shows: Machine-readable coverage data
   - Use: For CI/CD integration

3. GENERATED PROJECT FILES:
   Run: python run_real_demo.py
   Then check: output/real_demo_led_blinker/

   Files you'll see:
   - HRS_<Project_Name>.md          (Hardware Requirements)
   - compliance_report.md           (Compliance validation)
   - netlist.json                   (Circuit connections)
   - glr_specification.md           (Register map)
   - SRS_<Project_Name>.md          (Software Requirements)
   - SDD_<Project_Name>.md          (Software Design)
   - src/                           (Generated C/C++ code)

4. DATABASE:
   - Open: demo_pipeline.db (use DB Browser for SQLite)
   - Tables: projects, phase_outputs
   - Shows: All phase results, timestamps, outputs

5. CONSOLE OUTPUT:
   - Run tests with: pytest tests/ -v
   - Run demo with: python run_demo_pipeline.py
   - Shows: Phase-by-phase execution progress
    """)

    print("\n" + "=" * 70)
    print("QUICK ACTIONS:")
    print("=" * 70)
    print("""
To see coverage:  start htmlcov/index.html
To run tests:     pytest tests/ -v
To run demo:      python run_demo_pipeline.py
To run REAL demo: python run_real_demo.py (uses API)
    """)

    # Check if we should open the coverage report
    coverage_html = base / "htmlcov" / "index.html"
    if coverage_html.exists():
        print("\n" + "=" * 70)
        response = input("Open coverage report in browser? (y/n): ").strip().lower()
        if response == 'y':
            import webbrowser
            webbrowser.open(str(coverage_html.absolute()))
            print("[OK] Opened coverage report in default browser")


if __name__ == "__main__":
    show_output_locations()
