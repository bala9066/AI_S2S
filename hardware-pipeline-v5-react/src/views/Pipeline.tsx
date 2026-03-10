
import type { Project, Statuses, TabId } from '../types';
import { PHASES } from '../phaseData';
import PhaseCard from '../components/PhaseCard';

interface Props {
  project: Project | null;
  statuses: Statuses;
  setTab: (t: TabId) => void;
  onRunPhase: (p: string) => void;
  onRunAll?: () => void;
}

const PHASE_STEPS = ['REQ', 'HRS', 'COMP', 'NET', 'PCB', 'GLR', 'FPGA', 'CODE'];

export default function Pipeline({ project, statuses, setTab, onRunPhase }: Props) {
  if (!project) {
    return (
      <div style={{ padding: '40px', textAlign: 'center' }}>
        <div style={{ fontFamily: '"DM Mono", monospace', fontSize: '13px', color: 'var(--text3)', marginBottom: '16px' }}>
          No project selected. Create or load a project to view the pipeline.
        </div>
        <button onClick={() => setTab('new')} style={{ padding: '10px 20px', background: 'var(--teal)', border: 'none', borderRadius: '4px', color: '#070b14', fontFamily: '"DM Mono", monospace', fontSize: '11px', fontWeight: 700, cursor: 'pointer' }}>
          + CREATE PROJECT
        </button>
      </div>
    );
  }

  const mainPhases = ['P1','P2','P3','P4'];
  const completedCount = mainPhases.filter(id => statuses[id]?.status === 'completed').length;
  const progress = Math.round((completedCount / 8) * 100);

  return (
    <div style={{ padding: '24px' }} className="fade-up">
      {/* Header */}
      <div style={{ marginBottom: '20px' }}>
        <div style={{ fontFamily: '"Syne", sans-serif', fontSize: '20px', fontWeight: 800, color: 'var(--text)', marginBottom: '4px' }}>
          Pipeline <span style={{ color: 'var(--teal)' }}>Studio</span>
        </div>
        <div style={{ fontFamily: '"DM Mono", monospace', fontSize: '11px', color: 'var(--text3)' }}>{project.name}</div>
      </div>

      {/* Progress Bar */}
      <div style={{ marginBottom: '24px', background: 'var(--panel)', border: '1px solid var(--border)', borderRadius: '6px', padding: '16px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
          <div style={{ display: 'flex', gap: '6px' }}>
            {PHASE_STEPS.map((step, i) => {
              const phaseId = `P${i + 1}`;
              const s = statuses[phaseId]?.status || 'pending';
              const color = s === 'completed' ? 'var(--green)' : s === 'in_progress' ? 'var(--teal)' : s === 'failed' ? 'var(--danger)' : 'var(--text3)';
              return (
                <div key={step} style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <span style={{ fontFamily: '"DM Mono", monospace', fontSize: '9px', color, padding: '3px 6px', background: 'var(--navy)', borderRadius: '2px', border: `1px solid ${color === 'var(--text3)' ? 'var(--border)' : color}` }}>
                    {step}
                  </span>
                  {i < PHASE_STEPS.length - 1 && <span style={{ color: 'var(--border)', fontSize: '10px' }}>→</span>}
                </div>
              );
            })}
          </div>
          <span style={{ fontFamily: '"DM Mono", monospace', fontSize: '11px', color: 'var(--teal)' }}>{progress}%</span>
        </div>
        <div style={{ height: '4px', background: 'var(--panel2)', borderRadius: '2px' }}>
          <div style={{ height: '100%', width: `${progress}%`, background: 'var(--teal)', borderRadius: '2px', boxShadow: '0 0 8px rgba(0,198,167,0.5)', transition: 'width 0.5s ease' }} />
        </div>
      </div>

      {/* Phase Cards */}
      {PHASES.map(phase => (
        <PhaseCard
          key={phase.id}
          phase={phase}
          statuses={statuses}
          onRun={onRunPhase}
          onApprove={onRunPhase}
        />
      ))}
    </div>
  );
}
