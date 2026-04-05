"""
Phase 7a: Register Description Table (RDT) + Programming Sequence (PSQ) Agent.

Automates the previously-manual parts of Phase 7 (FPGA Design):
  - Generates the Register Description Table (RDT) from GLR/netlist specs
  - Generates the Programming Sequence (PSQ) for device initialisation
  - Outputs structured Markdown documents ready for firmware / RTL use

Configuration: uses the same LLM settings as other agents.
"""

import logging
from pathlib import Path
from typing import Dict

from agents.base_agent import BaseAgent
from config import settings

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are an expert FPGA/embedded-systems engineer specialising in register map design and firmware programming sequences for defense/industrial electronics.

## YOUR TASK
Given a GLR (Glue Logic Requirements) specification and netlist information, generate:

### 1. Register Description Table (RDT)
A comprehensive, deeply detailed table of EVERY memory-mapped register in the design. Minimum 20 registers.

## REGISTER ADDRESS SCHEME (16-bit UART address):
```
Bit 15    : R/W# (1=Read, 0=Write)
Bit 14    : 0 (reserved)
Bits 13:12: RESERVED
Bits 11:8 : BASE_ADDRESS [3:0]  — selects functional group
Bits 7:0  : OFFSET [7:0]        — register offset within group
```

### BASE ADDRESS GROUPS (derive from GLR / project type):
| BASE[3:0] | Hex Offset | Functional Group |
|-----------|-----------|-----------------|
| 0000 | 0x000 | Board Information Registers |
| 0001 | 0x100 | Communication & Interface Registers |
| 0010 | 0x200 | ADC / Sensor Monitoring Registers |
| 0011 | 0x300 | Temperature & Health Registers |
| 0100 | 0x400 | PLL / Clock Configuration Registers |
| 0101 | 0x500 | EEPROM / NV Storage Registers |
| 0110 | 0x600 | Flash Interface Registers |
| 0111 | 0x700 | RF / Phase Control Registers |
| 1000 | 0x800 | GPIO / Control Registers |
| 1001 | 0x900 | DAC / Output Registers |

### REQUIRED REGISTER GROUPS — include ALL of these:

**Group 0x000 — Board Information:**
- BOARD_ID (0x0000): Board identification code [15:0] RO
- BOARD_VERSION (0x0001): Hardware version [7:4]=major, [3:0]=minor RO
- BOARD_TYPE_ID (0x0002): Board type identifier [15:0] RO
- SCRATCHPAD (0x0003): Read/write test register [15:0] RW, reset=0x0000
- MCS_VERSION_MAJOR (0x0010): FPGA firmware major version [7:0] RO
- MCS_VERSION_MINOR (0x0011): FPGA firmware minor version [7:0] RO
- BUILD_DATE (0x0012): Build date (YYYYMMDD packed BCD) [15:0] RO

**Group 0x100 — Communication:**
- UART_BAUD_DIV (0x0100): Baud rate divisor [15:0] RW
- UART_CTRL (0x0101): UART control [0]=enable, [1]=loopback, [7:4]=frame-format RW
- UART_STATUS (0x0102): UART status [0]=TX_BUSY, [1]=RX_AVAIL, [2]=FRAME_ERR RC
- UART_TX_COUNT (0x0103): TX FIFO byte count [7:0] RO
- UART_RX_COUNT (0x0104): RX FIFO byte count [7:0] RO
- ETH_MAC_LOW (0x0110): Ethernet MAC address [15:0] RO
- ETH_MAC_HIGH (0x0111): Ethernet MAC address [31:16] RO

**Group 0x200 — ADC / Supply Monitoring:**
- ADC_CTRL (0x0200): ADC control [0]=start, [1]=continuous, [3:2]=channel-select RW
- ADC_STATUS (0x0201): [0]=DATA_READY, [1]=OVERRANGE RC
- VCC_5V_RAW (0x0210): 5V rail ADC count [11:0] RO — multiply by 5.0/4096 for Volts
- VCC_3V3_RAW (0x0211): 3.3V rail ADC count [11:0] RO
- VCC_2V5_RAW (0x0212): 2.5V rail ADC count [11:0] RO
- VCC_1V8_RAW (0x0213): 1.8V rail ADC count [11:0] RO
- ICC_5V_RAW (0x0218): 5V rail current ADC count [11:0] RO
- ICC_3V3_RAW (0x0219): 3.3V rail current ADC count [11:0] RO

**Group 0x300 — Temperature & Health:**
- TEMP_LOCAL (0x0300): Local FPGA die temperature in 0.25°C units [9:0] RO (signed)
- TEMP_REMOTE1 (0x0301): Remote sensor 1 temperature [9:0] RO
- TEMP_REMOTE2 (0x0302): Remote sensor 2 temperature [9:0] RO
- TEMP_ALERT_HIGH (0x0308): Over-temperature alert threshold [9:0] RW reset=0x0190 (100°C)
- TEMP_ALERT_LOW (0x0309): Under-temperature alert threshold [9:0] RW reset=0xFF9C (-25°C)
- HEALTH_STATUS (0x030F): System health [0]=TEMP_OK, [1]=VOLT_OK, [2]=PLL_LOCK, [7]=SYSTEM_OK RO

**Group 0x400 — PLL / Clock:**
- PLL_CTRL (0x0400): PLL control [0]=ENABLE, [1]=RESET, [3:2]=REF_SEL RW
- PLL_STATUS (0x0401): [0]=LOCKED, [1]=LOSS_OF_LOCK RC
- PLL_N_DIV (0x0402): N divider [15:0] RW
- PLL_R_DIV (0x0403): R divider [7:0] RW
- CLK_ENABLE (0x0410): Clock output enables [7:0] RW — one bit per output

**Group 0x500 — EEPROM:**
- EEPROM_CTRL (0x0500): [0]=READ, [1]=WRITE, [2]=ERASE, [7]=BUSY RW/RO
- EEPROM_ADDR (0x0501): EEPROM byte address [15:0] RW
- EEPROM_DATA (0x0502): Read/write data [15:0] RW

**Group 0x600 — Configuration Flash:**
- FLASH_CTRL (0x0600): [0]=READ, [1]=WRITE, [2]=ERASE_SECTOR, [3]=ERASE_CHIP, [7]=BUSY RW/RO
- FLASH_ADDR_LOW (0x0601): Flash address [15:0] RW
- FLASH_ADDR_HIGH (0x0602): Flash address [23:16] RW
- FLASH_DATA (0x0603): Read/write data FIFO [15:0] RW
- FLASH_STATUS (0x0604): [0]=READY, [1]=WRITE_ERR, [2]=ERASE_ERR RC

Add MORE registers from GLR/netlist (RF control, DAC, GPIO, application-specific).

### 2. Programming Sequence (PSQ)
A detailed, ordered initialisation sequence. Minimum 15 steps covering:

**PHASE 1 — Power-On Reset & Self-Check (Steps 1-4)**
**PHASE 2 — PLL & Clock Init (Steps 5-7)**
**PHASE 3 — Peripheral Enable (Steps 8-10)**
**PHASE 4 — Communication Init (Steps 11-12)**
**PHASE 5 — Application Init (Steps 13-15+)**

For EACH step:
- Read SCRATCHPAD register, write known value, read back to verify (RAM check)
- Poll HEALTH_STATUS until VOLT_OK=1 (power rails stable)
- Read BOARD_ID, verify against expected value
- Configure PLL N/R dividers, enable PLL, poll until LOCKED
- Enable required clock outputs
- Configure UART baud rate
- Arm temperature alerts
- Initialize Flash interface, verify flash ID
- Initialize EEPROM, read calibration data
- Enable application-specific peripherals

## UART FRAME FORMATS (document in _build_rdt_md):

**Single Register Write (3 bytes + command byte):**
```
[CMD=0x57 'W'] [ADDR_MSB] [ADDR_LSB] [DATA_MSB] [DATA_LSB]
```
Where ADDR bit15=0 (Write), bits11:8=BASE, bits7:0=OFFSET

**Single Register Read (command + 2 addr bytes, response 2 data bytes):**
```
TX: [CMD=0x52 'R'] [ADDR_MSB|0x80] [ADDR_LSB]
RX: [DATA_MSB] [DATA_LSB]
```

**Bulk Write (N registers):**
```
TX: [CMD=0x42 'B'] [START_ADDR_MSB] [START_ADDR_LSB] [NUM_REGS] [D0_MSB] [D0_LSB] ... [DN_MSB] [DN_LSB]
```

**Bulk Read (N consecutive registers):**
```
TX: [CMD=0x62 'b'] [START_ADDR_MSB|0x80] [START_ADDR_LSB] [NUM_REGS]
RX: [D0_MSB] [D0_LSB] ... [DN_MSB] [DN_LSB]
```

## OUTPUT FORMAT
Use the `generate_rdt_psq` tool to return structured data.
The `_build_rdt_md` method will also append the UART frame format tables automatically.

## GUIDELINES
- Use 0x-prefixed hex for ALL addresses and values
- Access types: R (read-only), W (write-only), RW (read-write), RC (read-clears on read)
- Reset values must be concrete hex values — never TBD/TBC/TBA
- Programming sequence must be in correct hardware dependency order
- Flag registers requiring special write sequences (e.g. unlock key before erase)
- Include ALL registers visible in the provided GLR/netlist — add project-specific registers beyond the required set
- Minimum 20 registers total, minimum 15 PSQ steps
"""

GENERATE_RDT_PSQ_TOOL = {
    "name": "generate_rdt_psq",
    "description": "Generate structured Register Description Table and Programming Sequence.",
    "input_schema": {
        "type": "object",
        "properties": {
            "registers": {
                "type": "array",
                "description": "List of memory-mapped registers",
                "items": {
                    "type": "object",
                    "properties": {
                        "name":         {"type": "string", "description": "Register name (e.g. CTRL_REG)"},
                        "address":      {"type": "string", "description": "Hex address (e.g. 0x0000)"},
                        "reset_value":  {"type": "string", "description": "Reset value (e.g. 0x00)"},
                        "description":  {"type": "string", "description": "Register purpose"},
                        "fields": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name":        {"type": "string"},
                                    "bits":        {"type": "string", "description": "e.g. [7:4]"},
                                    "access":      {"type": "string", "description": "RW / R / W / RC"},
                                    "reset":       {"type": "string", "description": "Reset value for this field"},
                                    "description": {"type": "string"},
                                },
                                "required": ["name", "bits", "access", "description"],
                            },
                        },
                    },
                    "required": ["name", "address", "description", "fields"],
                },
            },
            "programming_sequence": {
                "type": "array",
                "description": "Ordered list of initialisation steps",
                "items": {
                    "type": "object",
                    "properties": {
                        "step":          {"type": "integer"},
                        "phase":         {"type": "string", "description": "Phase label (e.g. Clock Init)"},
                        "register":      {"type": "string", "description": "Register name"},
                        "address":       {"type": "string", "description": "Hex address"},
                        "value":         {"type": "string", "description": "Hex value to write"},
                        "condition":     {"type": "string", "description": "Wait/poll condition (optional)"},
                        "rationale":     {"type": "string", "description": "Why this step is needed"},
                    },
                    "required": ["step", "phase", "register", "address", "value", "rationale"],
                },
            },
            "summary": {
                "type": "string",
                "description": "Short summary of the register map and sequence",
            },
        },
        "required": ["registers", "programming_sequence"],
    },
}


class RdtPsqAgent(BaseAgent):
    """Phase 7a: Register Description Table + Programming Sequence generation."""

    def __init__(self):
        super().__init__(
            phase_number="P7a",
            phase_name="Register Map & Programming Sequence",
            model=settings.primary_model,
            tools=[GENERATE_RDT_PSQ_TOOL],
            max_tokens=16384,  # Increased for comprehensive RDT/PSQ reports
        )

    def get_system_prompt(self, project_context: dict) -> str:
        return SYSTEM_PROMPT

    async def execute(self, project_context: dict, user_input: str) -> dict:
        output_dir = Path(project_context.get("output_dir", "output"))
        output_dir.mkdir(parents=True, exist_ok=True)
        project_name = project_context.get("name", "Project")

        # Load prior phase outputs
        glr_spec   = self._load_file(output_dir / f"GLR_{project_name.replace(' ', '_')}.md")
        netlist    = self._load_file(output_dir / "netlist_visual.md")
        hrs        = self._load_file(output_dir / f"HRS_{project_name.replace(' ', '_')}.md")

        if not glr_spec:
            self.log("GLR spec not found — using requirements and netlist only")

        user_message = f"""Generate a complete Register Description Table (RDT) and
Programming Sequence (PSQ) for:

**Project:** {project_name}

### GLR Specification:
{glr_spec[:5000] if glr_spec else '(not yet generated — infer from requirements)'}

### Netlist Summary:
{netlist[:3000] if netlist else '(not available)'}

### HRS Reference:
{hrs[:2000] if hrs else '(not available)'}

Use the `generate_rdt_psq` tool to return structured register data and initialisation steps.
Include all memory-mapped registers visible in the GLR / netlist.
"""

        messages = [{"role": "user", "content": user_message}]
        response = await self.call_llm(
            messages=messages,
            system=self.get_system_prompt(project_context),
        )

        outputs: Dict[str, str] = {}
        rdt_psq_data = None

        if response.get("tool_calls"):
            for tc in response["tool_calls"]:
                if tc["name"] == "generate_rdt_psq":
                    rdt_psq_data = tc["input"]
                    break

        # Retry once with an explicit tool-use nudge if the first call missed the tool
        if not rdt_psq_data:
            logger.warning("P7a: tool not called on first attempt — retrying with explicit prompt")
            messages = messages + [
                {"role": "assistant", "content": response.get("content", "")},
                {"role": "user", "content": (
                    "You must call the `generate_rdt_psq` tool now to return the structured "
                    "register map and programming sequence. Do not write prose — call the tool."
                )},
            ]
            retry_response = await self.call_llm(
                messages=messages,
                system=self.get_system_prompt(project_context),
            )
            if retry_response.get("tool_calls"):
                for tc in retry_response["tool_calls"]:
                    if tc["name"] == "generate_rdt_psq":
                        rdt_psq_data = tc["input"]
                        response = retry_response
                        break

        if rdt_psq_data:
            outputs["register_description_table.md"] = self._build_rdt_md(
                rdt_psq_data, project_name
            )
            outputs["programming_sequence.md"] = self._build_psq_md(
                rdt_psq_data, project_name
            )
            self.log(
                f"RDT: {len(rdt_psq_data.get('registers', []))} registers, "
                f"PSQ: {len(rdt_psq_data.get('programming_sequence', []))} steps"
            )
        else:
            logger.warning("P7a: generate_rdt_psq tool not called after retry — using text fallback")
            llm_text = response.get("content", "")
            outputs["register_description_table.md"] = (
                f"# Register Description Table — {project_name}\n\n"
                f"{llm_text}\n\n"
                "_Note: Structured tool output was unavailable. Re-run Phase 7a for full table._\n"
            )
            outputs["programming_sequence.md"] = (
                f"# Programming Sequence — {project_name}\n\n"
                "_Structured programming sequence could not be generated in this run._\n\n"
                "Re-run Phase 7a to generate the complete initialisation sequence.\n"
            )

        return {
            "response": response.get("content", "RDT & PSQ generated."),
            "phase_complete": True,  # files always written; pipeline should continue
            "outputs": outputs,
        }

    # ------------------------------------------------------------------ #
    # Markdown builders
    # ------------------------------------------------------------------ #

    def _build_rdt_md(self, data: dict, project_name: str) -> str:
        lines = [
            "# Register Description Table (RDT)",
            f"## {project_name}",
            "",
            f"> **Total registers:** {len(data.get('registers', []))}",
            "",
        ]
        if data.get("summary"):
            lines += [data["summary"], ""]

        # --- Register Address Scheme ---
        lines += [
            "---",
            "## Register Address Decoding",
            "",
            "The 16-bit UART register address is decoded as follows:",
            "",
            "| Bit(s) | Field | Description |",
            "|--------|-------|-------------|",
            "| [15] | R/W# | 1 = Read operation, 0 = Write operation |",
            "| [14] | Reserved | Must be 0 |",
            "| [13:12] | Reserved | Must be 0 |",
            "| [11:8] | BASE_ADDR[3:0] | Functional group selector |",
            "| [7:0] | OFFSET[7:0] | Register offset within group |",
            "",
            "### Base Address Map",
            "",
            "| BASE[3:0] | Address Range | Functional Group |",
            "|-----------|--------------|-----------------|",
            "| 0x0 | 0x0000–0x00FF | Board Information |",
            "| 0x1 | 0x0100–0x01FF | Communication & Interface |",
            "| 0x2 | 0x0200–0x02FF | ADC / Supply Monitoring |",
            "| 0x3 | 0x0300–0x03FF | Temperature & Health |",
            "| 0x4 | 0x0400–0x04FF | PLL / Clock Configuration |",
            "| 0x5 | 0x0500–0x05FF | EEPROM / NV Storage |",
            "| 0x6 | 0x0600–0x06FF | Configuration Flash |",
            "| 0x7 | 0x0700–0x07FF | RF / Phase Control |",
            "| 0x8 | 0x0800–0x08FF | GPIO / Control |",
            "| 0x9 | 0x0900–0x09FF | DAC / Output |",
            "",
        ]

        # --- UART Frame Formats ---
        lines += [
            "---",
            "## UART Frame Formats",
            "",
            "### Single Register Write",
            "```",
            "TX: [0x57 'W'] [ADDR_MSB (bit15=0)] [ADDR_LSB] [DATA_MSB] [DATA_LSB]",
            "RX: [ACK=0x06] or [NAK=0x15]",
            "```",
            "",
            "### Single Register Read",
            "```",
            "TX: [0x52 'R'] [ADDR_MSB (bit15=1)] [ADDR_LSB]",
            "RX: [DATA_MSB] [DATA_LSB]",
            "```",
            "",
            "### Bulk Write (N consecutive registers)",
            "```",
            "TX: [0x42 'B'] [START_ADDR_MSB] [START_ADDR_LSB] [NUM_REGS (1 byte)]",
            "    [D0_MSB] [D0_LSB] ... [DN-1_MSB] [DN-1_LSB]",
            "RX: [ACK=0x06]",
            "```",
            "",
            "### Bulk Read (N consecutive registers)",
            "```",
            "TX: [0x62 'b'] [START_ADDR_MSB|0x80] [START_ADDR_LSB] [NUM_REGS]",
            "RX: [D0_MSB] [D0_LSB] ... [DN-1_MSB] [DN-1_LSB]",
            "```",
            "",
        ]

        # --- Register detail sections ---
        lines += ["---", "## Register Definitions", ""]

        # Group registers by base address
        regs = data.get("registers", [])
        lines.append(
            "| Address | Register Name | Access | Reset | Description |"
        )
        lines.append("|---------|--------------|--------|-------|-------------|")
        for reg in regs:
            lines.append(
                f"| `{reg.get('address','0x????')}` "
                f"| `{reg.get('name','REG')}` "
                f"| — "
                f"| `{reg.get('reset_value','0x0000')}` "
                f"| {reg.get('description','')} |"
            )
        lines.append("")

        for reg in regs:
            lines += [
                "---",
                f"### `{reg.get('name', 'REG')}` — Address `{reg.get('address', '0x??')}`",
                "",
                f"**Reset value:** `{reg.get('reset_value', '0x0000')}`  "
                f"**Access:** see fields below",
                "",
                reg.get("description", ""),
                "",
                "| Field | Bits | Access | Reset | Description |",
                "|-------|------|--------|-------|-------------|",
            ]
            for f in reg.get("fields", []):
                lines.append(
                    f"| `{f.get('name','')}` | `{f.get('bits','')}` "
                    f"| {f.get('access','')} | `{f.get('reset','0x0')}` "
                    f"| {f.get('description','')} |"
                )
            lines.append("")

        return "\n".join(lines)

    def _build_psq_md(self, data: dict, project_name: str) -> str:
        steps = data.get("programming_sequence", [])
        lines = [
            "# Programming Sequence (PSQ)",
            f"## {project_name}",
            "",
            f"> **Total steps:** {len(steps)}",
            "",
            "| # | Phase | Register | Address | Value | Condition | Rationale |",
            "|---|-------|----------|---------|-------|-----------|-----------|",
        ]

        for s in steps:
            cond = s.get("condition", "—") or "—"
            lines.append(
                f"| {s.get('step','')} | {s.get('phase','')} "
                f"| `{s.get('register','')}` | `{s.get('address','')}` "
                f"| `{s.get('value','')}` | {cond} "
                f"| {s.get('rationale','')} |"
            )

        lines += [
            "",
            "---",
            "",
            "## Detailed Steps",
            "",
        ]
        for s in steps:
            lines += [
                f"### Step {s.get('step','')} — {s.get('phase','')}",
                f"- **Register:** `{s.get('register','')}` at `{s.get('address','')}`",
                f"- **Write value:** `{s.get('value','')}`",
            ]
            if s.get("condition"):
                lines.append(f"- **Wait/Poll:** {s['condition']}")
            lines += [
                f"- **Rationale:** {s.get('rationale','')}",
                "",
            ]

        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # File loader
    # ------------------------------------------------------------------ #

    def _load_file(self, path: Path) -> str:
        if path.exists():
            try:
                return path.read_text(encoding="utf-8")
            except Exception:
                pass
        return ""
