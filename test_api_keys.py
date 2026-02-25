"""
Quick API Key Testing Script

Run this to verify your API keys are configured correctly.
"""

import asyncio
import sys
from pathlib import Path


async def test_anthropic_api():
    """Test Anthropic API connection."""
    print("\n" + "=" * 60)
    print("Testing Anthropic API Connection")
    print("=" * 60)

    try:
        from config import settings

        if not settings.anthropic_api_key:
            print("FAIL: Anthropic API key not configured")
            print("\nTo fix:")
            print("1. Get API key from https://console.anthropic.com/")
            print("2. Add to .env file: ANTHROPIC_API_KEY=sk-ant-...")
            print("3. Or export: export ANTHROPIC_API_KEY=sk-ant-...")
            return False

        key = settings.anthropic_api_key
        print(f"OK - API Key found: {key[:10]}...{key[-4:]}")
        print(f"OK - Primary Model: {settings.primary_model}")
        print(f"OK - Fast Model: {settings.fast_model}")

        # Test actual API call
        from agents.base_agent import BaseAgent

        class TestAgent(BaseAgent):
            def __init__(self):
                super().__init__(phase_number="TEST", phase_name="Test", max_tokens=100)

            def get_system_prompt(self, project_context):
                return "You are a helpful assistant."

            async def execute(self, project_context, user_input):
                return {"response": "test"}

        agent = TestAgent()
        print("\nTesting API call...")

        response = await agent.call_llm(
            messages=[{
                "role": "user",
                "content": "Please respond with exactly: 'API connection successful'"
            }],
            system="You are a helpful assistant.",
        )

        content = response.get("content", "")
        if "API connection successful" in content.lower():
            print("SUCCESS: API call completed")
            print(f"OK - Response: {content[:100]}")
            print(f"OK - Model used: {response.get('model_used', 'unknown')}")
            print(f"OK - Tokens: {response['usage']['input_tokens']} in, {response['usage']['output_tokens']} out")
            return True
        else:
            print("FAIL: Unexpected response")
            print(f"   Got: {content[:100]}")
            return False

    except Exception as e:
        print(f"FAIL: {str(e)}")
        return False


async def test_generators():
    """Test generator functionality."""
    print("\n" + "=" * 60)
    print("Testing Generator Functionality")
    print("=" * 60)

    try:
        from generators.hrs_generator import HRSGenerator
        from generators.netlist_generator import NetlistGenerator
        from generators.code_reviewer import CodeReviewer

        # Test HRS Generator
        print("\n🔄 Testing HRS Generator...")
        hrs_gen = HRSGenerator()
        hrs = hrs_gen.generate(
            project_name="API Test Project",
            requirements=[{"id": "REQ-001", "text": "Test requirement", "priority": "HIGH"}],
            metadata={"version": "1.0"}
        )
        print(f"OK HRS Generator: {len(hrs)} characters generated")

        # Test Netlist Generator
        print("\n🔄 Testing Netlist Generator...")
        netlist_gen = NetlistGenerator()
        netlist = netlist_gen.generate(
            project_name="API Test",
            components=[{"id": "U1", "name": "MCU", "type": "IC", "pins": []}],
            connections=[]
        )
        print(f"OK Netlist Generator: {len(netlist['nodes'])} nodes generated")

        # Test CodeReviewer
        print("\n🔄 Testing CodeReviewer...")
        reviewer = CodeReviewer()
        test_code = """
void test() {
    char *p = malloc(100);
    strcpy(p, "test");
    free(p);
}
"""
        result = reviewer.review_code(test_code, language="c")
        print(f"OK CodeReviewer: Score {result['score']}/100, {result['total_issues']} issues")

        return True

    except Exception as e:
        print(f"FAIL FAIL: {str(e)}")
        return False


async def test_component_search():
    """Test ComponentSearchTool (optional)."""
    print("\n" + "=" * 60)
    print("Testing ComponentSearchTool (Optional)")
    print("=" * 60)

    try:
        from tools.component_search import ComponentSearchTool

        print("\n🔄 Initializing ComponentSearchTool...")
        tool = ComponentSearchTool()
        stats = tool.get_stats()

        print(f"OK ComponentSearchTool initialized")
        print(f"   Components cached: {stats['total_components']}")
        print(f"   Categories: {list(stats.get('categories', {}).keys())}")

        if stats['total_components'] > 0:
            print("\n🔄 Testing search...")
            results = tool.search("MCU", n_results=2)
            print(f"OK Search completed: {len(results)} results found")
            if results:
                print(f"   Top result: {results[0].component.part_number}")
        else:
            print("WARN️  No components in cache (optional feature)")
            print("   To populate: Run data/populate_components.py (if available)")

        return True

    except ImportError as e:
        print("WARN️  ComponentSearchTool not available (ChromaDB)")
        print("   This is optional - system will use LLM fallback")
        return True
    except Exception as e:
        print(f"WARN️  ComponentSearchTool error: {str(e)[:100]}")
        return True


async def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("HARDWARE PIPELINE - API KEY & GENERATOR TEST")
    print("=" * 60)

    results = []

    # Test Anthropic API
    results.append(await test_anthropic_api())

    # Test Generators
    results.append(await test_generators())

    # Test Component Search
    results.append(await test_component_search())

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    total = len(results)
    passed = sum(results)

    print(f"Tests Passed: {passed}/{total}")

    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
        print("\nYou're ready to use the Hardware Pipeline AI System!")
        print("\nNext steps:")
        print("1. Run interactive mode: python run_interactive.py")
        print("2. Start Streamlit UI: streamlit run app.py")
        print("3. Run full test: python test_full_architecture.py")
    else:
        print("\nWARN️  SOME TESTS FAILED")
        print("\nPlease check the errors above and:")
        print("1. Verify your .env file has correct API keys")
        print("2. Check that you've installed all dependencies")
        print("3. Review API_KEY_SETUP.md for detailed instructions")

    print("=" * 60)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
    except Exception as e:
        print(f"\n\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
