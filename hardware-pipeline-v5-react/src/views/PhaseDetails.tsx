import React, { useState } from 'react';
import type { PhaseDefinition, PhaseStatus } from '../types';

interface Props {
    phase: PhaseDefinition;
    status: PhaseStatus;
    onRunPhase: (phase: string) => void;
    canRun: boolean;
}

export default function PhaseDetails({ phase, status, onRunPhase, canRun }: Props) {
    const [expanded, setExpanded] = useState(true);
    const isLocked = !phase.isAI;

    return (
        <div className="fade-up">
            {/* Locked banner for manual phases */}
            {isLocked && (
                <div style={{
                    padding: '12px 16px', marginBottom: 20, borderRadius: 6,
                    background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.2)',
                    display: 'flex', alignItems: 'center', gap: 10,
                    fontSize: 11, color: '#f59e0b',
                }}>
                    <span style={{ fontSize: 16 }}>{'\uD83D\uDD12'}</span>
                    <div>
                        <div style={{ fontWeight: 600 }}>Engineer-Driven Phase</div>
                        <div style={{ color: '#b45309', fontSize: 10, marginTop: 2 }}>
                            Completed externally in {phase.externalTool}
                        </div>
                    </div>
                </div>
            )}

            {/* Inputs */}
            <Section label="INPUTS" color={phase.color}>
                {phase.inputs.map((item, i) => (
                    <ListItem key={i} text={item} color={phase.color} />
                ))}
            </Section>

            {/* Outputs */}
            <Section label="OUTPUTS" color={phase.color}>
                {phase.outputs.map((item, i) => (
                    <ListItem key={i} text={item} color={phase.color} />
                ))}
            </Section>

            {/* Tools */}
            <Section label="TOOLS" color={phase.color}>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                    {phase.tools.map((tool, i) => (
                        <span key={i} style={{
                            padding: '3px 10px', borderRadius: 3, fontSize: 10,
                            background: phase.colorDim, border: `1px solid ${phase.colorBorder}`,
                            color: phase.color, fontFamily: 'DM Mono, monospace',
                        }}>
                            {tool}
                        </span>
                    ))}
                </div>
            </Section>

            {/* Sub-steps accordion */}
            <div style={{ marginTop: 20 }}>
                <button
                    onClick={() => setExpanded(!expanded)}
                    style={{
                        width: '100%', background: 'none', border: 'none', cursor: 'pointer',
                        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                        padding: '8px 0', fontSize: 9, letterSpacing: '0.16em', textTransform: 'uppercase',
                        color: '#64748b', fontFamily: 'DM Mono, monospace',
                    }}
                >
                    <span>SUB-STEPS ({phase.subSteps.length})</span>
                    <span style={{ fontSize: 12, transition: 'transform 0.2s', transform: expanded ? 'rotate(180deg)' : 'none' }}>
                        {'\u25BC'}
                    </span>
                </button>
                {expanded && (
                    <div style={{ borderLeft: `1px solid ${phase.colorBorder}`, marginLeft: 8, paddingLeft: 16 }}>
                        {phase.subSteps.map((step, i) => (
                            <div key={i} style={{
                                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                                padding: '6px 0', borderBottom: '1px solid rgba(42,58,80,0.3)',
                            }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                    <span style={{ fontSize: 10, color: phase.color, fontFamily: 'DM Mono, monospace', fontWeight: 600, width: 16 }}>
                                        {i + 1}.
                                    </span>
                                    <span style={{ fontSize: 11, color: '#94a3b8' }}>{step.name}</span>
                                </div>
                                <span style={{ fontSize: 10, color: '#475569', fontFamily: 'DM Mono, monospace', whiteSpace: 'nowrap' }}>
                                    {step.time}
                                </span>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {/* Action buttons */}
            <div style={{ display: 'flex', gap: 12, marginTop: 24 }}>
                {phase.isAI && status === 'pending' && (
                    <button
                        disabled={!canRun}
                        onClick={() => onRunPhase(phase.id)}
                        style={{
                            padding: '10px 20px', borderRadius: 6, cursor: canRun ? 'pointer' : 'not-allowed',
                            opacity: canRun ? 1 : 0.4,
                            background: phase.colorDim, border: `1px solid ${phase.colorBorder}`,
                            color: phase.color, fontFamily: 'DM Mono, monospace', fontSize: 11,
                            letterSpacing: '0.06em', fontWeight: 600, transition: 'all 0.15s',
                        }}
                    >
                        {'\u25B6'} Run P{phase.num}
                    </button>
                )}
                {status === 'draft_pending' && (
                    <div style={{
                        padding: '10px 20px', borderRadius: 6,
                        background: 'rgba(201,168,76,0.08)', border: '1px solid rgba(201,168,76,0.2)',
                        color: '#c9a84c', fontFamily: 'DM Mono, monospace', fontSize: 11,
                        letterSpacing: '0.06em',
                    }}>
                        {'\u231B'} DRAFT PENDING - REVIEW IN CHAT
                    </div>
                )}
                {status === 'completed' && (
                    <div style={{
                        padding: '10px 20px', borderRadius: 6,
                        background: 'rgba(16,185,129,0.08)', border: '1px solid rgba(16,185,129,0.2)',
                        color: '#10b981', fontFamily: 'DM Mono, monospace', fontSize: 11,
                        letterSpacing: '0.06em',
                    }}>
                        {'\u2713'} COMPLETED
                    </div>
                )}
                {status === 'in_progress' && (
                    <div style={{
                        padding: '10px 20px', borderRadius: 6,
                        background: phase.colorDim, border: `1px solid ${phase.colorBorder}`,
                        color: phase.color, fontFamily: 'DM Mono, monospace', fontSize: 11,
                        display: 'flex', alignItems: 'center', gap: 8,
                    }}>
                        <span className="spin-slow" style={{ display: 'inline-block', width: 12, height: 12, border: `2px solid ${phase.colorBorder}`, borderTopColor: phase.color, borderRadius: '50%' }} />
                        Running...
                    </div>
                )}
            </div>
        </div>
    );
}

function Section({ label, color, children }: { label: string; color: string; children: React.ReactNode }) {
    return (
        <div style={{ marginBottom: 16 }}>
            <div style={{
                fontSize: 9, letterSpacing: '0.16em', textTransform: 'uppercase',
                color: '#64748b', fontFamily: 'DM Mono, monospace', marginBottom: 8,
                paddingBottom: 4, borderBottom: `1px solid rgba(42,58,80,0.4)`,
            }}>
                {label}
            </div>
            {children}
        </div>
    );
}

function ListItem({ text, color }: { text: string; color: string }) {
    return (
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, padding: '3px 0' }}>
            <span style={{ color, fontSize: 6, marginTop: 5 }}>{'\u25CF'}</span>
            <span style={{ fontSize: 11, color: '#94a3b8' }}>{text}</span>
        </div>
    );
}
