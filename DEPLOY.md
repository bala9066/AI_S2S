# Hardware Pipeline — Deploy on a New PC

## Prerequisites (install once on the new PC)

| Tool | Download | Notes |
|------|----------|-------|
| **Python 3.10+** | https://python.org/downloads/ | Check ✅ "Add Python to PATH" |
| **Git** *(optional)* | https://git-scm.com/ | Only needed for the Git clone method |

---

## Method A — One-Click from USB / Folder Copy (Recommended)

1. **Copy the entire project folder** to the new PC (USB drive, shared folder, etc.)
2. **Copy your `.env` file** into the project folder root (contains your API keys)
3. **Copy `hardware_pipeline.db`** if you want to keep your existing projects
4. Double-click **`INSTALL.bat`**

That's it. The script installs all Python packages and opens the app at `http://localhost:8000/app`.

---

## Method B — Clone from GitHub

```cmd
git clone https://github.com/bala9066/AI_S2S.git
cd AI_S2S
```

Then copy your `.env` file into the `AI_S2S` folder and double-click **`INSTALL.bat`**.

> ⚠️ The `.env` file and database (`hardware_pipeline.db`) are **not** on GitHub for security.
> You must copy them manually from your original PC.

---

## What to Copy Between PCs

| File / Folder | Required | Purpose |
|---------------|----------|---------|
| `.env` | **YES** | Your API keys (GLM, DeepSeek, etc.) |
| `hardware_pipeline.db` | Optional | Your existing projects |
| `output/` | Optional | Generated documents for existing projects |

---

## Your `.env` Keys (minimum required)

Open `.env` and make sure at least one LLM key is filled:

```env
# Primary LLM (at least one required)
GLM_API_KEY=ef9bb2855a4c4fb6b41c0fbec2f03708.tJryP8doyZnJdgVC
GLM_BASE_URL=https://api.z.ai/api/anthropic
GLM_MODEL=glm-4.7
GLM_FAST_MODEL=glm-4.5-air

# Model selection
PRIMARY_MODEL=glm-4.7
FAST_MODEL=glm-4.5-air

# Database
DATABASE_URL=sqlite:///hardware_pipeline.db
```

---

## After First Launch

- App: **http://localhost:8000/app**
- API docs: **http://localhost:8000/docs**
- Keep the **"S2S — FastAPI Backend"** terminal window open while working.
- To restart: just double-click `run.bat` (after first install).

---

## Running Daily (after first setup)

Double-click **`run.bat`** — it starts the backend and opens the browser.
No need to re-install packages every time.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "Python not found" | Install Python 3.10+ and check "Add to PATH" |
| Port 8000 in use | Close other apps using port 8000, or reboot |
| API errors / phases failing | Check your API keys in `.env` |
| Projects missing after copy | Also copy `hardware_pipeline.db` + `output/` folder |
| ChromaDB seeding errors on startup | Normal — wait ~60s, it's downloading embeddings |
