import { PhaseMeta } from '../types';

export const PHASES: PhaseMeta[] = [
  {
    id: 'P1', code: 'P01', num: 1,
    name: 'Requirements & Component Selection',
    tagline: 'Natural language → verified BOM',
    color: '#00c6a7', auto: true, manual: false, time: '~4 min',
    subSteps: [
      { label: 'Parse natural language input', time: '12s', detail: 'Claude extracts domain, voltage, current, form-factor from free text' },
      { label: 'Identify hardware domain', time: '5s', detail: 'Classify: RF / Motor / Power / Digital / Mixed-signal' },
      { label: 'Query component database', time: '48s', detail: 'Search 500K+ parts across DigiKey, Mouser, Arrow APIs' },
      { label: 'Rank & select components', time: '20s', detail: 'Score by: availability, lifecycle, cost, specs match, RoHS' },
      { label: 'Generate BOM with alternates', time: '15s', detail: '2-3 alternatives per critical component, footprint verified' },
      { label: 'Block diagram verification', time: '30s', detail: 'ASCII block diagram generated, engineer confirms connectivity' },
      { label: 'Requirement finalization loop', time: '50s', detail: 'AI asks clarifying questions, engineer approves final spec' },
    ],
    metrics: { timeSaved: '2 weeks → 4 min', errorReduction: '72%', confidence: '94%', costImpact: 'Rs 8.2L/yr' },
    inputs: ['Engineer natural language description', 'Design type (RF / Digital)', 'Voltage / current requirements'],
    outputs: ['Requirements document (.md)', 'Block diagram (.md)', 'Architecture overview (.md)', 'Component recommendations BOM (.md)'],
    tools: ['Claude AI', 'Component search (ChromaDB, optional)'],
  },
  {
    id: 'P2', code: 'P02', num: 2,
    name: 'HRS Document Generation',
    tagline: '50-100 page specification in minutes',
    color: '#3b82f6', auto: true, manual: false, time: '~4 min',
    subSteps: [
      { label: 'Load requirements from P1', time: '3s', detail: 'Structured JSON requirements parsed from phase 1 output' },
      { label: 'Select domain template', time: '5s', detail: 'Motor / RF / Power / Digital template loaded with section schema' },
      { label: 'Calculate power budget', time: '18s', detail: 'PySpice simulation: efficiency curves, thermal derating, margins' },
      { label: 'Generate interface tables', time: '22s', detail: 'All connectors, signals, pin assignments auto-populated' },
      { label: 'Write specification sections', time: '120s', detail: 'Claude writes each section: overview, electrical, mechanical, thermal' },
      { label: 'Insert Graphviz diagrams', time: '30s', detail: 'Block diagrams, power tree, interface diagrams auto-generated' },
      { label: 'Export .docx / .pdf', time: '12s', detail: 'python-docx + ReportLab render final document with TOC' },
    ],
    metrics: { timeSaved: '3 weeks → 4 min', errorReduction: '68%', confidence: '91%', costImpact: 'Rs 11.4L/yr' },
    inputs: ['Requirements from P1', 'Block diagram from P1', 'Architecture from P1', 'BOM from P1'],
    outputs: ['HRS document (.md)', 'HRS document (.docx)'],
    tools: ['Claude AI', 'python-docx'],
  },
  {
    id: 'P3', code: 'P03', num: 3,
    name: 'Compliance Validation',
    tagline: 'Multi-standard real-time checking',
    color: '#f59e0b', auto: true, manual: false, time: '~4 min',
    subSteps: [
      { label: 'Load HRS + BOM from P1/P2', time: '4s', detail: 'Component list and spec parameters extracted for validation' },
      { label: 'RoHS / REACH substance check', time: '35s', detail: 'Each component checked against restricted substance database' },
      { label: 'EMC pre-compliance check', time: '45s', detail: 'IEC 61000 series: conducted/radiated emissions estimated' },
      { label: 'Safety standard mapping', time: '30s', detail: 'ISO 26262, IEC 61508, MIL-STD-461 rules applied per domain' },
      { label: 'Generate compliance matrix', time: '20s', detail: 'PASS / WARN / FAIL per standard with evidence links' },
      { label: 'Generate CycloneDX SBOM', time: '8s', detail: 'CycloneDX 1.4 JSON SBOM with component PURLs — importable into Dependency-Track' },
      { label: 'Compliance report export', time: '10s', detail: 'Full report + SBOM exported; certificate readiness score included' },
    ],
    metrics: { timeSaved: '1 week → 4 min', errorReduction: '91%', confidence: '97%', costImpact: 'Rs 6.8L/yr' },
    inputs: ['BOM / component recommendations from P1', 'Requirements from P1', 'Design type'],
    outputs: ['Compliance report (.md)', 'CycloneDX SBOM (.json)', 'SBOM summary (.md)'],
    tools: ['Claude AI', 'RoHS/REACH rules (built-in)', 'cyclonedx-bom'],
  },
  {
    id: 'P4', code: 'P04', num: 4,
    name: 'Logical Netlist Generation',
    tagline: 'Pre-PCB netlists — the paradigm shift',
    color: '#8b5cf6', auto: true, manual: false, time: '~4 min',
    subSteps: [
      { label: 'Parse block diagram from P1', time: '8s', detail: 'ASCII / text block diagram converted to graph model (NetworkX)' },
      { label: 'Map components to pinouts', time: '22s', detail: 'Each block resolved to actual component pins from datasheets' },
      { label: 'Build connectivity graph', time: '30s', detail: 'Net connections derived from interface definitions in HRS' },
      { label: 'Assign net classes', time: '15s', detail: 'Power, ground, differential pairs, high-speed nets classified' },
      { label: 'Run electrical rules check', time: '35s', detail: 'SymPy validates: no floating pins, correct power domains, no shorts' },
      { label: 'Export KiCad netlist (.net)', time: '8s', detail: 'Standard netlist format compatible with all major EDA tools' },
      { label: 'Pre-PCB DRC report', time: '10s', detail: 'Design rule pre-check: clearances, current capacity, impedance' },
    ],
    metrics: { timeSaved: 'Eliminates post-layout rework', errorReduction: '85%', confidence: '89%', costImpact: 'Rs 9.1L/yr' },
    inputs: ['Requirements from P1', 'BOM from P1', 'HRS from P2'],
    outputs: ['Netlist JSON (.json)', 'Netlist visual (.md)', 'Netlist validation report (.json)'],
    tools: ['Claude AI', 'NetworkX (graph validation)'],
  },
  {
    id: 'P5', code: 'P05', num: 5,
    name: 'PCB Layout',
    tagline: 'Engineer-driven EDA tool',
    color: '#475569', auto: false, manual: true, time: 'Days-Weeks',
    externalTool: 'Altium Designer / KiCad / OrCAD',
    subSteps: [
      { label: 'Import validated netlist (P4)', time: '5 min', detail: 'Zero connectivity ambiguity — netlist pre-validated by AI' },
      { label: 'Define layer stackup', time: '2 hrs', detail: '6-layer: signal, ground, power, signal, ground, signal' },
      { label: 'Component placement', time: '1-2 days', detail: 'Manual placement following mechanical constraints' },
      { label: 'Route critical signals', time: '2-3 days', detail: 'Differential pairs, high-speed, RF traces routed manually' },
      { label: 'DRC / ERC check', time: '2 hrs', detail: 'Design rule check in EDA tool, resolve all violations' },
      { label: 'Gerber export', time: '30 min', detail: 'Manufacturing files: Gerber, drill, BOM, assembly drawing' },
    ],
    metrics: { timeSaved: 'N/A (manual)', errorReduction: '85% fewer netlist errors', confidence: 'N/A', costImpact: 'Reduced re-spins' },
    inputs: ['KiCad netlist from P4', 'Mechanical constraints', 'PCB stackup spec'],
    outputs: ['PCB layout file', 'Gerber files', 'Assembly drawing', 'Drill file'],
    tools: ['Altium Designer', 'KiCad', 'OrCAD'],
  },
  {
    id: 'P6', code: 'P06', num: 6,
    name: 'GLR Specification',
    tagline: 'Glue logic requirements for FPGA/CPLD',
    color: '#00c6a7', auto: true, manual: false, time: '~4 min',
    subSteps: [
      { label: 'Load netlist from P4', time: '5s', detail: 'Connectivity graph parsed, FPGA/CPLD nodes identified' },
      { label: 'Identify FPGA/CPLD boundaries', time: '20s', detail: 'Logic cells, I/O banks, clock domains mapped' },
      { label: 'Map glue logic requirements', time: '35s', detail: 'Level shifting, bus arbitration, state machine specs derived' },
      { label: 'Generate RTL constraints', time: '40s', detail: 'Timing constraints, I/O standards, pin assignments generated' },
      { label: 'Write GLR document', time: '80s', detail: 'Full specification with truth tables, state diagrams, timing' },
      { label: 'Export specification', time: '10s', detail: 'GLR document exported as .md and .docx' },
    ],
    metrics: { timeSaved: '1 week → 4 min', errorReduction: '78%', confidence: '88%', costImpact: 'Rs 5.2L/yr' },
    inputs: ['Requirements from P1', 'Netlist JSON from P4'],
    outputs: ['GLR specification (.md)'],
    tools: ['Claude AI'],
  },
  {
    id: 'P7', code: 'P07', num: 7,
    name: 'FPGA Design',
    tagline: 'Vivado / Quartus — manual implementation',
    color: '#475569', auto: false, manual: true, time: 'Days-Weeks',
    externalTool: 'Vivado / Quartus',
    subSteps: [
      { label: 'Import GLR specification', time: '30 min', detail: 'RTL constraints and pin assignments imported into EDA tool' },
      { label: 'RTL coding (VHDL/Verilog)', time: '2-5 days', detail: 'Engineer writes HDL following GLR specification' },
      { label: 'Simulation & verification', time: '1-2 days', detail: 'Testbenches validate all logic paths and edge cases' },
      { label: 'Synthesis & place-and-route', time: '4 hrs', detail: 'EDA tool synthesizes and maps to FPGA fabric' },
      { label: 'Timing closure', time: '2-4 hrs', detail: 'All timing constraints met, critical paths resolved' },
      { label: 'Bitstream generation', time: '1 hr', detail: 'Final bitstream and programming file generated' },
    ],
    metrics: { timeSaved: 'N/A (manual)', errorReduction: '80% fewer spec errors', confidence: 'N/A', costImpact: 'Reduced redesigns' },
    inputs: ['GLR specification from P6', 'Register map from P7a', 'Pin assignment table', 'FPGA dev board / target'],
    outputs: ['HDL source files', 'Simulation results', 'Bitstream (.bit)', 'Programming file'],
    tools: ['Vivado', 'Quartus', 'ModelSim'],
  },
  {
    id: 'P7a', code: 'P07a', num: 7,
    name: 'Register Map & Programming Sequence',
    tagline: 'AI-generated RDT + PSQ from GLR spec',
    color: '#f59e0b', auto: true, manual: false, time: '~2 min',
    subSteps: [
      { label: 'Load GLR specification from P6', time: '5s', detail: 'GLR document parsed, FPGA register interfaces identified' },
      { label: 'Identify memory-mapped registers', time: '20s', detail: 'All registers extracted: address, width, access type, reset value' },
      { label: 'Generate Register Description Table', time: '60s', detail: 'Full RDT with bit-field breakdown: name, bits, access (R/W/RO/RC), description' },
      { label: 'Define Programming Sequence', time: '45s', detail: 'Ordered init steps: power-on → clock → peripherals, with rationale per step' },
      { label: 'Validate sequence dependencies', time: '15s', detail: 'Dependency order checked: unlock sequences, self-clearing bits, poll conditions' },
      { label: 'Export RDT + PSQ documents', time: '10s', detail: 'register_description_table.md + programming_sequence.md exported' },
    ],
    metrics: { timeSaved: '2 days → 2 min', errorReduction: '90%', confidence: '88%', costImpact: 'Rs 3.4L/yr' },
    inputs: ['GLR specification from P6', 'Netlist from P4'],
    outputs: ['Register Description Table (.md)', 'Programming Sequence (.md)'],
    tools: ['Claude AI', 'GLR parser', 'Register map validator'],
  },
  {
    id: 'P8a', code: 'P08a', num: 8,
    name: 'SRS Document',
    tagline: 'Software Requirements Specification',
    color: '#00c6a7', auto: true, manual: false, time: '~4 min',
    subSteps: [
      { label: 'Load hardware spec from P1-P4', time: '5s', detail: 'Hardware interfaces, signals, and protocols extracted' },
      { label: 'Define software interfaces', time: '25s', detail: 'Driver APIs, HAL layer, communication protocols specified' },
      { label: 'Write functional requirements', time: '90s', detail: 'Claude writes all functional SW requirements with IDs' },
      { label: 'Write non-functional requirements', time: '40s', detail: 'Performance, memory, RTOS, safety level requirements' },
      { label: 'Generate traceability matrix', time: '20s', detail: 'HW-to-SW requirement links validated and mapped' },
      { label: 'Export SRS document', time: '10s', detail: 'SRS exported as .md and .docx with revision history' },
    ],
    metrics: { timeSaved: '2 weeks → 4 min', errorReduction: '74%', confidence: '90%', costImpact: 'Rs 7.6L/yr' },
    inputs: ['Requirements from P1', 'HRS from P2', 'GLR specification from P6'],
    outputs: ['SRS document (.md)', 'SRS document (.docx)'],
    tools: ['Claude AI', 'python-docx'],
  },
  {
    id: 'P8b', code: 'P08b', num: 9,
    name: 'SDD Document',
    tagline: 'Software Design Document',
    color: '#3b82f6', auto: true, manual: false, time: '~4 min',
    subSteps: [
      { label: 'Load SRS from P8a', time: '5s', detail: 'All software requirements parsed and structured' },
      { label: 'Design software architecture', time: '60s', detail: 'Layered architecture: HAL, drivers, middleware, application' },
      { label: 'Define module interfaces', time: '35s', detail: 'Function signatures, data structures, return codes defined' },
      { label: 'Write design descriptions', time: '80s', detail: 'Each module described with flowcharts and pseudocode' },
      { label: 'Generate architecture diagrams', time: '25s', detail: 'Mermaid diagrams: class, sequence, state machine' },
      { label: 'Export SDD document', time: '10s', detail: 'SDD exported as .md and .docx' },
    ],
    metrics: { timeSaved: '2 weeks → 4 min', errorReduction: '70%', confidence: '88%', costImpact: 'Rs 8.9L/yr' },
    inputs: ['SRS from P8a', 'HRS from P2', 'GLR specification from P6'],
    outputs: ['SDD document (.md)', 'SDD document (.docx)'],
    tools: ['Claude AI', 'python-docx', 'Mermaid (embedded diagrams)'],
  },
  {
    id: 'P8c', code: 'P08c', num: 10,
    name: 'Code Generation + Review',
    tagline: 'C/C++ drivers, Qt GUI, MISRA-C analysis, CI/CD',
    color: '#8b5cf6', auto: true, manual: false, time: '~4 min',
    subSteps: [
      { label: 'Generate C/C++ device drivers', time: '30s', detail: 'HAL register layer, interrupt handlers, DMA, error codes — MISRA-C 2012 compliant' },
      { label: 'Run Cppcheck static analysis', time: '45s', detail: 'Real cppcheck binary: null pointers, memory leaks, MISRA rule mapping' },
      { label: 'Run Lizard complexity analysis', time: '25s', detail: 'Cyclomatic complexity per function — MISRA Rule 15.5 violations flagged' },
      { label: 'Generate Qt C++ GUI application', time: '60s', detail: 'Qt 5.14.2 QMake app: .pro file, .ui designer files, promoted widgets — no dynamic widget creation in C++' },
      { label: 'Generate + validate CI/CD workflow', time: '12s', detail: 'Generates .github/workflows/hardware_pipeline_ci.yml then validates YAML syntax, job structure, and runs actionlint — no credentials needed' },
      { label: 'LLM MISRA-C 2023 deep review', time: '50s', detail: 'Claude maps findings to exact MISRA-C 2023 rule numbers, before/after fixes, CWE classification' },
      { label: 'Git commit + GitHub PR', time: '12s', detail: 'All artefacts committed; CI/CD workflow included; PR auto-opened with review summary' },
    ],
    metrics: { timeSaved: '3 days → 4 min', errorReduction: '83%', confidence: '95%', costImpact: 'Rs 4.8L/yr' },
    inputs: ['Firmware source files (.c/.h)', 'SDD from P8b', 'SRS from P8a', 'Register map from P7a'],
    outputs: [
      'C/C++ driver source files',
      'Qt 5.14.2 GUI (.pro, .ui files, MainWindow, DashboardPanel, ControlPanel, LogPanel, SettingsPanel, SerialWorker)',
      'GitHub Actions CI/CD workflow (.yml)',
      'Code review report (.md)',
      'Git commit + GitHub PR URL',
    ],
    tools: ['Cppcheck', 'Lizard', 'cpplint', 'Claude AI (MISRA-C 2023)', 'Qt 5.14.2 / QMake', 'gitpython', 'PyGithub'],
  },
];

export function getPhase(id: string): PhaseMeta | undefined {
  return PHASES.find(p => p.id === id);
}

export function getPhaseByIndex(idx: number): PhaseMeta {
  return PHASES[idx];
}

// Returns true if phase is unlocked given completed phase IDs.
// Manual phases (P5 PCB Layout, P7 FPGA Design) are always locked in the UI
// but their AI successors (P6 GLR, P8a SRS) unlock when the nearest prior AI
// phase is complete — manual phases are simply skipped in the dependency chain.
export function isUnlocked(phase: PhaseMeta, completedIds: string[]): boolean {
  if (phase.id === 'P1') return true;
  if (phase.manual) return false; // manual phases cannot be "run" — always shown locked
  const idx = PHASES.findIndex(p => p.id === phase.id);
  if (idx <= 0) return true;
  // Walk backwards to find the nearest non-manual predecessor
  for (let i = idx - 1; i >= 0; i--) {
    const prev = PHASES[i];
    if (!prev.manual) {
      return completedIds.includes(prev.id);
    }
    // prev is manual — skip it and keep looking
  }
  return true; // no prior AI phase found
}

// Document files generated by each phase
export const PHASE_DOCUMENTS: Record<string, string[]> = {
  'P1': ['requirements.md', 'block_diagram.md', 'architecture.md', 'component_recommendations.md'],
  'P2': ['HRS_{project_name}.md', 'HRS_{project_name}.docx', 'HRS_{project_name}.pdf'],
  'P3': ['compliance_report.md', 'compliance_matrix.csv', 'sbom_summary.md'],
  'P4': ['netlist_visual.md', 'drc_report.md'],
  'P5': [], // Manual phase - no AI-generated documents
  'P6': ['glr_specification.md', 'rtl_constraints.xdc', 'pin_assignments.csv'],
  'P7': [], // Manual phase - no AI-generated documents
  'P7a': ['register_description_table.md', 'programming_sequence.md'],
  'P8a': ['SRS_{project_name}.md', 'SRS_{project_name}.docx', 'traceability_matrix.csv'],
  'P8b': ['SDD_{project_name}.md', 'SDD_{project_name}.docx'],
  'P8c': [
    'code_review_report.md',
    'qt_gui/README.md',
    'qt_gui/main.cpp',
    'qt_gui/MainWindow.h',
    'qt_gui/MainWindow.cpp',
    'qt_gui/MainWindow.ui',
    'qt_gui/SerialWorker.h',
    'qt_gui/SerialWorker.cpp',
    'qt_gui/DashboardPanel.h',
    'qt_gui/DashboardPanel.cpp',
    'qt_gui/DashboardPanel.ui',
    'qt_gui/ControlPanel.h',
    'qt_gui/ControlPanel.cpp',
    'qt_gui/ControlPanel.ui',
    'qt_gui/LogPanel.h',
    'qt_gui/LogPanel.cpp',
    'qt_gui/LogPanel.ui',
    'qt_gui/SettingsPanel.h',
    'qt_gui/SettingsPanel.cpp',
    'qt_gui/SettingsPanel.ui',
    '.github/workflows/hardware_pipeline_ci.yml',
    'ci_validation_report.md',
    'git_summary.md',
  ],
};

// Get documents for the given phase only (not cumulative across prior phases).
// Each phase's Documents tab shows only that phase's output files.
export function getVisibleDocuments(phaseId: string, projectName: string): string[] {
  // Backend agents use project_name.replace(' ', '_') when naming output files.
  // e.g. project "BLDC Motor Controller" → "HRS_BLDC_Motor_Controller.md"
  const safeName = projectName.replace(/ /g, '_');
  const docs = PHASE_DOCUMENTS[phaseId] || [];
  return docs.map(doc => doc.replace('{project_name}', safeName));
}
