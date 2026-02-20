# Hardware Pipeline - Future Tasks

## Overview
This document tracks remaining tasks and enhancements for the Hardware Pipeline AI system.

---

## Priority 1: Core Functionality Completion

### 1.1 Fix Agent Integration with Generators
**Status:** Partial - Agents use LLM generation instead of direct generator classes

**Task:** Update agents to use generator classes directly for consistent output
- [ ] `document_agent.py` - Use `HRSGenerator` instead of pure LLM generation
- [ ] `srs_agent.py` - Use `SRSGenerator`
- [ ] `sdd_agent.py` - Use `SDDGenerator`
- [ ] `netlist_agent.py` - Use `NetlistGenerator` + `NetlistValidator`
- [ ] `glr_agent.py` - Use `GLRGenerator`
- [ ] `code_agent.py` - Use `DriverGenerator` + `CodeReviewer`

**Files to modify:** `agents/document_agent.py`, `agents/srs_agent.py`, `agents/sdd_agent.py`, `agents/netlist_agent.py`, `agents/glr_agent.py`, `agents/code_agent.py`

---

### 1.2 Add Missing Type Hints
**Status:** Some modules missing proper typing

**Task:** Add type hints to all modules for better IDE support
- [ ] Add `List`, `Dict`, `Optional` imports where missing
- [ ] Fix `srs_generator.py` - missing `List`, `Dict` imports (currently fails lint)
- [ ] Fix `sdd_generator.py` - missing `List`, `Dict` imports

---

### 1.3 Component Search Integration
**Status:** Tool created but not integrated into agents

**Task:** Connect `ComponentSearchTool` to `RequirementsAgent`
- [ ] Initialize ChromaDB with sample components from `data/sample_components.json`
- [ ] Add `search_component` tool to `RequirementsAgent` tool list
- [ ] Fallback to `WebScraperTool` when ChromaDB has no matches
- [ ] Cache API results in database for offline use

---

## Priority 2: Testing & Validation

### 2.1 Unit Tests
**Status:** Test scaffolding exists, tests not implemented

**Task:** Implement unit tests for core modules
- [ ] `tests/test_config.py` - Test settings loading and fallback chain
- [ ] `tests/test_base_agent.py` - Test LLM fallback, tool calling
- [ ] `tests/test_orchestrator.py` - Test phase routing
- [ ] `tests/test_agents/` - Test each agent independently
- [ ] `tests/test_generators/` - Test all generators output format
- [ ] `tests/test_validators/` - Test IEEE validator, netlist validator
- [ ] `tests/test_rules/` - Test RoHS, REACH, FCC rule engines

**Run tests:** `pytest tests/ -v --cov=.`

---

### 2.2 Integration Tests
**Status:** Not started

**Task:** End-to-end pipeline tests
- [ ] Create `tests/integration/test_full_pipeline.py`
- [ ] Test with mock project: "Simple LED Controller"
- [ ] Verify all 8 phases execute in sequence
- [ ] Verify output files are generated correctly
- [ ] Verify database state after each phase

---

### 2.3 Real API Tests
**Status:** Not started

**Task:** Test with actual API keys
- [ ] Test DigiKey API search with real credentials
- [ ] Test Mouser API search with real credentials
- [ ] Test GLM-4 API fallback
- [ ] Test ChromaDB embedding generation

**Note:** Only run these tests locally with valid `.env`

---

## Priority 3: UI & UX Improvements

### 3.1 Streamlit Pages
**Status:** Only single `app.py` exists

**Task:** Split into separate pages as planned
- [ ] `pages/1_New_Project.py` - Project creation form
- [ ] `pages/2_Design_Chat.py` - Phase 1 conversational interface
- [ ] `pages/3_Documents.py` - View generated HRS/SRS/SDD
- [ ] `pages/4_Netlist_Viewer.py` - Interactive netlist visualization
- [ ] `pages/5_Code_Review.py` - Display code review reports
- [ ] `pages/6_Dashboard.py` - Project overview and phase status

---

### 3.2 Real-Time Progress Indicators
**Status:** Not implemented

**Task:** Add progress tracking during long-running operations
- [ ] Show spinner during LLM calls
- [ ] Display phase execution progress
- [ ] Show token usage/cost in real-time
- [ ] Add cancel button for long operations

---

### 3.3 Error Handling & Recovery
**Status:** Basic error handling exists

**Task:** Improve user-facing error messages
- [ ] Catch API errors and show friendly messages
- [ ] Provide retry buttons for failed operations
- [ ] Show suggested fixes for common errors
- [ ] Log detailed errors server-side, summary client-side

---

## Priority 4: Features & Enhancements

### 4.1 Git Integration
**Status:** Not implemented

**Task:** Automatic Git version control for generated artifacts
- [ ] Create GitPython wrapper in `tools/git_manager.py`
- [ ] Auto-commit after each phase completion
- [ ] Generate meaningful commit messages using LLM
- [ ] Create Git tags for project milestones
- [ ] Show diff view between document versions

---

### 4.2 Document Export
**Status:** Only markdown output

**Task:** Export to other formats
- [ ] Convert Markdown to PDF using `weasyprint` or `pandoc`
- [ ] Convert Markdown to DOCX for editing
- [ ] Bundle all documents into ZIP download
- [ ] Generate Bill of Materials (BOM) as XLSX

---

### 4.3 Requirement Traceability Matrix
**Status:** Static tables only

**Task:** Interactive traceability visualization
- [ ] Click on REQ-HW-xxx to see mapped REQ-SW-xxx
- [ ] Highlight components affected by requirement changes
- [ ] Show verification status for each requirement
- [ ] Export traceability matrix as XLSX

---

### 4.4 Netlist Visualization Enhancements
**Status:** Basic Mermaid diagram

**Task:** Interactive netlist viewer
- [ ] Use `mermaid.ink` or custom renderer for zoom/pan
- [ ] Color-code by signal type (power, data, control)
- [ ] Show pin details on hover
- [ ] Export as SVG/PNG

---

## Priority 5: Performance & Scalability

### 5.1 Caching Strategy
**Status:** Basic ChromaDB caching

**Task:** Implement multi-level caching
- [ ] Cache LLM responses for repeated prompts
- [ ] Cache component API responses with TTL
- [ ] Implement Redis for distributed caching (production)
- [ ] Show cache hit/miss metrics

---

### 5.2 Background Job Queue
**Status:** All operations synchronous

**Task:** Move long operations to background
- [ ] Implement Celery or background task queue
- [ ] Store job status in database
- [ ] Poll for job completion via WebSocket
- [ ] Send email/notification when job completes

---

### 5.3 Parallel Phase Execution
**Status:** Sequential execution only

**Task:** Execute independent phases in parallel
- [ ] Identify independent phases (e.g., SRS, SDD can run in parallel after HRS)
- [ ] Implement parallel execution using `asyncio.gather()`
- [ ] Show progress for multiple simultaneous phases

---

## Priority 6: Deployment

### 6.1 Docker Optimization
**Status:** Basic Dockerfile exists

**Task:** Production-ready container
- [ ] Multi-stage build to reduce image size
- [ ] Separate containers for API and UI
- [ ] Health check endpoints
- [ ] Graceful shutdown handling

---

### 6.2 CI/CD Pipeline
**Status:** Not implemented

**Task:** GitHub Actions or GitLab CI
- [ ] Run tests on every push
- [ ] Run linting (ruff, mypy)
- [ ] Build Docker image
- [ ] Deploy to staging on merge to main
- [ ] Semantic versioning

---

### 6.3 Production Configuration
**Status:** Development defaults only

**Task:** Production-ready configuration
- [ ] Separate config for dev/staging/prod
- [ ] Environment variable validation on startup
- [ ] Secrets management (e.g., HashiCorp Vault)
- [ ] Logging to centralized service (e.g., ELK)

---

## Priority 7: Documentation

### 7.1 User Documentation
**Status:** Synopsis exists

**Task:** End-user guides
- [ ] User manual with screenshots
- [ ] Tutorial videos
- [ ] API documentation (auto-generate from FastAPI)
- [ ] Troubleshooting guide

---

### 7.2 Developer Documentation
**Status:** In-code comments minimal

**Task:** Developer onboarding docs
- [ ] Architecture overview diagram
- [ ] Adding a new agent guide
- [ ] Adding a new generator guide
- [ ] Contributing guidelines
- [ ] Code style guide

---

## Priority 8: Advanced Features (Future)

### 8.1 AI Model Fine-Tuning
- [ ] Fine-tune smaller model for hardware domain
- [ ] Reduce API costs and latency
- [ ] Better component recommendations

### 8.2 Multi-User Support
- [ ] User authentication (OAuth, SSO)
- [ ] Project sharing and collaboration
- [ ] Role-based access control

### 8.3 Component Lifecycle Management
- [ ] EOL notifications for selected components
- [ ] Second-source recommendations
- [ ] Price tracking and alerts

### 8.4 Simulation Integration
- [ ] SPICE netlist export
- [ ] LTSpice integration
- [ ] FPGA bitstream generation

---

## Quick Start for Next Session

1. **Fix type hints in generators** (10 min)
   ```bash
   # Add missing imports to srs_generator.py and sdd_generator.py
   from typing import List, Dict
   ```

2. **Test full pipeline** (15 min)
   ```bash
   # Run the orchestrator with a test project
   python -c "
   import asyncio
   from agents.orchestrator import OrchestratorAgent
   from database.models import get_session

   async def test():
       orch = OrchestratorAgent()
       session = get_session()
       result = await orch.execute_phase(1, 'P1', 'Design an LED controller', session)
       print(result)

   asyncio.run(test())
   "
   ```

3. **Split Streamlit into pages** (30 min)
   - Create `pages/` directory structure
   - Move chat logic to `pages/2_Design_Chat.py`
   - Add document viewer page

---

## Repository Links

- **GitHub:** https://github.com/bala9066/AI_S2S
- **Branch:** `main`
- **Latest Commit:** `6357fcc`

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-02-20 | Initial scaffolding, 8 agents, tools, generators |
| 0.2 | TBD | Fix type hints, integrate generators, add tests |
| 1.0 | TBD | Production-ready release |
