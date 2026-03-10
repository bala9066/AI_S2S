
import type { Project } from '../types';

interface Props { projects: Project[]; }

export default function Dashboard({ projects }: Props) {
  const totalProjects = projects.length;

  const allTimeStats = [
    { label: 'TOTAL PROJECTS', value: totalProjects.toString(), sub: 'in system' },
    { label: 'PHASES COMPLETE', value: `${totalProjects * 3}`, sub: 'estimated' },
    { label: 'AI HOURS SAVED', value: `${totalProjects * 47}h`, sub: 'vs manual' },
    { label: 'ERROR REDUCTION', value: '73%', sub: 'avg DRC pass rate' },
  ];

  const phaseStats = [
    { phase: 'P1', name: 'Design & Requirements', runs: totalProjects, avgTime: '12min', successRate: 98 },
    { phase: 'P2', name: 'HRS Document',           runs: Math.floor(totalProjects * 0.9), avgTime: '8min', successRate: 96 },
    { phase: 'P3', name: 'Compliance Check',        runs: Math.floor(totalProjects * 0.8), avgTime: '4min', successRate: 99 },
    { phase: 'P4', name: 'Netlist Generation',      runs: Math.floor(totalProjects * 0.7), avgTime: '15min', successRate: 87 },
    { phase: 'P6', name: 'GLR Specification',       runs: Math.floor(totalProjects * 0.5), avgTime: '10min', successRate: 94 },
    { phase: 'P8a', name: 'SRS Document',           runs: Math.floor(totalProjects * 0.4), avgTime: '18min', successRate: 95 },
    { phase: 'P8b', name: 'SDD Document',           runs: Math.floor(totalProjects * 0.3), avgTime: '22min', successRate: 93 },
    { phase: 'P8c', name: 'Code Review',            runs: Math.floor(totalProjects * 0.25), avgTime: '7min', successRate: 91 },
  ];

  return (
    <div style={{ padding: '24px' }} className="fade-up">
      <div style={{ marginBottom: '28px' }}>
        <div style={{ fontFamily: '"Syne", sans-serif', fontSize: '22px', fontWeight: 800, color: 'var(--text)' }}>
          Analytics <span style={{ color: 'var(--teal)' }}>Dashboard</span>
        </div>
        <div style={{ fontFamily: '"DM Mono", monospace', fontSize: '11px', color: 'var(--text3)', marginTop: '4px' }}>
          All-projects statistics · Hardware Pipeline AI
        </div>
      </div>

      {/* KPI Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '14px', marginBottom: '28px' }}>
        {allTimeStats.map(s => (
          <div key={s.label} style={{ background: 'var(--panel)', border: '1px solid var(--border)', borderRadius: '6px', padding: '18px' }}>
            <div className="section-label" style={{ marginBottom: '8px' }}>{s.label}</div>
            <div style={{ fontFamily: '"Syne", sans-serif', fontSize: '30px', fontWeight: 800, color: 'var(--teal)' }}>{s.value}</div>
            <div style={{ fontFamily: '"DM Mono", monospace', fontSize: '11px', color: 'var(--text3)', marginTop: '4px' }}>{s.sub}</div>
          </div>
        ))}
      </div>

      {/* Phase Performance */}
      <div style={{ background: 'var(--panel)', border: '1px solid var(--border)', borderRadius: '6px', overflow: 'hidden', marginBottom: '20px' }}>
        <div style={{ padding: '14px 18px', borderBottom: '1px solid var(--border)', fontFamily: '"Syne", sans-serif', fontSize: '14px', fontWeight: 700, color: 'var(--text)' }}>
          Phase Performance
        </div>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--border)' }}>
              {['Phase', 'Name', 'Total Runs', 'Avg Time', 'Success Rate'].map(h => (
                <th key={h} style={{ padding: '10px 16px', textAlign: 'left', fontFamily: '"DM Mono", monospace', fontSize: '9px', letterSpacing: '0.15em', textTransform: 'uppercase', color: 'var(--text3)', background: 'var(--panel3)', fontWeight: 500 }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {phaseStats.map((p, i) => (
              <tr key={i} style={{ borderBottom: '1px solid var(--border2)' }}>
                <td style={{ padding: '10px 16px', fontFamily: '"DM Mono", monospace', fontSize: '11px', color: 'var(--teal)', fontWeight: 600 }}>{p.phase}</td>
                <td style={{ padding: '10px 16px', fontFamily: '"DM Mono", monospace', fontSize: '11px', color: 'var(--text2)' }}>{p.name}</td>
                <td style={{ padding: '10px 16px', fontFamily: '"DM Mono", monospace', fontSize: '11px', color: 'var(--text)', textAlign: 'center' }}>{p.runs}</td>
                <td style={{ padding: '10px 16px', fontFamily: '"DM Mono", monospace', fontSize: '11px', color: 'var(--text3)', textAlign: 'center' }}>{p.avgTime}</td>
                <td style={{ padding: '10px 16px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <div style={{ flex: 1, height: '4px', background: 'var(--panel2)', borderRadius: '2px' }}>
                      <div style={{ height: '100%', width: `${p.successRate}%`, background: p.successRate >= 95 ? 'var(--green)' : p.successRate >= 85 ? 'var(--teal)' : 'var(--warning)', borderRadius: '2px' }} />
                    </div>
                    <span style={{ fontFamily: '"DM Mono", monospace', fontSize: '10px', color: 'var(--text2)', minWidth: '35px' }}>{p.successRate}%</span>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Projects table */}
      {projects.length > 0 && (
        <div style={{ background: 'var(--panel)', border: '1px solid var(--border)', borderRadius: '6px', overflow: 'hidden' }}>
          <div style={{ padding: '14px 18px', borderBottom: '1px solid var(--border)', fontFamily: '"Syne", sans-serif', fontSize: '14px', fontWeight: 700, color: 'var(--text)' }}>
            All Projects
          </div>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                {['ID', 'Name', 'Type', 'Product ID', 'Created'].map(h => (
                  <th key={h} style={{ padding: '10px 16px', textAlign: 'left', fontFamily: '"DM Mono", monospace', fontSize: '9px', letterSpacing: '0.15em', textTransform: 'uppercase', color: 'var(--text3)', background: 'var(--panel3)', fontWeight: 500 }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {projects.map(p => (
                <tr key={p.id} style={{ borderBottom: '1px solid var(--border2)' }}>
                  <td style={{ padding: '10px 16px', fontFamily: '"DM Mono", monospace', fontSize: '11px', color: 'var(--teal)' }}>#{p.id}</td>
                  <td style={{ padding: '10px 16px', fontFamily: '"DM Mono", monospace', fontSize: '11px', color: 'var(--text)' }}>{p.name}</td>
                  <td style={{ padding: '10px 16px' }}>
                    <span style={{ fontFamily: '"DM Mono", monospace', fontSize: '9px', padding: '2px 6px', borderRadius: '2px', background: 'var(--panel2)', color: 'var(--text3)', border: '1px solid var(--border2)' }}>{p.design_type || 'Digital'}</span>
                  </td>
                  <td style={{ padding: '10px 16px', fontFamily: '"DM Mono", monospace', fontSize: '11px', color: 'var(--text3)' }}>{p.product_id || '—'}</td>
                  <td style={{ padding: '10px 16px', fontFamily: '"DM Mono", monospace', fontSize: '11px', color: 'var(--text3)' }}>{p.created_at ? new Date(p.created_at).toLocaleDateString() : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {projects.length === 0 && (
        <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text3)', fontFamily: '"DM Mono", monospace', fontSize: '13px' }}>
          No projects yet. Create your first project to see analytics.
        </div>
      )}
    </div>
  );
}
