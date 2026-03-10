import type { PhaseDefinition } from './types';

export const PHASES: PhaseDefinition[] = [
  {
    id: 'P1', num: '1', name: 'Design & Requirements', isAI: true,
    color: '#00c6a7', colorDim: 'rgba(0,198,167,0.12)', colorBorder: 'rgba(0,198,167,0.4)',
    description: 'AI-powered design chat — block diagram + requirements capture via iterative conversation',
    inputs: ['Customer brief / verbal description', 'Product specifications', 'Target environment constraints'],
    outputs: ['System block diagram', 'IEEE 29148 requirements draft', 'Engineering assumptions log'],
    tools: ['Claude AI', 'Chroma vector DB', 'Domain-specific templates'],
    metrics: { timeSaved: '6–8 hrs', errorReduction: '40%', confidence: '94%', costImpact: '$12,000/yr' },
    subSteps: [
      { name: 'Parse design intent from conversation', time: '5 min' },
      { name: 'Generate system block diagram', time: '8 min' },
      { name: 'Extract requirements with SHALL statements', time: '12 min' },
      { name: 'Engineer ↔ AI requirement finalization', time: '15 min' },
    ],
  },
  {
    id: 'P2', num: '2', name: 'HRS Document', isAI: true,
    color: '#3b82f6', colorDim: 'rgba(59,130,246,0.12)', colorBorder: 'rgba(59,130,246,0.4)',
    description: 'Auto-generate IEEE 29148-compliant Hardware Requirements Specification with traceability matrix',
    inputs: ['P1 block diagram', 'Requirements list', 'Compliance targets'],
    outputs: ['Full HRS .docx document', 'Traceability matrix', 'Review checklist'],
    tools: ['Claude AI', 'Doxygen', 'Export .docx / .pdf'],
    metrics: { timeSaved: '8–12 hrs', errorReduction: '55%', confidence: '91%', costImpact: '$18,000/yr' },
    subSteps: [
      { name: 'Structure IEEE 29148 template', time: '4 min' },
      { name: 'Populate all SHALL/SHOULD requirements', time: '15 min' },
      { name: 'Build traceability matrix', time: '8 min' },
      { name: 'Generate review checklist', time: '5 min' },
    ],
  },
  {
    id: 'P3', num: '3', name: 'Compliance Check', isAI: true,
    color: '#f59e0b', colorDim: 'rgba(245,158,11,0.12)', colorBorder: 'rgba(245,158,11,0.4)',
    description: 'Automated RoHS / REACH / FCC / MIL-STD rules engine with certificate readiness scoring',
    inputs: ['HRS document', 'Component list', 'Target markets'],
    outputs: ['Compliance matrix report', 'Certificate readiness score', 'Compliance report export'],
    tools: ['Custom rules engine', 'DigiKey/Mouser API', 'Compliance DB'],
    metrics: { timeSaved: '10–15 hrs', errorReduction: '70%', confidence: '96%', costImpact: '$25,000/yr' },
    subSteps: [
      { name: 'Each component checked vs restricted substance DB', time: '6 min' },
      { name: 'FCC / CE / MIL-STD rules evaluation', time: '8 min' },
      { name: 'Compliance gap analysis', time: '5 min' },
      { name: 'Certificate readiness scoring', time: '3 min' },
    ],
  },
  {
    id: 'P4', num: '4', name: 'Netlist Generation', isAI: true,
    color: '#a855f7', colorDim: 'rgba(168,85,247,0.12)', colorBorder: 'rgba(168,85,247,0.4)',
    description: 'Build component connectivity graph with DRC validation and BOM generation',
    inputs: ['Compliance-approved components', 'Block diagram connections', 'Pin/interface definitions'],
    outputs: ['Netlist (.json)', 'Visual netlist diagram', 'Final BOM with footprints'],
    tools: ['Claude AI', 'DigiKey/Mouser API', 'DRC/ERC tools'],
    metrics: { timeSaved: '5–8 hrs', errorReduction: '60%', confidence: '89%', costImpact: '$15,000/yr' },
    subSteps: [
      { name: 'Resolve block diagram to actual component pins', time: '8 min' },
      { name: 'Build connectivity graph', time: '10 min' },
      { name: 'Run DRC / ERC validation', time: '6 min' },
      { name: 'Export netlist + BOM', time: '4 min' },
    ],
  },
  {
    id: 'P5', num: '5', name: 'PCB Layout', isAI: false,
    color: '#64748b', colorDim: 'rgba(100,116,139,0.12)', colorBorder: 'rgba(100,116,139,0.4)',
    description: 'Engineer-driven PCB design in EDA tool — component placement, routing, layer stackup',
    inputs: ['Validated netlist', 'BOM with footprints', 'Mechanical constraints'],
    outputs: ['PCB layout file', 'Gerber files', 'Assembly drawings'],
    tools: ['Altium Designer / KiCad / OrCAD'],
    metrics: { timeSaved: '0 hrs', errorReduction: '0%', confidence: '100%', costImpact: '$0/yr' },
    subSteps: [
      { name: 'Import netlist to EDA tool', time: 'Manual' },
      { name: 'Define layer stackup', time: 'Manual' },
      { name: 'Component placement', time: 'Manual' },
      { name: 'Complete routing + fill', time: 'Manual' },
      { name: 'DRC / ERC final check', time: 'Manual' },
    ],
    externalTool: 'Altium Designer / KiCad / OrCAD',
  },
  {
    id: 'P6', num: '6', name: 'GLR Specification', isAI: true,
    color: '#06b6d4', colorDim: 'rgba(6,182,212,0.12)', colorBorder: 'rgba(6,182,212,0.4)',
    description: 'AI generates Glue Logic Requirements document for FPGA/CPLD based on validated netlist',
    inputs: ['Validated netlist', 'Interface requirements', 'FPGA target selection'],
    outputs: ['GLR document', 'FPGA I/O map', 'Custom IP cores list'],
    tools: ['Claude AI', 'Vivado API', 'Custom IP cores'],
    metrics: { timeSaved: '8–12 hrs', errorReduction: '50%', confidence: '87%', costImpact: '$20,000/yr' },
    subSteps: [
      { name: 'Extract FPGA I/O signals from netlist', time: '5 min' },
      { name: 'Define glue logic requirements', time: '12 min' },
      { name: 'Map to FPGA pin constraints', time: '8 min' },
      { name: 'Generate GLR document', time: '6 min' },
    ],
  },
  {
    id: 'P7', num: '7', name: 'FPGA Design', isAI: false,
    color: '#64748b', colorDim: 'rgba(100,116,139,0.12)', colorBorder: 'rgba(100,116,139,0.4)',
    description: 'Engineer implements RTL in Vivado or Quartus — synthesis, simulation, timing closure',
    inputs: ['GLR document', 'FPGA I/O map', 'Target FPGA part'],
    outputs: ['RTL design files', 'Synthesis report', 'Timing closure report'],
    tools: ['Vivado / Quartus'],
    metrics: { timeSaved: '0 hrs', errorReduction: '0%', confidence: '100%', costImpact: '$0/yr' },
    subSteps: [
      { name: 'RTL implementation', time: 'Manual' },
      { name: 'Functional simulation', time: 'Manual' },
      { name: 'Synthesis + timing closure', time: 'Manual' },
      { name: 'Generate bitstream', time: 'Manual' },
    ],
    externalTool: 'Vivado / Quartus',
  },
  {
    id: 'P8a', num: '8a', name: 'SRS Document', isAI: true,
    color: '#6366f1', colorDim: 'rgba(99,102,241,0.12)', colorBorder: 'rgba(99,102,241,0.4)',
    description: 'Auto-generate Software Requirements Specification from hardware interfaces and block diagram',
    inputs: ['GLR document', 'Interface definitions', 'Register map'],
    outputs: ['SRS document', 'API documentation', 'Dashboard UI spec'],
    tools: ['Claude AI', 'Doxygen API docs'],
    metrics: { timeSaved: '6–10 hrs', errorReduction: '45%', confidence: '90%', costImpact: '$16,000/yr' },
    subSteps: [
      { name: 'Parse all interface definitions', time: '5 min' },
      { name: 'Generate software requirements', time: '10 min' },
      { name: 'Build register map documentation', time: '8 min' },
      { name: 'Generate API stubs', time: '6 min' },
    ],
  },
  {
    id: 'P8b', num: '8b', name: 'SDD Document', isAI: true,
    color: '#8b5cf6', colorDim: 'rgba(139,92,246,0.12)', colorBorder: 'rgba(139,92,246,0.4)',
    description: 'Auto-generate Software Design Document with driver architecture and module breakdown',
    inputs: ['SRS document', 'Hardware abstraction layer spec', 'Driver requirements'],
    outputs: ['SDD document', 'Driver architecture diagram', 'Module interface specs'],
    tools: ['Claude AI', 'Doxygen'],
    metrics: { timeSaved: '8–10 hrs', errorReduction: '45%', confidence: '88%', costImpact: '$18,000/yr' },
    subSteps: [
      { name: 'Design software architecture', time: '8 min' },
      { name: 'Define module boundaries', time: '6 min' },
      { name: 'Generate driver skeletons', time: '10 min' },
      { name: 'Create SDD document', time: '5 min' },
    ],
  },
  {
    id: 'P8c', num: '8c', name: 'Code Review', isAI: true,
    color: '#f43f5e', colorDim: 'rgba(244,63,94,0.12)', colorBorder: 'rgba(244,63,94,0.4)',
    description: 'MISRA-C compliant code generation + Clang-Tidy static analysis and violation report',
    inputs: ['SDD document', 'Driver specifications', 'MISRA-C rules set'],
    outputs: ['MISRA-C compliant code', 'Static analysis report', 'Violation correction log'],
    tools: ['Clang-Tidy + MISRA', 'Claude AI', 'Custom MISRA rules engine'],
    metrics: { timeSaved: '12–20 hrs', errorReduction: '85%', confidence: '97%', costImpact: '$40,000/yr' },
    subSteps: [
      { name: 'Generate C driver code from SDD', time: '10 min' },
      { name: 'Run MISRA-C rule checks', time: '5 min' },
      { name: 'Auto-fix MISRA violations', time: '8 min' },
      { name: 'Generate compliance report', time: '4 min' },
    ],
  },
];

/** Get available sub-tabs for a given phase */
export function getSubTabs(phaseId: string): { id: string; label: string }[] {
  const tabs: { id: string; label: string }[] = [];
  if (phaseId === 'P1') tabs.push({ id: 'chat', label: 'DESIGN CHAT' });
  tabs.push({ id: 'details', label: 'DETAILS' });
  const phase = PHASES.find(p => p.id === phaseId);
  if (phase?.isAI) tabs.push({ id: 'metrics', label: 'METRICS' });
  tabs.push({ id: 'documents', label: 'DOCUMENTS' });
  return tabs;
}

/** Get phase by id */
export function getPhase(phaseId: string): PhaseDefinition | undefined {
  return PHASES.find(p => p.id === phaseId);
}
