import type { PhaseMeta, PhaseStatusValue, CenterTab } from '../types';

interface Props {
  phase: PhaseMeta;
  status: PhaseStatusValue;
  tab: CenterTab;
  onTabChange: (t: CenterTab) => void;
}

export default function PhaseHeader({ phase, status, tab, onTabChange }: Props) {
  const isComplete = status === 'completed';
  const isRunning = status === 'in_progress';

  const tabs: { id: CenterTab; label: string; show: boolean }[] = [
    { id: 'chat', label: '⚡ Chat', show: phase.id === 'P1' },
    { id: 'details', label: '◆ Details', show: true },
    { id: 'metrics', label: '◎ Metrics', show: true },
    { id: 'documents', label: '📄 Documents', show: true },
  ].filter(t => t.show);

  return (
    <div style={{ padding: '22px 26px 0', borderBottom: '1px solid var(--border2)' }}>
      {/* Phase title row */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 14, marginBottom: 14 }}>
        {/* Circle icon */}
        <div style={{
          width: 46, height: 46, borderRadius: '50%', flexShrink: 0,
          background: `${phase.color}15`,
          border: `2px solid ${phase.color}`,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontFamily: "'Syne', sans-serif", fontWeight: 800, fontSize: 16,
          color: phase.color,
          boxShadow: isRunning ? `0 0 18px ${phase.color}44` : 'none',
          transition: 'box-shadow 0.3s',
        }}>
          {isComplete && !phase.manual ? '✓' : isRunning ? (
            <div style={{
              width: 16, height: 16, borderRadius: '50%',
              border: `2.5px solid ${phase.color}`,
              borderTopColor: 'transparent',
              animation: 'spin 0.8s linear infinite',
            }} />
          ) : phase.num}
        </div>

        {/* Meta */}
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 5, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 11, color: phase.color, letterSpacing: '0.12em', fontFamily: "'DM Mono', monospace" }}>
              {phase.code}
            </span>
            <span style={{
              fontSize: 10, padding: '1px 8px', borderRadius: 3,
              color: phase.auto ? phase.color : 'var(--text4)',
              background: phase.auto ? `${phase.color}15` : 'var(--panel2)',
              border: `1px solid ${phase.auto ? phase.color + '33' : 'var(--panel3)'}`,
            }}>
              {phase.manual ? 'MANUAL / EXTERNAL' : '⚡ AUTOMATED'}
            </span>
            <span style={{ fontSize: 11, color: 'var(--text4)', fontFamily: "'DM Mono', monospace" }}>
              {phase.time}
            </span>
            {isComplete && !phase.manual && (
              <span style={{
                fontSize: 10, color: phase.color, background: `${phase.color}15`,
                border: `1px solid ${phase.color}33`, padding: '1px 10px', borderRadius: 3,
              }}>
                COMPLETED
              </span>
            )}
            {isRunning && (
              <span style={{
                fontSize: 10, color: '#f59e0b', background: 'rgba(245,158,11,0.1)',
                border: '1px solid rgba(245,158,11,0.3)', padding: '1px 10px', borderRadius: 3,
                animation: 'pulse 1.5s ease infinite',
              }}>
                RUNNING...
              </span>
            )}
          </div>
          <div style={{ fontFamily: "'Syne', sans-serif", fontSize: 17, fontWeight: 800, color: 'var(--text)' }}>
            {phase.name}
          </div>
          <div style={{ fontSize: 12, color: 'var(--text3)', marginTop: 3 }}>{phase.tagline}</div>
        </div>
      </div>

      {/* Manual lock note */}
      {phase.manual && (
        <div style={{
          marginBottom: 14, padding: '9px 14px',
          background: 'var(--panel2)', border: '1px solid var(--panel3)',
          borderRadius: 6, fontSize: 12, color: 'var(--text3)',
          display: 'flex', gap: 8, alignItems: 'center',
        }}>
          <span>🔒</span>
          <span>
            Completed externally in {phase.externalTool || 'external EDA tool'}. This phase is informational and does not block the pipeline.
          </span>
        </div>
      )}

      {/* Sub-tabs */}
      <div style={{ display: 'flex', gap: 0 }}>
        {tabs.map(t => (
          <button key={t.id} onClick={() => onTabChange(t.id)} style={{
            padding: '7px 18px', fontSize: 12,
            fontFamily: "'DM Mono', monospace",
            cursor: 'pointer', border: 'none', background: 'transparent',
            color: tab === t.id ? phase.color : 'var(--text4)',
            borderBottom: `2px solid ${tab === t.id ? phase.color : 'transparent'}`,
            transition: 'all 0.15s', whiteSpace: 'nowrap',
          }}>
            {t.label}
          </button>
        ))}
      </div>
    </div>
  );
}
