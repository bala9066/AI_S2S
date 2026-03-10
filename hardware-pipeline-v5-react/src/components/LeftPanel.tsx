import type { PhaseMeta, Statuses } from '../types';
import { isUnlocked } from '../data/phases';

interface Props {
  phases: PhaseMeta[];
  selectedIdx: number;
  statuses: Statuses;
  completedIds: string[];
  onSelect: (idx: number) => void;
  onLanding: () => void;
}

export default function LeftPanel({ phases, selectedIdx, statuses, completedIds, onSelect, onLanding }: Props) {
  return (
    <div style={{
      width: 248, background: 'var(--navy)', borderRight: '1px solid var(--border2)',
      display: 'flex', flexDirection: 'column', flexShrink: 0,
      height: '100vh', position: 'sticky', top: 0,
    }}>
      {/* Logo */}
      <div style={{ padding: '17px 16px 13px', borderBottom: '1px solid var(--border2)' }}>
        <button onClick={onLanding} style={{
          background: 'transparent', border: 'none', cursor: 'pointer',
          textAlign: 'left', width: '100%', padding: 0,
        }}>
          <div style={{ fontSize: 10, color: 'var(--teal)', letterSpacing: '0.14em', marginBottom: 4 }}>
            DATA PATTERNS &middot; CODE KNIGHTS
          </div>
          <div style={{ fontFamily: "'Syne', sans-serif", fontSize: 16, fontWeight: 800, color: 'var(--text)' }}>
            Hardware <span style={{ color: 'var(--teal)' }}>Pipeline</span>
          </div>
        </button>
      </div>

      {/* Phase list */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '8px 6px' }}>
        {phases.map((phase, idx) => {
          const isActive = idx === selectedIdx;
          const isComplete = completedIds.includes(phase.id);
          const unlocked = isUnlocked(phase, completedIds);
          const isLocked = !phase.manual && !unlocked && phase.id !== 'P1';
          const status = statuses[phase.id] || 'pending';
          const isRunning = status === 'in_progress';

          return (
            <button
              key={phase.id}
              onClick={() => onSelect(idx)}
              style={{
                width: '100%',
                background: isActive ? `${phase.color}10` : 'transparent',
                border: `1px solid ${isActive ? phase.color + '44' : 'transparent'}`,
                borderRadius: 7, padding: '9px 11px',
                cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 10,
                marginBottom: 2, transition: 'all 0.15s', textAlign: 'left',
                opacity: isLocked ? 0.32 : 1,
              }}
            >
              {/* Circle icon */}
              <div style={{
                width: 28, height: 28, borderRadius: '50%', flexShrink: 0,
                background: isActive ? `${phase.color}20` : isComplete ? `${phase.color}12` : '#111827',
                border: `2px solid ${isActive ? phase.color : isComplete ? phase.color + '88' : phase.manual ? 'var(--panel3)' : isLocked ? 'var(--panel2)' : phase.color + '44'}`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontFamily: "'Syne', sans-serif", fontSize: 12, fontWeight: 800,
                color: isActive ? phase.color : isComplete ? phase.color + 'cc' : phase.manual ? 'var(--text4)' : isLocked ? 'var(--panel2)' : phase.color + '88',
                transition: 'all 0.2s',
                position: 'relative',
              }}>
                {isRunning ? (
                  <div style={{
                    width: 10, height: 10, borderRadius: '50%',
                    border: `2px solid ${phase.color}`,
                    borderTopColor: 'transparent',
                    animation: 'spin 0.8s linear infinite',
                  }} />
                ) : isComplete && !phase.manual ? '✓' : phase.manual ? '🔒' : phase.num}
              </div>

              {/* Label */}
              <div style={{ flex: 1, overflow: 'hidden' }}>
                <div style={{
                  fontSize: 11, color: isActive ? 'var(--text)' : isComplete ? 'var(--text2)' : isLocked ? '#1e2a3a' : 'var(--text3)',
                  fontWeight: isActive ? 600 : 400,
                  whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                  transition: 'color 0.2s',
                }}>
                  {phase.name}
                </div>
                <div style={{
                  fontSize: 10, marginTop: 2,
                  color: phase.manual ? 'var(--panel3)' : (isActive || isComplete) ? phase.color + '88' : isLocked ? 'var(--panel2)' : phase.color + '44',
                }}>
                  {phase.manual ? 'MANUAL' : isRunning ? 'Running...' : isComplete ? 'COMPLETE' : '⚡ AUTO'}
                </div>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
