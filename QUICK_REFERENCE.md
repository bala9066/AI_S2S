# 🚀 Quick Reference - Hardware Pipeline AI System

## 🎯 What Do You Want To Do?

### I want to SEE WHAT THE SYSTEM GENERATES
```bash
# View sample outputs (created for you)
cat output/sample_led_blinker/HRS_LED_Blinker.md
cat output/sample_led_blinker/netlist.json
cat output/sample_led_blinker/src/main.c
```
📄 **Sample Outputs README:** [SAMPLE_OUTPUTS_README.md](SAMPLE_OUTPUTS_README.md)

### I want to GENERATE REAL FILES
```bash
python run_interactive.py
```
Then:
1. Describe your project
2. Answer AI questions (3-5 rounds)
3. Type "done" when ready
4. Check `output/interactive_led_blinker/`

### I want to RUN TESTS
```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=. --cov-report=html

# View coverage report
start htmlcov/index.html
```
✅ **Current Status:** 116/116 tests passing (100%)

### I want to SEE WHERE OUTPUTS ARE
```bash
python show_outputs.py
```
Shows all output locations and opens coverage report.

### I want to UNDERSTAND THE SYSTEM
- [PATH_FORWARD_SUMMARY.md](PATH_FORWARD_SUMMARY.md) - Complete analysis and recommendations
- [OUTPUTS_GUIDE.md](OUTPUTS_GUIDE.md) - Where to find outputs
- [MASTER_PLAN.md](MASTER_PLAN.md) - Implementation roadmap
- [TASKS.md](TASKS.md) - Future development tasks

---

## 📊 Current System Status

| Component | Tests | Coverage | Status |
|-----------|-------|----------|--------|
| Core Agents | 116/116 | 90%+ | ✅ Working |
| Orchestrator | 15/15 | 93% | ✅ Working |
| Database | All pass | 91% | ✅ Working |
| Generators | 0 | 0% | ⚠️ Unused |
| Tools | 0 | 0% | ⚠️ Unused |
| Validators | 0 | 0% | ⚠️ Unused |

**Overall:** Production-ready core, needs integration work

---

## 🔑 Key Files

| File | Purpose |
|------|---------|
| `run_interactive.py` | **Best way** to generate real files |
| `run_demo_pipeline.py` | Fast mock demo (no real files) |
| `show_outputs.py` | Show all output locations |
| `pytest tests/` | Run test suite |
| `htmlcov/index.html` | Coverage report |

---

## 📁 Output Locations

```
output/
├── sample_led_blinker/          # Sample outputs (view these!)
│   ├── HRS_LED_Blinker.md
│   ├── netlist.json
│   └── src/main.c
├── interactive_led_blinker/      # From run_interactive.py
├── demo_led_blinker/             # From run_demo_pipeline.py (empty)
└── real_demo_led_blinker/        # From run_real_demo.py
```

---

## 🎯 Pipeline Phases (8 Total)

```
P1: Requirements Capture  →  P2: HRS Generation  →  P3: Compliance Validation
       (Conversational)          (IEEE 29148)           (RoHS, REACH)

P4: Netlist Generation  →  P6: GLR Generation  →  P8a: SRS Generation
    (Circuit graph)          (GPIO/Register)        (IEEE 830)

P8b: SDD Generation  →  P8c: Code Generation
     (IEEE 1016)           (C/C++ + Review)
```

---

## ⚡ Quick Commands

```bash
# Show everything
python show_outputs.py

# Run tests
pytest tests/ -v

# Interactive demo (best)
python run_interactive.py

# Fast demo (no files)
python run_demo_pipeline.py

# View coverage
start htmlcov/index.html
```

---

## 💡 Pro Tips

1. **Start with samples:** View `output/sample_led_blinker/` first
2. **Use interactive mode:** It's the only reliable way to get real files
3. **Check coverage:** Open `htmlcov/index.html` to see what's tested
4. **Be patient:** Phase 1 asks questions by design
5. **API key needed:** Ensure `.env` has `ANTHROPIC_API_KEY`

---

## 🐛 Troubleshooting

**Problem:** No files generated
**Solution:** Check API key in `.env`, use interactive mode

**Problem:** Phase 1 keeps asking questions
**Solution:** This is normal! Answer them or type "done"

**Problem:** Tests failing
**Solution:** Run `pytest tests/ -v` to see which tests fail

**Problem:** Can't find outputs
**Solution:** Run `python show_outputs.py`

---

## 📚 Documentation

- [QUICK_REFERENCE.md](QUICK_REFERENCE.md) - This file
- [PATH_FORWARD_SUMMARY.md](PATH_FORWARD_SUMMARY.md) - Complete analysis
- [OUTPUTS_GUIDE.md](OUTPUTS_GUIDE.md) - Output locations explained
- [SAMPLE_OUTPUTS_README.md](SAMPLE_OUTPUTS_README.md) - Sample files guide
- [MASTER_PLAN.md](MASTER_PLAN.md) - Implementation plan
- [TASKS.md](TASKS.md) - Future tasks

---

**Last Updated:** 2026-02-24
**Tests Passing:** 116/116 (100%)
**Coverage:** 90%+ on core agents
**Status:** ✅ Production-ready core
