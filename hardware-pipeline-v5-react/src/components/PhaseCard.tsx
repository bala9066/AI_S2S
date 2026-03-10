import React, { useState } from 'react';
import type { PhaseDefinition, PhaseStatus, Statuses } from '../types';

interface Props {
  phase: PhaseDefinition;
  statuses: Statuses;
  onRun: (phaseId: string) => void;
  onApprove: (phaseId: string) => void;
}

function StatusBadge({ status }: { status: PhaseStatus }) {
  const map: Record<PhaseStatus, { label: string; cls: string }> = {
    completed:      { label: 'COMPLETE',  cls: 'badge-done'    },
    in_progress:    { label: 'RUNNING',   cls: 'badge-running'  },
    pending:        { label: 'PENDING',   cls: 'badge-pending'  },
    failed:         { label: 'FAILED',    cls: 'badge-failed'   },
    draft_pending:  { label: 'REVIEWING', cls: 'badge-manual'   },
  };
  const { label, cls } = map[status] || { label: 'PENDING', cls: 'badge-pending' };
  return <span className={`badge ${cls}`}>{label}</span>;
}

export default function PhaseCard({ phase, statuses, onRun, onApprove }: Props) {
  const [expanded, setExpanded] = useState(false);
  const phaseInfo = statuses[phase.id] || statuses[phase.num] || { status: 'pending' as PhaseStatus };
  const status = phaseInfo.status;
  const isRunning = status === 'in_progress';
  const isComplete = status === 'completed';
  const isDraftPending = status === 'draft_pending';

  const cardBorder = isRunning
    ? '1px solid var(--teal-border)'
    : isComplete
    ? '1px solid rgba(16,185,129,0.3)'
    : '1px solid var(--border)';

  const cardBg = isRunning
    ? 'rgba(0,198,167,0.04)'
    : 'var(--panel)';

  return (
    <div className="fade-up" style={{
      background: cardBg,
      border: cardBorder,
      borderRadius: '6px',
      padding: '20px',
      marginBottom: '12px',
      boxShadow: isRunning ? '0 0 24px rgba(0,198,167,0.08)' : 'none',
      transition: 'all 0.2s',
    }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span style={{ fontSize: '16px' }}>{phase.isAI ? '🤖' : '👤'}</span>
          <div>
            <div style={{ fontFamily: '"Syne", sans-serif', fontWeight: 700, fontSize: '15px', color: 'var(--text)' }}>
              <span style={{ color: 'var(--teal)' }}>{phase.num}</span>
              <span style={{ color: 'var(--text3)', margin: '0 6px' }}>·</span>
              {phase.name}
            </div>
            <div style={{ fontFamily: '"DM Mono", monospace', fontSize: '11px', color: 'var(--text2)', marginTop: '2px' }}>
              {phase.description}
            </div>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0, marginLeft: '12px' }}>
          {isRunning && <div className="spin-slow" style={{ width: '14px', height: '14px', border: '2px solid var(--teal)', borderTopColor: 'transparent', borderRadius: '50%' }} />}
          <StatusBadge status={status} />
        </div>
      </div>

      {phaseInfo.error && (
        <div style={{ margin: '8px 0', padding: '8px 12px', background: 'rgba(220,38,38,0.08)', border: '1px solid rgba(220,38,38,0.25)', borderRadius: '4px', color: 'var(--danger)', fontFamily: '"DM Mono", monospace', fontSize: '11px' }}>
          ⚠ {phaseInfo.error}
        </div>
      )}

      {/* Inputs / Outputs / Tools */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginTop: '14px' }}>
        <Section title="INPUTS" items={phase.inputs} />
        <Section title="OUTPUTS" items={phase.outputs} />
      </div>
      <div style={{ marginTop: '12px' }}>
        <div className="section-label" style={{ marginBottom: '6px' }}>TOOLS</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
          {phase.tools.map(t => (
            <span key={t} style={{ fontFamily: '"DM Mono", monospace', fontSize: '11px', padding: '2px 8px', background: 'var(--panel2)', borderRadius: '3px', color: 'var(--text2)', border: '1px solid var(--border2)' }}>{t}</span>
          ))}
        </div>
      </div>

      {/* Metrics */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px', marginTop: '14px', padding: '12px', background: 'var(--panel3)', borderRadius: '4px', border: '1px solid var(--border2)' }}>
        <Metric label="TIME SAVED" value={phase.metrics.timeSaved} />
        <Metric label="ERROR REDUCTION" value={phase.metrics.errorReduction} />
        <Metric label="CONFIDENCE" value={phase.metrics.confidence} />
        <Metric label="COST IMPACT" value={phase.metrics.costImpact} />
      </div>

      {/* Sub-Steps */}
      {phase.subSteps.length > 0 && (
        <div style={{ marginTop: '12px' }}>
          <button
            onClick={() => setExpanded(!expanded)}
            style={{ background: 'none', border: 'none', color: 'var(--teal)', fontFamily: '"DM Mono", monospace', fontSize: '11px', cursor: 'pointer', letterSpacing: '0.08em', padding: 0 }}
          >
            {expanded ? '▼' : '▶'} SUB-STEPS ({phase.subSteps.length})
          </button>
          {expanded && (
            <div style={{ marginTop: '8px', padding: '12px', background: 'var(--panel3)', borderRadius: '4px', border: '1px solid var(--border2)' }}>
              {phase.subSteps.map((step, i) => (
                <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '3px 0', borderBottom: i < phase.subSteps.length - 1 ? '1px dashed var(--border2)' : 'none' }}>
                  <span style={{ fontFamily: '"DM Mono", monospace', fontSize: '11px', color: 'var(--text2)' }}>
                    <span style={{ color: 'var(--teal)', marginRight: '8px' }}>{'①②③④⑤⑥⑦⑧⑨⑩'[i] || `${i+1}.`}</span>
                    {step.name}
                  </span>
                  <span style={{ fontFamily: '"DM Mono", monospace', fontSize: '11px', color: 'var(--text3)', marginLeft: '12px' }}>{step.time}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Actions */}
      <div style={{ display: 'flex', gap: '10px', marginTop: '16px', flexWrap: 'wrap' }}>
        {phase.externalTool ? (
          <div style={{ fontFamily: '"DM Mono", monospace', fontSize: '11px', color: 'var(--text3)', padding: '8px 0', display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span>👤</span> Completed externally in {phase.externalTool}
          </div>
        ) : (
          !isComplete && !isDraftPending && (
            <button
              onClick={() => onRun(phase.id)}
              disabled={isRunning}
              style={{
                padding: '8px 16px',
                background: isRunning ? 'rgba(0,198,167,0.1)' : 'rgba(0,198,167,0.12)',
                border: '1px solid var(--teal-border)',
                borderRadius: '4px',
                color: 'var(--teal)',
                fontFamily: '"DM Mono", monospace',
                fontSize: '11px',
                letterSpacing: '0.08em',
                cursor: isRunning ? 'not-allowed' : 'pointer',
                display: 'flex', alignItems: 'center', gap: '6px',
              }}
            >
              {isRunning ? (
                <><div className="spin-slow" style={{ width: '10px', height: '10px', border: '1.5px solid var(--teal)', borderTopColor: 'transparent', borderRadius: '50%' }} /> Running…</>
              ) : (
                <>▶ Run {phase.num}</>
              )}
            </button>
          )
        )}
        {(isComplete || isDraftPending) && (
          <button
            onClick={() => onApprove(phase.id)}
            style={{
              padding: '8px 16px',
              background: 'rgba(0,198,167,0.15)',
              border: '1px solid var(--teal)',
              borderRadius: '4px',
              color: 'var(--teal)',
              fontFamily: '"DM Mono", monospace',
              fontSize: '11px',
              letterSpacing: '0.08em',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            APPROVE & PROCEED →
          </button>
        )}
      </div>
    </div>
  );
}

function Section({ title, items }: { title: string; items: string[] }) {
  return (
    <div>
      <div className="section-label" style={{ marginBottom: '6px' }}>{title}</div>
      <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
        {items.map((item, i) => (
          <li key={i} style={{ fontFamily: '"DM Mono", monospace', fontSize: '11px', color: 'var(--text2)', padding: '2px 0', display: 'flex', alignItems: 'baseline', gap: '6px' }}>
            <span style={{ color: 'var(--teal)', flexShrink: 0 }}>•</span>{item}
          </li>
        ))}
      </ul>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="section-label" style={{ marginBottom: '4px' }}>{label}</div>
      <div style={{ fontFamily: '"Syne", sans-serif', fontSize: '14px', fontWeight: 700, color: 'var(--teal)' }}>{value}</div>
    </div>
  );
}
