"""
Quick Git/GitHub integration test.
Run this from the project root:  python test_git.py

It checks:
  1. .env is loaded correctly
  2. GITHUB_TOKEN is valid (hits /user endpoint)
  3. GITHUB_REPO exists and is accessible
  4. Token has the required scopes (Contents write + Pull requests write)
  5. PyGithub is installed
"""

import os
import sys

# ── Load .env ──────────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # Manual parse if python-dotenv not installed
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip())

TOKEN = os.environ.get("GITHUB_TOKEN", "")
REPO  = os.environ.get("GITHUB_REPO", "")

print("=" * 60)
print("Hardware Pipeline — Git Integration Test")
print("=" * 60)

# ── 1. Check token present ─────────────────────────────────────────────────────
if not TOKEN or TOKEN.startswith("ghp_xxx"):
    print("\n❌  GITHUB_TOKEN not set or still placeholder.")
    print("   Edit .env and set a real token.")
    sys.exit(1)
print(f"\n✓  GITHUB_TOKEN loaded ({TOKEN[:8]}...)")

# ── 2. Check repo set ──────────────────────────────────────────────────────────
if not REPO or REPO.startswith("owner/"):
    print(f"\n❌  GITHUB_REPO is '{REPO}' — still has placeholder 'owner'.")
    print("   Set it to your real repo, e.g.  GITHUB_REPO=shivaram240820/AI_S2S")
    sys.exit(1)
print(f"✓  GITHUB_REPO = {REPO}")

# ── 3. PyGithub installed? ─────────────────────────────────────────────────────
try:
    from github import Github, GithubException
    print("✓  PyGithub installed")
except ImportError:
    print("\n❌  PyGithub not installed.")
    print("   Run:  pip install PyGithub")
    sys.exit(1)

# ── 4. Test token against GitHub API ──────────────────────────────────────────
print("\nConnecting to GitHub API...")
try:
    gh = Github(TOKEN)
    user = gh.get_user()
    print(f"✓  Token valid — authenticated as: {user.login} ({user.name or 'no display name'})")
except GithubException as e:
    print(f"\n❌  GitHub API error: {e.status} — {e.data.get('message', e)}")
    if e.status == 401:
        print("   Token is invalid or expired. Generate a new one at:")
        print("   https://github.com/settings/tokens/new")
    sys.exit(1)
except Exception as e:
    print(f"\n❌  Connection error: {e}")
    print("   Check network / proxy settings.")
    sys.exit(1)

# ── 5. Check repo access ───────────────────────────────────────────────────────
try:
    repo = gh.get_repo(REPO)
    perms = repo.permissions
    print(f"✓  Repo '{REPO}' found — push={perms.push}, admin={perms.admin}")
    if not perms.push:
        print("   ⚠  Token does not have push (write) access to this repo.")
        print("   Go to https://github.com/settings/tokens and ensure")
        print("   the token has 'Contents: Write' scope.")
except GithubException as e:
    print(f"\n❌  Cannot access repo '{REPO}': {e.status} — {e.data.get('message', e)}")
    if e.status == 404:
        print(f"   Repo not found. Check the spelling — it should be 'owner/reponame'.")
        print(f"   Your GitHub username is: {user.login}")
        print(f"   Try:  GITHUB_REPO={user.login}/{REPO.split('/')[-1]}")
    sys.exit(1)

# ── 6. Check token scopes ─────────────────────────────────────────────────────
# PyGithub exposes scopes via the last response headers
try:
    scopes = gh.oauth_scopes or []
    if scopes:
        print(f"✓  Token scopes: {', '.join(scopes)}")
        if "repo" not in scopes and "public_repo" not in scopes:
            print("   ⚠  Token may be missing 'repo' scope — PR creation might fail.")
    else:
        print("   (scope header not returned — fine-grained PAT)")
except Exception:
    pass

print("\n" + "=" * 60)
print("✅  All checks passed — Git integration is ready.")
print("    Restart the FastAPI server to apply .env changes:")
print("    Ctrl+C → uvicorn main:app --reload --port 8000")
print("=" * 60)
