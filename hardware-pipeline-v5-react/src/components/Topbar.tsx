import React from 'react';
import type { Project, Statuses } from '../types';
import { PHASES } from '../phaseData';

interface Props {
  project: Project | null;
  statuses: Statuses;
  onCreateProject: () => void;
  onGoHome: () => void;
}

export function Topbar({ project, statuses, onCreateProject, onGoHome }: Props) {
  return (
    <header style={{
      position: 'fixed', top: 0, left: 0, right: 0, height: 56, zIndex: 100,
      background: 'rgba(7,11,20,0.97)',
      borderBottom: '1px solid rgba(42,58,80,0.8)',
      display: 'flex', alignItems: 'center', gap: 0,
      backdropFilter: 'blur(12px)',
    }}>
      {/* Logo */}
      <div
        onClick={onGoHome}
        style={{
          display: 'flex', alignItems: 'center', gap: 10,
          padding: '0 20px', minWidth: 200, borderRight: '1px solid rgba(42,58,80,0.6)',
          height: '100%', cursor: 'pointer',
        }}
      >
        <span style={{ color: '#00c6a7', fontSize: 20 }}>&#x26A1;</span>
        <div>
          <div style={{ fontFamily: 'Syne, sans-serif', fontWeight: 700, fontSize: 14, color: '#e2e8f0', letterSpacing: '0.04em' }}>
            Hardware <span style={{ color: '#00c6a7' }}>Pipeline</span>
          </div>
          <div style={{ fontSize: 9, color: '#64748b', letterSpacing: '0.1em', fontFamily: 'DM Mono, monospace' }}>
            AI DESIGN STUDIO
          </div>
        </div>
      </div>

      {/* Phase progress dots - shown when a project is loaded */}
      {project && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 0, padding: '0 16px', flex: 1 }}>
          <div style={{ fontSize: 9, color: '#475569', letterSpacing: '0.1em', fontFamily: 'DM Mono, monospace', marginRight: 14 }}>
            PHASES
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
            {PHASES.map((phase, idx) => {
              const st = statuses[phase.id]?.status || 'pending';
              const dotColor = st === 'completed' ? phase.color
                : st === 'in_progress' ? phase.color
                  : st === 'failed' ? '#dc2626'
                    : '#2a3a50';
              const isRunning = st === 'in_progress';
              return (
                <React.Fragment key={phase.id}>
                  <div
                    title={`P${phase.num} ${phase.name} — ${st}`}
                    style={{
                      width: 10, height: 10, borderRadius: '50%',
                      background: dotColor,
                      opacity: st === 'pending' ? 0.4 : 1,
                      boxShadow: isRunning ? `0 0 8px ${phase.color}` : 'none',
                      transition: 'all 0.3s ease',
                      cursor: 'default',
                    }}
                    className={isRunning ? 'blink' : ''}
                  />
                  {idx < PHASES.length - 1 && (
                    <div style={{
                      width: 12, height: 1,
                      background: st === 'completed' ? 'rgba(255,255,255,0.15)' : 'rgba(42,58,80,0.4)',
                    }} />
                  )}
                </React.Fragment>
              );
            })}
          </div>
          <div style={{
            marginLeft: 14, fontSize: 9, color: '#64748b', fontFamily: 'DM Mono, monospace',
          }}>
            {PHASES.filter(p => statuses[p.id]?.status === 'completed').length}/{PHASES.length}
          </div>
        </div>
      )}

      {!project && (
        <div style={{ flex: 1, padding: '0 20px', fontSize: 10, color: '#475569', letterSpacing: '0.1em', fontFamily: 'DM Mono, monospace' }}>
          DATA PATTERNS INDIA &middot; GREAT AI HACK-A-THON 2026
        </div>
      )}

      {/* Right — project breadcrumb + actions */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '0 16px' }}>
        {project && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: 6,
            background: 'rgba(42,58,80,0.5)', border: '1px solid rgba(42,58,80,0.8)',
            borderRadius: 4, padding: '4px 10px', fontSize: 10,
            fontFamily: 'DM Mono, monospace', color: '#94a3b8',
          }}>
            <span style={{ color: '#00c6a7', fontSize: 8 }}>&#x25CF;</span>
            {project.name}
          </div>
        )}
        <button onClick={onCreateProject} style={{
          background: 'rgba(0,198,167,0.12)', border: '1px solid rgba(0,198,167,0.4)',
          borderRadius: 4, padding: '5px 12px', cursor: 'pointer',
          fontFamily: 'DM Mono, monospace', fontSize: 10, letterSpacing: '0.08em',
          color: '#00c6a7', transition: 'all 0.15s', whiteSpace: 'nowrap',
        }}>
          + CREATE PROJECT
        </button>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 5,
          background: 'rgba(16,185,129,0.1)', border: '1px solid rgba(16,185,129,0.25)',
          borderRadius: 4, padding: '4px 10px', fontSize: 9,
          fontFamily: 'DM Mono, monospace', color: '#10b981', letterSpacing: '0.1em',
        }}>
          <span className="blink" style={{ fontSize: 6 }}>&#x25CF;</span>
          ENGINE ONLINE
        </div>
      </div>
    </header>
  );
}

export default Topbar;
