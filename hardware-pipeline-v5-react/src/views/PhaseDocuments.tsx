import React from 'react';
import type { PhaseDefinition, Project } from '../types';

interface Props {
    phase: PhaseDefinition;
    project: Project | null;
}

export default function PhaseDocuments({ phase, project }: Props) {
    if (!project) {
        return <div style={{ color: '#475569', fontSize: 11 }}>No project loaded</div>;
    }

    return (
        <div className="fade-up">
            {/* Phase-specific document content */}
            {phase.id === 'P1' && <P1Documents project={project} color={phase.color} />}
            {phase.id === 'P2' && <GenericDocView project={project} title="HRS Document" files={['HRS_{project}.md']} color={phase.color} desc="IEEE 29148-compliant Hardware Requirements Specification with traceability matrix and Mermaid diagrams" />}
            {phase.id === 'P3' && <P3ComplianceView project={project} color={phase.color} />}
            {phase.id === 'P4' && <P4NetlistView project={project} color={phase.color} />}
            {phase.id === 'P5' && <ExternalToolView tool="Altium Designer / KiCad / OrCAD" desc="Download the validated netlist and import into your EDA tool for PCB layout" color={phase.color} />}
            {phase.id === 'P6' && <GenericDocView project={project} title="GLR Specification" files={['glr_specification.md', 'io_table.xlsx']} color={phase.color} desc="Glue Logic Requirements with complete I/O specs, pin assignments, and timing constraints" />}
            {phase.id === 'P7' && <ExternalToolView tool="Vivado / Quartus" desc="Use the GLR specification to implement RTL design" color={phase.color} />}
            {phase.id === 'P8a' && <GenericDocView project={project} title="SRS Document" files={['SRS_{project}.md']} color={phase.color} desc="IEEE 830/29148-compliant Software Requirements Specification with requirement traceability matrix" />}
            {phase.id === 'P8b' && <GenericDocView project={project} title="SDD Document" files={['SDD_{project}.md']} color={phase.color} desc="IEEE 1016-compliant Software Design Document with Mermaid architecture, sequence, and state diagrams" />}
            {phase.id === 'P8c' && <P8cCodeReviewView project={project} color={phase.color} />}
        </div>
    );
}

/* ── P1: Component Recommendations + Block Diagrams ── */
function P1Documents({ project, color }: { project: Project; color: string }) {
    return (
        <div>
            <DocCard project={project} title="Requirements Document" icon={'\uD83D\uDCCB'} color={color}
                desc="Structured requirements extracted from design conversation"
                filename="requirements.md" />
            <DocCard project={project} title="System Block Diagram" icon={'\uD83D\uDDFA'} color={color}
                desc="Auto-generated system architecture diagram (Mermaid)"
                filename="block_diagram.md" />
            <DocCard project={project} title="Component Recommendations" icon={'\u2699'} color={color}
                desc="AI-suggested components with part numbers, specs, and alternatives"
                filename="component_recommendations.md" />
        </div>
    );
}

/* ── P3: Compliance Matrix ── */
function P3ComplianceView({ color, project }: { color: string; project: Project }) {
    const standards = ['RoHS', 'REACH', 'FCC', 'CE', 'MIL-STD-810', 'MIL-STD-461', 'IPC-2221'];
    return (
        <div>
            <DocCard project={project} title="Compliance Report" icon={'\uD83D\uDEE1'} color={color}
                desc="Detailed compliance analysis across all applicable standards"
                filename="compliance_report.md" />

            {/* Compliance matrix preview */}
            <div style={{
                marginTop: 16, padding: '16px',
                background: 'rgba(26,34,53,0.6)', border: '1px solid rgba(42,58,80,0.6)',
                borderRadius: 6,
            }}>
                <div className="section-label" style={{ marginBottom: 12 }}>COMPLIANCE MATRIX PREVIEW</div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))', gap: 8 }}>
                    {standards.map(std => (
                        <div key={std} style={{
                            padding: '8px 12px', borderRadius: 4,
                            background: 'rgba(42,58,80,0.3)', border: '1px solid rgba(42,58,80,0.5)',
                            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                        }}>
                            <span style={{ fontSize: 10, color: '#94a3b8' }}>{std}</span>
                            <span className="badge badge-pending" style={{ fontSize: 8 }}>PENDING</span>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}

/* ── P4: Netlist Graph + DRC ── */
function P4NetlistView({ color, project }: { color: string; project: Project }) {
    return (
        <div>
            <DocCard project={project} title="Netlist Data" icon={'\uD83D\uDD17'} color={color}
                desc="Machine-readable component connectivity graph (JSON)"
                filename="netlist.json" />
            <DocCard project={project} title="Visual Netlist Diagram" icon={'\uD83D\uDDFA'} color={color}
                desc="Interactive node/edge visualization of component connectivity"
                filename="netlist_visual.md" />

            {/* DRC Results */}
            <div style={{
                marginTop: 16, padding: '16px',
                background: 'rgba(26,34,53,0.6)', border: '1px solid rgba(42,58,80,0.6)',
                borderRadius: 6,
            }}>
                <div className="section-label" style={{ marginBottom: 12 }}>DRC RESULTS</div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
                    {[{ label: 'Nodes', value: '—' }, { label: 'Edges', value: '—' }, { label: 'Violations', value: '—' }].map(item => (
                        <div key={item.label} style={{ textAlign: 'center' }}>
                            <div style={{ fontFamily: 'Syne, sans-serif', fontSize: 18, fontWeight: 700, color }}>{item.value}</div>
                            <div style={{ fontSize: 9, color: '#64748b', letterSpacing: '0.1em', textTransform: 'uppercase' }}>{item.label}</div>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}

/* ── P8c: Code Review Dashboard ── */
function P8cCodeReviewView({ color, project }: { color: string; project: Project }) {
    const severities = [
        { level: 'Critical', count: 0, clr: '#dc2626' },
        { level: 'Warning', count: 0, clr: '#f59e0b' },
        { level: 'Info', count: 0, clr: '#3b82f6' },
        { level: 'Style', count: 0, clr: '#64748b' },
    ];
    return (
        <div>
            <DocCard project={project} title="MISRA-C Compliance Report" icon={'\uD83D\uDD0D'} color={color}
                desc="Static analysis results with MISRA-C rule violations and fixes"
                filename="code_review_report.md" />
            <DocCard project={project} title="Generated Driver Code" icon={'\uD83D\uDCBB'} color={color}
                desc="C/C++ device drivers generated from SDD architecture"
                filename="drivers/" />

            {/* Severity breakdown */}
            <div style={{
                marginTop: 16, padding: '16px',
                background: 'rgba(26,34,53,0.6)', border: '1px solid rgba(42,58,80,0.6)',
                borderRadius: 6,
            }}>
                <div className="section-label" style={{ marginBottom: 12 }}>SEVERITY BREAKDOWN</div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8 }}>
                    {severities.map(s => (
                        <div key={s.level} style={{ textAlign: 'center', padding: '8px' }}>
                            <div style={{ fontFamily: 'Syne, sans-serif', fontSize: 20, fontWeight: 700, color: s.clr }}>{s.count}</div>
                            <div style={{ fontSize: 9, color: '#64748b', letterSpacing: '0.08em', textTransform: 'uppercase' }}>{s.level}</div>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}

/* ── Generic document viewer ── */
function GenericDocView({ title, files, color, desc, project }: { title: string; files: string[]; color: string; desc: string; project: Project }) {
    return (
        <div>
            <DocCard project={project} title={title} icon={'\uD83D\uDCC4'} color={color} desc={desc} filename={files[0]} />
            {files.length > 1 && files.slice(1).map(f => (
                <DocCard key={f} title={f} icon={'\uD83D\uDCC4'} color={color} desc="" filename={f} />
            ))}
        </div>
    );
}

/* ── External tool placeholder ── */
function ExternalToolView({ tool, desc, color }: { tool: string; desc: string; color: string }) {
    return (
        <div style={{
            padding: '24px', borderRadius: 6,
            background: 'rgba(100,116,139,0.06)', border: '1px solid rgba(100,116,139,0.2)',
            textAlign: 'center',
        }}>
            <div style={{ fontSize: 32, marginBottom: 12 }}>{'\uD83D\uDD12'}</div>
            <div style={{ fontFamily: 'Syne, sans-serif', fontWeight: 600, fontSize: 14, color: '#94a3b8', marginBottom: 6 }}>
                {tool}
            </div>
            <div style={{ fontSize: 11, color: '#64748b', maxWidth: 400, margin: '0 auto' }}>{desc}</div>
        </div>
    );
}

/* ── Reusable document card ── */
function DocCard({ title, icon, color, desc, filename, project }: { title: string; icon: string; color: string; desc: string; filename: string; project: Project }) {
    const formattedFilename = filename.replace('{project}', project.id.toString());
    const downloadUrl = `${BASE}/api/v1/projects/${project.id}/documents/${formattedFilename}`;

    return (
        <a href={downloadUrl} target="_blank" rel="noopener noreferrer" style={{ textDecoration: 'none', display: 'block' }}>
            <div style={{
                padding: '14px 16px', marginBottom: 10, borderRadius: 6,
                background: 'rgba(26,34,53,0.6)', border: '1px solid rgba(42,58,80,0.6)',
                display: 'flex', alignItems: 'flex-start', gap: 12,
                transition: 'border-color 0.15s',
                cursor: 'pointer',
            }}
                onMouseEnter={e => (e.currentTarget.style.borderColor = color)}
                onMouseLeave={e => (e.currentTarget.style.borderColor = 'rgba(42,58,80,0.6)')}
            >
                <div style={{
                    width: 32, height: 32, borderRadius: 4, flexShrink: 0,
                    background: `${color}15`, display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: 16,
                }}>
                    {icon}
                </div>
                <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: '#e2e8f0', marginBottom: 2 }}>{title}</div>
                    {desc && <div style={{ fontSize: 10, color: '#64748b', marginBottom: 4 }}>{desc}</div>}
                    <div style={{ fontSize: 9, color: '#475569', fontFamily: 'DM Mono, monospace' }}>{formattedFilename}</div>
                </div>
                <div style={{
                    fontSize: 18, color: color, display: 'flex', alignItems: 'center', padding: '0 8px', opacity: 0.8
                }}>
                    ⤓
                </div>
            </div>
        </a>
    );
}
