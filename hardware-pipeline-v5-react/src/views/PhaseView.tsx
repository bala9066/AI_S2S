import React from 'react';
import type { SubTabId, Project, Statuses } from '../types';
import { PHASES, getSubTabs, getPhase } from '../phaseData';
import PhaseDetails from './PhaseDetails';
import PhaseMetrics from './PhaseMetrics';
import PhaseDocuments from './PhaseDocuments';
import DesignChat from './DesignChat';

interface Props {
    project: Project | null;
    statuses: Statuses;
    activePhase: string;
    subTab: SubTabId;
    setSubTab: (t: SubTabId) => void;
    onRunPhase: (phase: string) => void;
}

export default function PhaseView({ project, statuses, activePhase, subTab, setSubTab, onRunPhase }: Props) {
    const phase = getPhase(activePhase);
    const tabs = getSubTabs(activePhase);

    if (!phase) return null;

    // If current subTab is not available for this phase, default to 'details'
    const validTab = tabs.find(t => t.id === subTab) ? subTab : 'details';

    const st = statuses[phase.id]?.status || 'pending';

    const phaseIndex = PHASES.findIndex(p => p.id === phase.id);
    const prevPhase = phaseIndex > 0 ? PHASES[phaseIndex - 1] : null;
    const canRun = prevPhase ? (statuses[prevPhase.id]?.status === 'completed') : true;

    return (
        <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
            {/* Phase header */}
            <div style={{
                padding: '16px 24px 0',
                borderBottom: '1px solid rgba(42,58,80,0.6)',
                background: 'rgba(7,11,20,0.5)',
            }}>
                {/* Phase title row */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
                    <div style={{
                        width: 36, height: 36, borderRadius: 6,
                        background: phase.colorDim,
                        border: `1px solid ${phase.colorBorder}`,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        fontSize: 14, fontFamily: 'DM Mono, monospace', fontWeight: 700,
                        color: phase.color,
                    }}>
                        {phase.isAI ? '\uD83E\uDD16' : '\uD83D\uDC64'}
                    </div>
                    <div style={{ flex: 1 }}>
                        <div style={{ fontFamily: 'Syne, sans-serif', fontWeight: 700, fontSize: 16, color: '#e2e8f0' }}>
                            P{phase.num} &middot; <span style={{ color: phase.color }}>{phase.name}</span>
                        </div>
                        <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>
                            {phase.description}
                        </div>
                    </div>
                    <div>
                        {st === 'completed' && <span className="badge badge-done">COMPLETED</span>}
                        {st === 'in_progress' && <span className="badge badge-running">RUNNING</span>}
                        {st === 'failed' && <span className="badge badge-failed">FAILED</span>}
                        {st === 'draft_pending' && <span className="badge badge-pending">DRAFT PENDING</span>}
                        {st === 'pending' && !phase.isAI && <span className="badge badge-locked">LOCKED</span>}
                        {st === 'pending' && phase.isAI && <span className="badge badge-pending">PENDING</span>}
                    </div>
                </div>

                {/* Sub-tab bar */}
                <div style={{ display: 'flex', gap: 0 }}>
                    {tabs.map(t => (
                        <button
                            key={t.id}
                            onClick={() => setSubTab(t.id as SubTabId)}
                            style={{
                                padding: '8px 16px',
                                background: 'none', border: 'none', cursor: 'pointer',
                                fontFamily: 'DM Mono, monospace', fontSize: 10, letterSpacing: '0.1em',
                                color: validTab === t.id ? phase.color : '#64748b',
                                borderBottom: validTab === t.id ? `2px solid ${phase.color}` : '2px solid transparent',
                                transition: 'all 0.15s',
                            }}
                            onMouseEnter={e => { if (validTab !== t.id) (e.target as HTMLElement).style.color = '#94a3b8'; }}
                            onMouseLeave={e => { if (validTab !== t.id) (e.target as HTMLElement).style.color = '#64748b'; }}
                        >
                            {t.label}
                        </button>
                    ))}
                </div>
            </div>

            {/* Sub-tab content */}
            <div style={{ flex: 1, overflow: 'auto', padding: '20px 24px' }}>
                {validTab === 'chat' && <DesignChat project={project} />}
                {validTab === 'details' && <PhaseDetails phase={phase} status={st} onRunPhase={onRunPhase} canRun={canRun} />}
                {validTab === 'metrics' && <PhaseMetrics phase={phase} />}
                {validTab === 'documents' && <PhaseDocuments phase={phase} project={project} />}
            </div>
        </div>
    );
}
