import React from 'react';
import type { PhaseDefinition } from '../types';

interface Props {
    phase: PhaseDefinition;
}

export default function PhaseMetrics({ phase }: Props) {
    const metrics = [
        { label: 'TIME SAVED', value: phase.metrics.timeSaved, icon: '\u23F1' },
        { label: 'ERROR REDUCTION', value: phase.metrics.errorReduction, icon: '\uD83D\uDEE1' },
        { label: 'CONFIDENCE', value: phase.metrics.confidence, icon: '\uD83C\uDFAF' },
        { label: 'ANNUAL COST IMPACT', value: phase.metrics.costImpact, icon: '\uD83D\uDCB0' },
    ];

    return (
        <div className="fade-up">
            <div style={{
                display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 16,
            }}>
                {metrics.map((m, i) => (
                    <div key={i} style={{
                        padding: '20px',
                        background: 'rgba(26,34,53,0.6)',
                        border: '1px solid rgba(42,58,80,0.6)',
                        borderRadius: 6,
                        transition: 'all 0.2s',
                    }}>
                        <div style={{ fontSize: 20, marginBottom: 8 }}>{m.icon}</div>
                        <div style={{
                            fontFamily: 'Syne, sans-serif', fontWeight: 700, fontSize: 20,
                            color: phase.color, marginBottom: 4,
                        }}>
                            {m.value}
                        </div>
                        <div style={{
                            fontSize: 9, letterSpacing: '0.14em', textTransform: 'uppercase',
                            color: '#64748b', fontFamily: 'DM Mono, monospace',
                        }}>
                            {m.label}
                        </div>
                    </div>
                ))}
            </div>

            {/* Total impact summary */}
            <div style={{
                marginTop: 20, padding: '16px 20px',
                background: phase.colorDim,
                border: `1px solid ${phase.colorBorder}`,
                borderRadius: 6,
            }}>
                <div style={{ fontSize: 9, letterSpacing: '0.14em', textTransform: 'uppercase', color: '#64748b', marginBottom: 6, fontFamily: 'DM Mono, monospace' }}>
                    PHASE IMPACT SUMMARY
                </div>
                <div style={{ fontSize: 12, color: '#e2e8f0', lineHeight: 1.6 }}>
                    P{phase.num} ({phase.name}) saves <span style={{ color: phase.color, fontWeight: 600 }}>{phase.metrics.timeSaved}</span> per project
                    with <span style={{ color: phase.color, fontWeight: 600 }}>{phase.metrics.errorReduction}</span> error reduction
                    at <span style={{ color: phase.color, fontWeight: 600 }}>{phase.metrics.confidence}</span> confidence.
                </div>
            </div>
        </div>
    );
}
