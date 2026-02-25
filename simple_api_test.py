"""
Simple API Key Test - Run this to verify your setup

Usage:
    python simple_api_test.py
"""

import asyncio
import sys


async def main():
    print("=" * 60)
    print("HARDWARE PIPELINE - SIMPLE API TEST")
    print("=" * 60)

    # Test 1: Check API key
    print("\n[1/4] Checking API Key Configuration...")
    try:
        from config import settings

        if settings.anthropic_api_key:
            key = settings.anthropic_api_key
            print(f"  OK - API Key configured: {key[:10]}...{key[-4:]}")
            print(f"  OK - Primary Model: {settings.primary_model}")
        else:
            print("  FAIL - No API key found!")
            print("\n  To fix:")
            print("  1. Get key from: https://console.anthropic.com/")
            print("  2. Add to .env: ANTHROPIC_API_KEY=sk-ant-...")
            return
    except Exception as e:
        print(f"  FAIL - Error: {e}")
        return

    # Test 2: Test LLM Connection
    print("\n[2/4] Testing LLM Connection...")
    try:
        from agents.base_agent import BaseAgent

        class TestAgent(BaseAgent):
            def __init__(self):
                super().__init__(phase_number="TEST", phase_name="Test")
            def get_system_prompt(self, ctx):
                return "Test"
            async def execute(self, ctx, inp):
                return {}

        agent = TestAgent()
        response = await agent.call_llm(
            messages=[{"role": "user", "content": "Say 'OK'"}]
        )

        if "OK" in response.get("content", ""):
            print(f"  OK - API Response: {response.get('content', '')[:50]}")
            print(f"  OK - Model: {response.get('model_used', 'unknown')}")
        else:
            print(f"  FAIL - Unexpected response")
    except Exception as e:
        print(f"  FAIL - Error: {e}")
        return

    # Test 3: Test Generators
    print("\n[3/4] Testing Generators...")
    try:
        from generators.hrs_generator import HRSGenerator

        hrs_gen = HRSGenerator()
        hrs = hrs_gen.generate(
            project_name="Test",
            requirements=[{"id": "R1", "text": "Test", "priority": "HIGH"}]
        )
        print(f"  OK - HRS Generator: {len(hrs)} chars")
    except Exception as e:
        print(f"  FAIL - Error: {e}")

    # Test 4: Test CodeReviewer
    print("\n[4/4] Testing CodeReviewer...")
    try:
        from reviewers.code_reviewer import CodeReviewer

        reviewer = CodeReviewer()
        result = reviewer.review_code("void f() { int x = 1; }", "c")
        print(f"  OK - CodeReviewer: Score {result['score']}/100")
    except Exception as e:
        print(f"  FAIL - Error: {e}")

    # Summary
    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)
    print("\nIf all tests passed, you're ready to use the system!")
    print("\nNext steps:")
    print("  1. Run interactive: python run_interactive.py")
    print("  2. Run Streamlit:  streamlit run app.py")
    print("  3. Read setup guide: API_KEY_SETUP.md")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
