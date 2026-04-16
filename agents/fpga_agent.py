"""
Phase 7: FPGA Design Agent

AI-powered RTL code generation from GLR specification + Register Map.
Generates synthesisable Verilog HDL, testbench, and Vivado timing constraints.

Outputs:
  - fpga_top.v              — Top-level Verilog module (glue logic + state machines)
  - fpga_testbench.v        — Self-checking SystemVerilog testbench
  - constraints.xdc         — Vivado XDC timing & I/O constraints
  - fpga_design_report.md   — Design summary (resource estimate, FSM diagram, timing)
"""

import logging
import re
from pathlib import Path
from typing import Dict

from agents.base_agent import BaseAgent
from config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool definition
# ---------------------------------------------------------------------------

GENERATE_FPGA_TOOL = {
    "name": "generate_fpga_design",
    "description": (
        "Generate a complete FPGA RTL design: Verilog top module, testbench, "
        "XDC constraints, and design report."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "module_name": {
                "type": "string",
                "description": "Top-level Verilog module name (e.g. bldc_glue_logic)",
            },
            "clock_frequency_mhz": {
                "type": "number",
                "description": "Target clock frequency in MHz (e.g. 100.0)",
            },
            "fpga_part": {
                "type": "string",
                "description": "Xilinx part number (e.g. xc7a35tcpg236-1)",
            },
            "ports": {
                "type": "array",
                "description": "Top-level I/O ports",
                "items": {
                    "type": "object",
                    "properties": {
                        "name":        {"type": "string"},
                        "direction":   {"type": "string", "description": "input / output / inout"},
                        "width":       {"type": "integer", "description": "Bus width (1 for scalar)"},
                        "description": {"type": "string"},
                    },
                    "required": ["name", "direction", "width"],
                },
            },
            "state_machines": {
                "type": "array",
                "description": "FSMs to implement",
                "items": {
                    "type": "object",
                    "properties": {
                        "name":   {"type": "string"},
                        "states": {"type": "array", "items": {"type": "string"}},
                        "description": {"type": "string"},
                    },
                    "required": ["name", "states"],
                },
            },
            "verilog_top": {
                "type": "string",
                "description": "Complete synthesisable Verilog source for fpga_top.v",
            },
            "testbench": {
                "type": "string",
                "description": "Complete SystemVerilog testbench for fpga_testbench.v",
            },
            "xdc_constraints": {
                "type": "string",
                "description": "Complete Vivado XDC file content",
            },
            "design_summary": {
                "type": "string",
                "description": "Human-readable design summary (resource estimate, key decisions)",
            },
            "lut_estimate": {"type": "integer", "description": "Estimated LUT count"},
            "ff_estimate":  {"type": "integer", "description": "Estimated flip-flop count"},
        },
        "required": [
            "module_name", "clock_frequency_mhz", "fpga_part",
            "ports", "verilog_top", "testbench", "xdc_constraints", "design_summary",
        ],
    },
}

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a senior FPGA/RTL design engineer with 20+ years experience in
synthesisable Verilog/VHDL for Xilinx devices (Artix-7, Kintex-7, UltraScale).

## YOUR TASK
Given a GLR (Glue Logic Requirements) specification and optional register map, generate:

### 1. Top-Level Verilog Module (`fpga_top.v`)
Requirements:
- Synthesisable Verilog-2001 / SystemVerilog for Xilinx Vivado
- Clock domain crossing handled with synchronisers (2-FF for control, FIFO for data)
- All FSMs: binary encoding with default state, one-hot optional with `(* fsm_encoding = "one_hot" *)`
- No latches — all `always` blocks must have complete sensitivity lists or be `always_ff`
- Reset: active-low synchronous reset (`rst_n`)
- Register access layer: 16-bit UART address/data bus matching the RDT address map (if provided)
- MISRA-equivalent rules: no implicit casts, explicit bit-widths, no unbounded loops
- Doxygen-style module header comment
- All outputs registered (no combinatorial outputs directly from `assign`)

### 2. Testbench (`fpga_testbench.v`)
- SystemVerilog testbench with `timescale 1ns/1ps`
- Clock generation task (50 MHz default — adjustable via parameter)
- Reset assertion + release sequence
- Cover all FSM transitions with `$display` pass/fail messages
- Register write/read verification over UART bus
- Final `$display("TESTBENCH: ALL TESTS PASSED")` on success

### 3. XDC Constraints (`constraints.xdc`)
- `create_clock` for the primary clock port
- `set_input_delay` / `set_output_delay` for all I/O (10 ns default)
- `set_false_path` for asynchronous resets and static config signals
- FPGA part: derive from GLR or use `xc7a35tcpg236-1` (Artix-7 35T) as default
- Pin assignments: use `set_property PACKAGE_PIN` for clk and rst_n at minimum

### 4. Design Report
- Table of ports with direction, width, and purpose
- FSM state diagram in Mermaid syntax
- Resource estimate: LUT count, FF count, BRAM, DSP
- Key design decisions and trade-offs

## CODING STANDARDS
- Indent: 4 spaces (no tabs)
- Line length: max 100 chars
- Parameter names: ALL_CAPS_WITH_UNDERSCORES
- Port names: snake_case
- Registers: `_r` suffix (e.g. `state_r`, `data_out_r`)
- Constants: `localparam` (not `define`)
- No `initial` blocks in synthesisable code (only in testbenches)
- Every `always` block must cover all states / conditions to avoid latches
- Minimum 25 ports, 2 FSMs, full register bus interface

## REGISTER BUS (if RDT available)
Implement a 16-bit UART register interface:
- `reg_addr[15:0]` — address (bit15=R/W#, bits11:8=base, bits7:0=offset)
- `reg_wdata[15:0]` — write data
- `reg_rdata[15:0]` — read data
- `reg_wr`, `reg_rd` — strobes
- Registers: at minimum CTRL, STATUS, VERSION, SCRATCH, IRQ_MASK, IRQ_STATUS

Use the `generate_fpga_design` tool to return all output files.
"""


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class FpgaAgent(BaseAgent):
    """Phase 7: AI-powered FPGA RTL design generation."""

    def __init__(self):
        super().__init__(
            phase_number="P7",
            phase_name="FPGA Design",
            model=settings.primary_model,
            tools=[GENERATE_FPGA_TOOL],
            max_tokens=16384,
        )

    def get_system_prompt(self, project_context: dict) -> str:
        return SYSTEM_PROMPT

    async def execute(self, project_context: dict, user_input: str) -> dict:
        output_dir = Path(project_context.get("output_dir", "output"))
        output_dir.mkdir(parents=True, exist_ok=True)
        project_name = project_context.get("name", "Project")
        safe_name = project_name.replace(" ", "_")

        # Load prior phase outputs
        glr_spec = self._load_file(output_dir / f"GLR_{safe_name}.md")
        glr_generic = self._load_file(output_dir / "glr_specification.md")
        rdt = self._load_file(output_dir / "register_description_table.md")
        psq = self._load_file(output_dir / "programming_sequence.md")
        netlist = self._load_file(output_dir / "netlist_visual.md")
        hrs = self._load_file(output_dir / f"HRS_{safe_name}.md")

        glr = glr_spec or glr_generic
        if not glr:
            logger.warning("P7: GLR spec not found — proceeding with netlist + requirements only")

        user_message = f"""Generate a complete FPGA RTL design for:

**Project:** {project_name}

---

### GLR Specification (P6 output):
{(glr or '(not available)')[:6000]}

---

### Register Description Table (P7a output):
{(rdt or '(not available)')[:3000]}

---

### Programming Sequence (P7a output):
{(psq or '(not available)')[:1500]}

---

### Netlist Summary (P4 output):
{(netlist or '(not available)')[:2000]}

---

### HRS Reference (P2 output):
{(hrs or '(not available)')[:1500]}

---

Use the `generate_fpga_design` tool to return:
1. Complete synthesisable Verilog top module (`fpga_top.v`)
2. SystemVerilog testbench (`fpga_testbench.v`)
3. Vivado XDC constraints file (`constraints.xdc`)
4. Design summary report

Map all registers from the RDT to the register bus. Implement all FSMs identified in the GLR.
"""

        messages = [{"role": "user", "content": user_message}]
        response = await self.safe_call_llm(
            messages=messages,
            system=self.get_system_prompt(project_context),
        )

        fpga_data = None

        if response.get("tool_calls"):
            for tc in response["tool_calls"]:
                if tc["name"] == "generate_fpga_design":
                    fpga_data = tc["input"]
                    break

        # Retry with explicit nudge if first call missed the tool — but only
        # when the first attempt actually reached a live provider. When the
        # chain is exhausted (`degraded=True`), a retry would just hit the
        # same 429 and waste another ~30 s; jump straight to the skeleton.
        if not fpga_data and not response.get("degraded"):
            logger.warning("P7: tool not called on first attempt — retrying")
            retry_response = await self.safe_call_llm(
                messages=messages + [
                    {"role": "assistant", "content": response.get("content", "")},
                    {"role": "user", "content": (
                        "You MUST call the `generate_fpga_design` tool now. "
                        "Return the complete Verilog, testbench, XDC, and report — "
                        "do NOT write prose, call the tool immediately."
                    )},
                ],
                system=self.get_system_prompt(project_context),
            )
            if retry_response.get("tool_calls"):
                for tc in retry_response["tool_calls"]:
                    if tc["name"] == "generate_fpga_design":
                        fpga_data = tc["input"]
                        response = retry_response
                        break

        outputs: Dict[str, str] = {}

        if fpga_data:
            # Write RTL files
            verilog_top = fpga_data.get("verilog_top", "")
            testbench   = fpga_data.get("testbench", "")
            xdc         = fpga_data.get("xdc_constraints", "")
            summary     = fpga_data.get("design_summary", "")

            rtl_dir = output_dir / "rtl"
            rtl_dir.mkdir(exist_ok=True)

            if verilog_top:
                (rtl_dir / "fpga_top.v").write_text(verilog_top, encoding="utf-8")
                outputs["rtl/fpga_top.v"] = verilog_top

            if testbench:
                (rtl_dir / "fpga_testbench.v").write_text(testbench, encoding="utf-8")
                outputs["rtl/fpga_testbench.v"] = testbench

            if xdc:
                (rtl_dir / "constraints.xdc").write_text(xdc, encoding="utf-8")
                outputs["rtl/constraints.xdc"] = xdc

            # Build design report
            report = self._build_design_report(fpga_data, project_name)
            report_path = output_dir / "fpga_design_report.md"
            report_path.write_text(report, encoding="utf-8")
            outputs["fpga_design_report.md"] = report

            self.log(
                f"P7 complete: {len(outputs)} files | "
                f"module={fpga_data.get('module_name','?')} | "
                f"clock={fpga_data.get('clock_frequency_mhz','?')} MHz | "
                f"~{fpga_data.get('lut_estimate','?')} LUTs"
            )
        else:
            # Skeleton fallback — pipeline must continue
            logger.warning("P7: generate_fpga_design tool not called after retry — using skeleton")
            skeleton = self._build_skeleton(project_name, safe_name, glr or "")
            for fname, content in skeleton.items():
                fpath = output_dir / fname
                fpath.parent.mkdir(parents=True, exist_ok=True)
                fpath.write_text(content, encoding="utf-8")
                outputs[fname] = content

        return {
            "response": response.get("content", "FPGA design generated."),
            "phase_complete": True,
            "outputs": outputs,
        }

    # ------------------------------------------------------------------ #
    # Report builder
    # ------------------------------------------------------------------ #

    def _build_design_report(self, data: dict, project_name: str) -> str:
        module_name = data.get("module_name", "fpga_top")
        clk_mhz     = data.get("clock_frequency_mhz", "?")
        fpga_part   = data.get("fpga_part", "xc7a35tcpg236-1")
        lut_est     = data.get("lut_estimate", "?")
        ff_est      = data.get("ff_estimate", "?")
        summary     = data.get("design_summary", "")
        ports       = data.get("ports", [])
        fsms        = data.get("state_machines", [])

        lines = [
            "# FPGA Design Report",
            f"## {project_name}",
            "",
            f"> **Module:** `{module_name}`  |  "
            f"**Target:** `{fpga_part}`  |  "
            f"**Clock:** {clk_mhz} MHz",
            "",
        ]

        if summary:
            lines += ["## Design Summary", "", summary, ""]

        # Resource estimate
        lines += [
            "---",
            "## Resource Estimate",
            "",
            "| Resource | Estimate |",
            "|----------|----------|",
            f"| LUTs | ~{lut_est} |",
            f"| Flip-Flops | ~{ff_est} |",
            "| BRAM | 0 (pure logic) |",
            "| DSPs | 0 |",
            "",
        ]

        # Port table
        if ports:
            lines += [
                "---",
                "## Port List",
                "",
                "| Port | Direction | Width | Description |",
                "|------|-----------|-------|-------------|",
            ]
            for p in ports:
                lines.append(
                    f"| `{p.get('name','')}` "
                    f"| {p.get('direction','')} "
                    f"| {p.get('width',1)} "
                    f"| {p.get('description','')} |"
                )
            lines.append("")

        # FSM diagrams (Mermaid)
        if fsms:
            lines += ["---", "## State Machines", ""]
            for fsm in fsms:
                lines += [
                    f"### {fsm.get('name', 'FSM')}",
                    "",
                    f"{fsm.get('description', '')}",
                    "",
                    "```mermaid",
                    "stateDiagram-v2",
                ]
                states = fsm.get("states", [])
                if states:
                    lines.append(f"    [*] --> {states[0]}")
                    for i in range(len(states) - 1):
                        lines.append(f"    {states[i]} --> {states[i+1]}")
                    lines.append(f"    {states[-1]} --> {states[0]}")
                lines += ["```", ""]

        # Generated files
        lines += [
            "---",
            "## Generated Files",
            "",
            "| File | Description |",
            "|------|-------------|",
            "| `rtl/fpga_top.v` | Synthesisable top-level Verilog module |",
            "| `rtl/fpga_testbench.v` | Self-checking SystemVerilog testbench |",
            "| `rtl/constraints.xdc` | Vivado XDC timing & I/O constraints |",
            "",
            "---",
            "## How to Synthesise (Vivado)",
            "",
            "```tcl",
            "# In Vivado Tcl console:",
            f"create_project {module_name} . -part {fpga_part}",
            "add_files rtl/fpga_top.v",
            "add_files -fileset constrs_1 rtl/constraints.xdc",
            "launch_runs synth_1",
            "wait_on_run synth_1",
            "launch_runs impl_1 -to_step write_bitstream",
            "wait_on_run impl_1",
            "```",
        ]

        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # Skeleton fallback
    # ------------------------------------------------------------------ #

    def _build_skeleton(self, project_name: str, safe_name: str, glr: str) -> Dict[str, str]:
        """Minimal skeleton RTL when the LLM does not call the tool."""
        module = re.sub(r"[^a-z0-9_]", "_", safe_name.lower())

        verilog = f"""\
// ============================================================
// Module  : {module}_top
// Project : {project_name}
// Source  : Hardware Pipeline v2 (skeleton fallback)
// NOTE    : Re-run Phase 7 for AI-generated RTL
// ============================================================
`timescale 1ns / 1ps

module {module}_top (
    input  wire        clk,       // System clock
    input  wire        rst_n,     // Active-low synchronous reset

    // Register bus (16-bit UART interface)
    input  wire [15:0] reg_addr,  // Address (bit15=R/W#)
    input  wire [15:0] reg_wdata, // Write data
    output reg  [15:0] reg_rdata, // Read data
    input  wire        reg_wr,    // Write strobe
    input  wire        reg_rd,    // Read strobe

    // Status
    output reg         busy,
    output reg         error_flag
);

    // ----------------------------------------------------------
    // Parameters
    // ----------------------------------------------------------
    localparam VERSION = 16'h0100;  // v1.0

    // ----------------------------------------------------------
    // Internal registers
    // ----------------------------------------------------------
    reg [15:0] ctrl_r;
    reg [15:0] status_r;
    reg [15:0] scratch_r;
    reg [15:0] irq_mask_r;
    reg [15:0] irq_status_r;

    // ----------------------------------------------------------
    // Register Write
    // ----------------------------------------------------------
    always @(posedge clk) begin
        if (!rst_n) begin
            ctrl_r      <= 16'h0000;
            scratch_r   <= 16'h0000;
            irq_mask_r  <= 16'hFFFF;
            irq_status_r<= 16'h0000;
        end else if (reg_wr) begin
            case (reg_addr[11:0])
                12'h000: ctrl_r       <= reg_wdata;
                12'h003: scratch_r    <= reg_wdata;
                12'hF00: irq_mask_r   <= reg_wdata;
                12'hF01: irq_status_r <= irq_status_r & ~reg_wdata; // W1C
                default: /* read-only */;
            endcase
        end
    end

    // ----------------------------------------------------------
    // Register Read
    // ----------------------------------------------------------
    always @(posedge clk) begin
        if (!rst_n) begin
            reg_rdata <= 16'h0000;
        end else if (reg_rd) begin
            case (reg_addr[11:0])
                12'h000: reg_rdata <= ctrl_r;
                12'h001: reg_rdata <= status_r;
                12'h002: reg_rdata <= VERSION;
                12'h003: reg_rdata <= scratch_r;
                12'hF00: reg_rdata <= irq_mask_r;
                12'hF01: reg_rdata <= irq_status_r;
                default: reg_rdata <= 16'hDEAD;
            endcase
        end
    end

    // ----------------------------------------------------------
    // Status / busy
    // ----------------------------------------------------------
    always @(posedge clk) begin
        if (!rst_n) begin
            busy       <= 1'b0;
            error_flag <= 1'b0;
            status_r   <= 16'h0000;
        end else begin
            busy       <= ctrl_r[0];
            error_flag <= 1'b0;
            status_r   <= {{14'b0, error_flag, busy}};
        end
    end

endmodule
"""

        testbench = f"""\
// ============================================================
// Testbench : {module}_top_tb
// Project   : {project_name}
// ============================================================
`timescale 1ns / 1ps

module {module}_top_tb;

    // DUT ports
    reg        clk        = 0;
    reg        rst_n      = 0;
    reg [15:0] reg_addr   = 0;
    reg [15:0] reg_wdata  = 0;
    wire[15:0] reg_rdata;
    reg        reg_wr     = 0;
    reg        reg_rd     = 0;
    wire       busy;
    wire       error_flag;

    // Instantiate DUT
    {module}_top dut (.*);

    // Clock 50 MHz
    always #10 clk = ~clk;

    // Tasks
    task write_reg;
        input [15:0] addr;
        input [15:0] data;
        begin
            @(posedge clk); reg_addr = addr; reg_wdata = data; reg_wr = 1;
            @(posedge clk); reg_wr = 0;
        end
    endtask

    task read_reg;
        input  [15:0] addr;
        output [15:0] data;
        begin
            @(posedge clk); reg_addr = {{1'b1, addr[14:0]}}; reg_rd = 1;
            @(posedge clk); data = reg_rdata; reg_rd = 0;
        end
    endtask

    reg [15:0] rd_data;
    integer pass_cnt = 0;
    integer fail_cnt = 0;

    initial begin
        $dumpfile("{module}_tb.vcd");
        $dumpvars(0, {module}_top_tb);

        // Reset
        rst_n = 0; repeat(5) @(posedge clk);
        rst_n = 1; repeat(2) @(posedge clk);

        // Test 1: Scratch register read-back
        write_reg(16'h0003, 16'hA5A5);
        read_reg(16'h0003, rd_data);
        if (rd_data === 16'hA5A5) begin
            $display("PASS: Scratch R/W 0xA5A5"); pass_cnt = pass_cnt + 1;
        end else begin
            $display("FAIL: Scratch R/W got %04X expected A5A5", rd_data); fail_cnt = fail_cnt + 1;
        end

        // Test 2: Version register read-only
        read_reg(16'h0002, rd_data);
        if (rd_data === 16'h0100) begin
            $display("PASS: VERSION = 0x0100"); pass_cnt = pass_cnt + 1;
        end else begin
            $display("FAIL: VERSION got %04X expected 0100", rd_data); fail_cnt = fail_cnt + 1;
        end

        repeat(5) @(posedge clk);

        if (fail_cnt == 0)
            $display("TESTBENCH: ALL TESTS PASSED (%0d tests)", pass_cnt);
        else
            $display("TESTBENCH: %0d FAILURES of %0d tests", fail_cnt, pass_cnt + fail_cnt);

        $finish;
    end

endmodule
"""

        xdc = f"""\
# ============================================================
# Constraints : {project_name}
# Target      : xc7a35tcpg236-1 (Artix-7)
# Tool        : Vivado 2023.x
# NOTE        : Re-run Phase 7 for full pin assignments
# ============================================================

# Primary clock (100 MHz — adjust to your board)
create_clock -period 10.000 -name clk [get_ports clk]

# Input / output delays (10 ns default — refine after STA)
set_input_delay  -clock clk -max 4.0 [get_ports {{reg_addr reg_wdata reg_wr reg_rd}}]
set_input_delay  -clock clk -min 0.5 [get_ports {{reg_addr reg_wdata reg_wr reg_rd}}]
set_output_delay -clock clk -max 4.0 [get_ports {{reg_rdata busy error_flag}}]
set_output_delay -clock clk -min 0.5 [get_ports {{reg_rdata busy error_flag}}]

# False path on async reset
set_false_path -from [get_ports rst_n]

# Pin assignments (example Artix-7 — update for your board)
set_property PACKAGE_PIN W5  [get_ports clk]
set_property IOSTANDARD  LVCMOS33 [get_ports clk]

set_property PACKAGE_PIN V17 [get_ports rst_n]
set_property IOSTANDARD  LVCMOS33 [get_ports rst_n]
"""

        report = (
            f"# FPGA Design Report\n## {project_name}\n\n"
            f"> **Note:** This is a skeleton generated because the AI did not call the "
            f"structured tool. **Re-run Phase 7** for full AI-generated RTL with all FSMs "
            f"and registers from the GLR specification.\n\n"
            f"## Generated Files\n\n"
            f"| File | Description |\n|------|-------------|\n"
            f"| `rtl/fpga_top.v` | Skeleton top module with register bus |\n"
            f"| `rtl/fpga_testbench.v` | Basic R/W testbench |\n"
            f"| `rtl/constraints.xdc` | Skeleton XDC constraints |\n"
        )

        return {
            "rtl/fpga_top.v": verilog,
            "rtl/fpga_testbench.v": testbench,
            "rtl/constraints.xdc": xdc,
            "fpga_design_report.md": report,
        }

    # ------------------------------------------------------------------ #
    # Helper
    # ------------------------------------------------------------------ #

    def _load_file(self, path: Path) -> str:
        if path.exists():
            try:
                return path.read_text(encoding="utf-8")
            except Exception:
                pass
        return ""
