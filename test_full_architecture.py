"""
Full Architecture Testing Script

This script tests the complete Hardware Pipeline AI System with real API keys.
It validates:
1. All agent imports and initialization
2. Generator functionality
3. Tool integration (ComponentSearchTool, CodeReviewer)
4. End-to-end pipeline flow
5. API key configuration

Usage:
    python test_full_architecture.py
"""

import asyncio
import json
import logging
from pathlib import Path
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ArchitectureTester:
    """Test the full Hardware Pipeline architecture."""

    def __init__(self):
        self.results = {
            "timestamp": datetime.now().isoformat(),
            "tests": [],
            "summary": {},
        }

    def log_test(self, test_name: str, status: str, details: str = ""):
        """Log a test result."""
        result = {
            "test": test_name,
            "status": status,
            "details": details,
            "timestamp": datetime.now().isoformat(),
        }
        self.results["tests"].append(result)
        icon = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️ "
        logger.info(f"{icon} {test_name}: {status}")
        if details:
            logger.info(f"   {details}")

    def test_api_keys(self):
        """Test API key configuration."""
        logger.info("\n" + "=" * 70)
        logger.info("TEST 1: API Key Configuration")
        logger.info("=" * 70)

        try:
            from config import settings

            # Check Anthropic API key
            if settings.anthropic_api_key:
                self.log_test(
                    "Anthropic API Key",
                    "PASS",
                    f"Key found: {settings.anthropic_api_key[:10]}...{settings.anthropic_api_key[-4:]}"
                )
            else:
                self.log_test("Anthropic API Key", "FAIL", "No API key found")

            # Check OpenAI API key (for embeddings)
            if settings.openai_api_key:
                self.log_test(
                    "OpenAI API Key",
                    "PASS",
                    f"Key found: {settings.openai_api_key[:10]}...{settings.openai_api_key[-4:]}"
                )
            else:
                self.log_test("OpenAI API Key", "WARN", "Not configured (optional)")

            # Check GLM API key
            if settings.glm_api_key:
                self.log_test(
                    "GLM API Key",
                    "PASS",
                    f"Key found: {settings.glm_api_key[:10]}...{settings.glm_api_key[-4:]}"
                )
            else:
                self.log_test("GLM API Key", "WARN", "Not configured (optional fallback)")

            # Check models
            self.log_test("Primary Model", "PASS", f"{settings.primary_model}")
            self.log_test("Fast Model", "PASS", f"{settings.fast_model}")
            self.log_test("Fallback Chain", "PASS", f"{settings.fallback_chain}")

            return True

        except Exception as e:
            self.log_test("API Key Configuration", "FAIL", str(e))
            return False

    def test_agent_imports(self):
        """Test all agent imports."""
        logger.info("\n" + "=" * 70)
        logger.info("TEST 2: Agent Imports")
        logger.info("=" * 70)

        agents = [
            ("RequirementsAgent", "agents.requirements_agent"),
            ("DocumentAgent", "agents.document_agent"),
            ("ComplianceAgent", "agents.compliance_agent"),
            ("NetlistAgent", "agents.netlist_agent"),
            ("GLRAgent", "agents.glr_agent"),
            ("SRSAgent", "agents.srs_agent"),
            ("SDDAgent", "agents.sdd_agent"),
            ("CodeAgent", "agents.code_agent"),
            ("Orchestrator", "agents.orchestrator"),
        ]

        for agent_name, module_path in agents:
            try:
                module = __import__(module_path, fromlist=[agent_name])
                agent_class = getattr(module, agent_name)
                self.log_test(f"{agent_name} Import", "PASS", f"Class: {agent_class}")
            except Exception as e:
                self.log_test(f"{agent_name} Import", "FAIL", str(e))

    def test_agent_initialization(self):
        """Test all agent initialization."""
        logger.info("\n" + "=" * 70)
        logger.info("TEST 3: Agent Initialization")
        logger.info("=" * 70)

        try:
            from agents.requirements_agent import RequirementsAgent
            from agents.document_agent import DocumentAgent
            from agents.compliance_agent import ComplianceAgent
            from agents.netlist_agent import NetlistAgent
            from agents.glr_agent import GLRAgent
            from agents.srs_agent import SRSAgent
            from agents.sdd_agent import SDDAgent
            from agents.code_agent import CodeAgent

            # Initialize each agent
            agents = [
                ("RequirementsAgent", RequirementsAgent(), "component_search"),
                ("DocumentAgent", DocumentAgent(), "hrs_generator"),
                ("ComplianceAgent", ComplianceAgent(), None),
                ("NetlistAgent", NetlistAgent(), "netlist_generator"),
                ("GLRAgent", GLRAgent(), "glr_generator"),
                ("SRSAgent", SRSAgent(), "srs_generator"),
                ("SDDAgent", SDDAgent(), "sdd_generator"),
                ("CodeAgent", CodeAgent(), "driver_generator"),
            ]

            for name, agent, tool_attr in agents:
                if tool_attr:
                    has_tool = hasattr(agent, tool_attr)
                    status = "PASS" if has_tool else "FAIL"
                    self.log_test(f"{name} Init", status, f"{tool_attr}: {has_tool}")
                else:
                    self.log_test(f"{name} Init", "PASS", "No generator/tool")

        except Exception as e:
            self.log_test("Agent Initialization", "FAIL", str(e))

    def test_generators(self):
        """Test all generator classes."""
        logger.info("\n" + "=" * 70)
        logger.info("TEST 4: Generator Functionality")
        logger.info("=" * 70)

        try:
            from generators.hrs_generator import HRSGenerator
            from generators.netlist_generator import NetlistGenerator
            from generators.glr_generator import GLRGenerator
            from generators.srs_generator import SRSGenerator
            from generators.sdd_generator import SDDGenerator
            from generators.driver_generator import DriverGenerator

            # Test HRS Generator
            hrs_gen = HRSGenerator()
            hrs_content = hrs_gen.generate(
                project_name="Test Project",
                requirements=[{"id": "REQ-001", "text": "Test", "priority": "HIGH"}],
                metadata={"version": "1.0"}
            )
            self.log_test("HRSGenerator", "PASS", f"Generated {len(hrs_content)} chars")

            # Test Netlist Generator
            netlist_gen = NetlistGenerator()
            netlist = netlist_gen.generate(
                project_name="Test",
                components=[{"id": "U1", "name": "MCU", "type": "IC", "pins": []}],
                connections=[{"source": "U1", "source_pin": "1", "target": "U1", "target_pin": "2", "signal": "NET"}]
            )
            self.log_test("NetlistGenerator", "PASS", f"{len(netlist['nodes'])} nodes, {len(netlist['edges'])} edges")

            # Test GLR Generator
            glr_gen = GLRGenerator()
            glr_content = glr_gen.generate(project_name="Test", netlist={}, requirements=[])
            self.log_test("GLRGenerator", "PASS", f"Generated {len(glr_content)} chars")

            # Test SRS Generator
            srs_gen = SRSGenerator()
            srs_content = srs_gen.generate(project_name="Test", hw_requirements=[], sw_features=[])
            self.log_test("SRSGenerator", "PASS", f"Generated {len(srs_content)} chars")

            # Test SDD Generator
            sdd_gen = SDDGenerator()
            sdd_content = sdd_gen.generate(project_name="Test", modules=[], interfaces=[], state_machines=[])
            self.log_test("SDDGenerator", "PASS", f"Generated {len(sdd_content)} chars")

            # Test Driver Generator
            driver_gen = DriverGenerator()
            files = driver_gen.generate(project_name="Test", components=[], registers=[])
            self.log_test("DriverGenerator", "PASS", f"Generated {len(files)} files")

        except Exception as e:
            self.log_test("Generator Tests", "FAIL", str(e))

    def test_code_reviewer(self):
        """Test CodeReviewer functionality."""
        logger.info("\n" + "=" * 70)
        logger.info("TEST 5: CodeReviewer")
        logger.info("=" * 70)

        try:
            from reviewers.code_reviewer import CodeReviewer

            reviewer = CodeReviewer()

            # Test code with various issues
            test_code = """
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

void test_function() {
    char *ptr = malloc(100);
    strcpy(ptr, "test");
    goto label;
    label:
    free(ptr);
}
"""

            result = reviewer.review_code(
                code=test_code,
                language="c",
                standards=["MISRA-C-2012"]
            )

            self.log_test("CodeReviewer Init", "PASS", "CodeReviewer initialized")
            self.log_test("Code Review", "PASS", f"Score: {result['score']}/100")
            self.log_test("Issues Found", "PASS", f"{result['total_issues']} issues")
            self.log_test("Critical Issues", "PASS", f"{result['critical_issues']} critical")
            self.log_test("Warnings", "PASS", f"{result['warnings']} warnings")

        except Exception as e:
            self.log_test("CodeReviewer Tests", "FAIL", str(e))

    async def test_llm_connection(self):
        """Test LLM API connection."""
        logger.info("\n" + "=" * 70)
        logger.info("TEST 6: LLM API Connection")
        logger.info("=" * 70)

        try:
            from agents.base_agent import BaseAgent

            # Create a test agent
            class TestAgent(BaseAgent):
                def __init__(self):
                    super().__init__(
                        phase_number="TEST",
                        phase_name="Test",
                        max_tokens=100,
                    )

                def get_system_prompt(self, project_context):
                    return "You are a helpful assistant."

                async def execute(self, project_context, user_input):
                    return {"response": "test"}

            agent = TestAgent()

            # Test LLM call
            response = await agent.call_llm(
                messages=[{"role": "user", "content": "Say 'API test successful' in exactly that phrase."}],
                system="You are a helpful assistant.",
            )

            if "API test successful" in response.get("content", ""):
                self.log_test("LLM Connection", "PASS", f"Model: {response.get('model_used', 'unknown')}")
                self.log_test("LLM Response", "PASS", "Response received correctly")
            else:
                self.log_test("LLM Response", "FAIL", "Unexpected response")

        except Exception as e:
            self.log_test("LLM Connection", "FAIL", str(e))

    def test_component_search(self):
        """Test ComponentSearchTool (if available)."""
        logger.info("\n" + "=" * 70)
        logger.info("TEST 7: ComponentSearchTool")
        logger.info("=" * 70)

        try:
            from tools.component_search import ComponentSearchTool

            tool = ComponentSearchTool()
            stats = tool.get_stats()

            self.log_test("ComponentSearchTool Init", "PASS", f"Components cached: {stats['total_components']}")

            if stats['total_components'] > 0:
                # Test search
                results = tool.search("MCU microcontroller", n_results=3)
                self.log_test("Component Search", "PASS", f"Found {len(results)} results")

                if results:
                    top_result = results[0]
                    self.log_test("Top Result", "PASS", f"{top_result.component.part_number} - {top_result.component.description}")
            else:
                self.log_test("Component Search", "WARN", "No components in cache (run data/populate_components.py)")

        except ImportError as e:
            self.log_test("ComponentSearchTool", "WARN", f"ChromaDB not available: {str(e)[:50]}...")
        except Exception as e:
            self.log_test("ComponentSearchTool", "FAIL", str(e))

    async def test_mini_pipeline(self):
        """Test a mini end-to-end pipeline."""
        logger.info("\n" + "=" * 70)
        logger.info("TEST 8: Mini End-to-End Pipeline")
        logger.info("=" * 70)

        try:
            from pathlib import Path
            from generators.hrs_generator import HRSGenerator
            from generators.netlist_generator import NetlistGenerator

            # Create test output directory
            output_dir = Path("output/test_pipeline")
            output_dir.mkdir(parents=True, exist_ok=True)

            # Simulate Phase 1: Requirements
            requirements = [
                {"id": "REQ-HW-001", "text": "System shall operate from 12V DC", "priority": "HIGH"},
                {"id": "REQ-HW-002", "text": "System shall consume <5W power", "priority": "HIGH"},
            ]

            # Simulate Phase 2: HRS Generation
            hrs_gen = HRSGenerator()
            hrs_content = hrs_gen.generate(
                project_name="Mini Test Project",
                requirements=requirements,
                metadata={"version": "1.0", "author": "Test Suite"}
            )
            hrs_file = hrs_gen.save(hrs_content, output_dir, "Mini Test Project")
            self.log_test("Phase 2 - HRS", "PASS", f"HRS generated: {hrs_file.name}")

            # Simulate Phase 4: Netlist Generation
            netlist_gen = NetlistGenerator()
            netlist = netlist_gen.generate(
                project_name="Mini Test Project",
                components=[
                    {"id": "U1", "name": "MCU", "type": "IC", "pins": []},
                    {"id": "R1", "name": "Resistor", "type": "Resistor", "pins": []},
                ],
                connections=[
                    {"source": "U1", "source_pin": "1", "target": "R1", "target_pin": "1", "signal": "GPIO_1"}
                ]
            )
            netlist_file = netlist_gen.save(netlist, output_dir, "Mini Test Project")
            self.log_test("Phase 4 - Netlist", "PASS", f"Netlist generated: {netlist_file.name}")

            self.log_test("Mini Pipeline", "PASS", "All phases completed successfully")

        except Exception as e:
            self.log_test("Mini Pipeline", "FAIL", str(e))

    def save_results(self):
        """Save test results to file."""
        output_dir = Path("output")
        output_dir.mkdir(parents=True, exist_ok=True)

        results_file = output_dir / f"architecture_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        results_file.write_text(json.dumps(self.results, indent=2), encoding="utf-8")

        logger.info(f"\n📊 Results saved to: {results_file}")

    def print_summary(self):
        """Print test summary."""
        logger.info("\n" + "=" * 70)
        logger.info("TEST SUMMARY")
        logger.info("=" * 70)

        total = len(self.results["tests"])
        passed = sum(1 for t in self.results["tests"] if t["status"] == "PASS")
        failed = sum(1 for t in self.results["tests"] if t["status"] == "FAIL")
        warned = sum(1 for t in self.results["tests"] if t["status"] == "WARN")

        logger.info(f"Total Tests: {total}")
        logger.info(f"✅ Passed: {passed}")
        logger.info(f"⚠️  Warnings: {warned}")
        logger.info(f"❌ Failed: {failed}")

        if failed == 0:
            logger.info("\n🎉 ALL TESTS PASSED!")
        else:
            logger.info(f"\n⚠️  {failed} test(s) failed")

        self.results["summary"] = {
            "total": total,
            "passed": passed,
            "failed": failed,
            "warned": warned,
            "success_rate": f"{(passed/total*100):.1f}%" if total > 0 else "0%"
        }


async def main():
    """Run all tests."""
    print("\n" + "=" * 70)
    print("HARDWARE PIPELINE AI SYSTEM - FULL ARCHITECTURE TEST")
    print("=" * 70)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    tester = ArchitectureTester()

    # Run all tests
    tester.test_api_keys()
    tester.test_agent_imports()
    tester.test_agent_initialization()
    tester.test_generators()
    tester.test_code_reviewer()
    await tester.test_llm_connection()
    tester.test_component_search()
    await tester.test_mini_pipeline()

    # Print summary and save results
    tester.print_summary()
    tester.save_results()

    print(f"\nCompleted at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
