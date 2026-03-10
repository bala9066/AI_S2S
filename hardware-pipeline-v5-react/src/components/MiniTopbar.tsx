import type { Project, Statuses, PhaseMeta } from '../types';

interface Props {
  project: Project | null;
  phases: PhaseMeta[];
  statuses: Statuses;
}

export default function MiniTopbar({ project, phases, statuses }: Props) {
  const completedCount = phases.filter(p => statuses[p.id] === 'completed').length;

  return (
    <div style={{
      padding: '9px 26px', borderBottom: '1px solid var(--border2)',
      display: 'flex', alignItems: 'center', gap: 10,
      background: 'var(--navy)', position: 'sticky', top: 0, zIndex: 5,
    }}>
      <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)' }}>
        {project?.name || 'No project'}
      </span>
      {project?.design_type && (
        <span style={{
          fontSize: 11, color: 'var(--teal)', background: '#0a2a20',
          border: '1px solid #0d4035', padding: '2px 8px', borderRadius: 3,
          fontFamily: "'DM Mono', monospace",
        }}>
          {project.design_type.toUpperCase()}
        </span>
      )}

      <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 10 }}>
        <span style={{ fontSize: 11, color: 'var(--text4)' }}>
          {completedCount} / {phases.length}
        </span>
        <div style={{ display: 'flex', gap: 3 }}>
          {phases.map(p => (
            <div key={p.id} title={p.code} style={{
              width: 16, height: 4, borderRadius: 2,
              background: statuses[p.id] === 'completed' ? p.color
                : statuses[p.id] === 'in_progress' ? p.color + '88'
                : 'var(--panel2)',
              transition: 'background 0.3s',
            }} />
          ))}
        </div>
      </div>
    </div>
  );
}
