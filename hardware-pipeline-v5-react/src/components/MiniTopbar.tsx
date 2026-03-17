import type { Project, Statuses, PhaseMeta } from '../types';

interface Props {
  project: Project | null;
  phases: PhaseMeta[];
  statuses: Statuses;
  stalePhaseIds?: string[];
  onRunPipeline?: () => void;
  onRerunStale?: (staleIds: string[]) => void;
  pipelineRunning?: boolean;
}

export default function MiniTopbar({ project, phases, statuses, stalePhaseIds = [], onRunPipeline, onRerunStale, pipelineRunning }: Props) {
  const completedCount = phases.filter(p => statuses[p.id] === 'completed').length;
  const runningPhase = phases.find(p => statuses[p.id] === 'in_progress');
  const pct = Math.round((completedCount / phases.length) * 100);
  const p1Done = statuses['P1'] === 'completed';
  const allDone = completedCount === phases.length;
  // Only show Run Pipeline when pipeline has already been started (P2+ has activity)
  // but is currently stopped — this is the recovery/restart case.
  // Hidden during initial Approve flow (user uses the Approve button in chat instead).
  const p2PlusActive = phases.filter(p => p.id !== 'P1').some(p =>
    ['completed', 'in_progress', 'failed'].includes(statuses[p.id] || ''));
  const showRunBtn = onRunPipeline && p1Done && !pipelineRunning && !allDone && p2PlusActive;

  return (
    <div style={{
      padding: '0 24px', borderBottom: '1px solid #1e2d40',
      background: '#080c17', position: 'sticky', top: 0, zIndex: 5,
      minHeight: 52, display: 'flex', alignItems: 'center', gap: 12,
    }}>
      {/* Project name + type */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
        <span style={{
          fontSize: 14, fontWeight: 600, color: 'var(--text)',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          maxWidth: 240,
        }}>
          {project?.name || 'No project'}
        </span>
        {project?.design_type && (
          <span style={{
            fontSize: 10, color: 'var(--teal)', background: 'rgba(0,198,167,0.08)',
            border: '1px solid rgba(0,198,167,0.25)', padding: '2px 8px', borderRadius: 3,
            fontFamily: "'DM Mono', monospace", letterSpacing: '0.06em', flexShrink: 0,
          }}>
            {project.design_type.toUpperCase()}
          </span>
        )}
      </div>

      {/* Run Pipeline button — shown when P1 done but pipeline not yet running */}
      {showRunBtn && (
        <button
          onClick={onRunPipeline}
          style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '5px 14px', borderRadius: 5,
            background: 'rgba(0,198,167,0.12)',
            border: '1px solid rgba(0,198,167,0.4)',
            color: '#00c6a7', fontSize: 11,
            fontFamily: "'DM Mono', monospace", fontWeight: 700,
            cursor: 'pointer', letterSpacing: '0.05em',
            transition: 'all 0.2s', flexShrink: 0,
          }}
          onMouseEnter={e => { e.currentTarget.style.background = 'rgba(0,198,167,0.22)'; e.currentTarget.style.boxShadow = '0 0 12px rgba(0,198,167,0.3)'; }}
          onMouseLeave={e => { e.currentTarget.style.background = 'rgba(0,198,167,0.12)'; e.currentTarget.style.boxShadow = 'none'; }}
        >
          ▶ Run Pipeline
        </button>
      )}

      {/* Re-run stale phases button — amber, shown when requirements changed after some phases ran */}
      {onRerunStale && stalePhaseIds.length > 0 && !pipelineRunning && (
        <button
          onClick={() => onRerunStale(stalePhaseIds)}
          title={`Re-run ${stalePhaseIds.join(', ')} — requirements updated since these ran`}
          style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '5px 14px', borderRadius: 5,
            background: 'rgba(245,158,11,0.1)',
            border: '1px solid rgba(245,158,11,0.38)',
            color: '#f59e0b', fontSize: 11,
            fontFamily: "'DM Mono', monospace", fontWeight: 700,
            cursor: 'pointer', letterSpacing: '0.05em',
            transition: 'all 0.2s', flexShrink: 0,
          }}
          onMouseEnter={e => { e.currentTarget.style.background = 'rgba(245,158,11,0.2)'; e.currentTarget.style.boxShadow = '0 0 12px rgba(245,158,11,0.25)'; }}
          onMouseLeave={e => { e.currentTarget.style.background = 'rgba(245,158,11,0.1)'; e.currentTarget.style.boxShadow = 'none'; }}
        >
          ↺ Re-run {stalePhaseIds.length} stale
        </button>
      )}

      {/* Running indicator */}
      {runningPhase && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
          <div style={{
            width: 7, height: 7, borderRadius: '50%',
            background: runningPhase.color,
            boxShadow: `0 0 8px ${runningPhase.color}`,
            animation: 'pulse 1.5s ease infinite',
          }} />
          <span style={{ fontSize: 11, color: runningPhase.color, fontFamily: "'DM Mono', monospace", letterSpacing: '0.04em' }}>
            {runningPhase.code} running
          </span>
        </div>
      )}

      {/* Spacer */}
      <div style={{ flex: 1 }} />

      {/* Phase progress pills */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <span style={{ fontSize: 10, color: 'var(--text4)', fontFamily: "'DM Mono', monospace", marginRight: 4 }}>
          {pct}%
        </span>
        <div style={{ display: 'flex', gap: 2.5 }}>
          {phases.map(p => {
            const s = statuses[p.id];
            const isDone = s === 'completed';
            const isRunning = s === 'in_progress';
            return (
              <div
                key={p.id}
                title={`${p.code} — ${p.name}: ${s || 'pending'}`}
                style={{
                  width: 20, height: 6, borderRadius: 3,
                  background: isDone
                    ? p.color
                    : isRunning
                    ? p.color + '77'
                    : '#1e2d40',
                  transition: 'background 0.4s',
                  boxShadow: isRunning ? `0 0 6px ${p.color}55` : 'none',
                  position: 'relative',
                  overflow: isRunning ? 'hidden' : 'visible',
                }}
              >
                {isRunning && (
                  <div style={{
                    position: 'absolute', inset: 0, borderRadius: 3,
                    background: `linear-gradient(90deg, transparent, ${p.color}cc, transparent)`,
                    animation: 'shimmer 1.5s linear infinite',
                  }} />
                )}
              </div>
            );
          })}
        </div>
        <span style={{ fontSize: 10, color: 'var(--text4)', fontFamily: "'DM Mono', monospace", marginLeft: 4 }}>
          {completedCount}/{phases.length}
        </span>
      </div>
    </div>
  );
}
