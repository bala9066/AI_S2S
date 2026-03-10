import React from 'react';
import type { Project, Statuses } from '../types';
import { PHASES } from '../phaseData';

interface Props {
  project: Project | null;
  statuses: Statuses;
  projects: Project[];
  onOpenProject: (p: Project) => void;
  onCreateProject: () => void;
}

export default function Overview({ project, statuses, projects, onOpenProject, onCreateProject }: Props) {
  return (
    <div className="grid-bg" style={{
      minHeight: '100%', display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center',
      position: 'relative', overflow: 'hidden', padding: '40px 24px',
    }}>
      {/* Animated glowing orbs */}
      <div style={{
        position: 'absolute', top: '15%', left: '20%',
        width: 200, height: 200, borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(0,198,167,0.08) 0%, transparent 70%)',
        filter: 'blur(40px)', pointerEvents: 'none',
      }} className="glow-pulse" />
      <div style={{
        position: 'absolute', bottom: '20%', right: '15%',
        width: 250, height: 250, borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(59,130,246,0.06) 0%, transparent 70%)',
        filter: 'blur(50px)', pointerEvents: 'none',
      }} className="glow-pulse" />
      <div style={{
        position: 'absolute', top: '50%', right: '40%',
        width: 150, height: 150, borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(168,85,247,0.05) 0%, transparent 70%)',
        filter: 'blur(35px)', pointerEvents: 'none',
      }} className="glow-pulse" />

      {/* Hero content */}
      <div style={{ textAlign: 'center', position: 'relative', zIndex: 1 }} className="fade-up">
        {/* Lightning bolt logo */}
        <div style={{
          width: 64, height: 64, borderRadius: 12,
          background: 'rgba(0,198,167,0.1)', border: '1px solid rgba(0,198,167,0.3)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 30, margin: '0 auto 24px',
          boxShadow: '0 0 30px rgba(0,198,167,0.15)',
        }}>
          {'\u26A1'}
        </div>

        {/* Title */}
        <h1 style={{
          fontFamily: 'Syne, sans-serif', fontWeight: 800, fontSize: 42,
          color: '#e2e8f0', letterSpacing: '-0.02em', margin: 0,
          lineHeight: 1.1,
        }}>
          Hardware <span style={{ color: '#00c6a7' }}>Pipeline</span>
        </h1>
        <div style={{
          fontFamily: 'DM Mono, monospace', fontSize: 11,
          letterSpacing: '0.2em', color: '#475569',
          marginTop: 12, textTransform: 'uppercase',
        }}>
          DATA PATTERNS INDIA &middot; GREAT AI HACK-A-THON 2026
        </div>

        {/* Subtitle */}
        <div style={{
          fontFamily: 'DM Mono, monospace', fontSize: 13,
          color: '#64748b', maxWidth: 500, margin: '20px auto 0',
          lineHeight: 1.7,
        }}>
          AI-powered hardware design automation. From natural language requirements
          to production-ready specifications in minutes.
        </div>

        {/* CTA Buttons */}
        <div style={{ display: 'flex', gap: 16, justifyContent: 'center', marginTop: 36 }}>
          <button onClick={onCreateProject} style={{
            padding: '14px 28px', borderRadius: 6,
            background: '#00c6a7', border: '1px solid rgba(0,198,167,0.6)',
            color: '#070b14', fontFamily: 'DM Mono, monospace', fontSize: 12,
            fontWeight: 700, letterSpacing: '0.08em', cursor: 'pointer',
            boxShadow: '0 0 20px rgba(0,198,167,0.2)',
            transition: 'all 0.2s',
          }}>
            + CREATE NEW PROJECT
          </button>
          {projects.length > 0 && (
            <button onClick={() => onOpenProject(projects[projects.length - 1])} style={{
              padding: '14px 28px', borderRadius: 6,
              background: 'none', border: '1px solid rgba(42,58,80,0.8)',
              color: '#94a3b8', fontFamily: 'DM Mono, monospace', fontSize: 12,
              fontWeight: 500, letterSpacing: '0.08em', cursor: 'pointer',
              transition: 'all 0.2s',
            }}>
              LOAD EXISTING
            </button>
          )}
        </div>
      </div>

      {/* Pipeline phases preview bar */}
      <div style={{
        marginTop: 48, display: 'flex', gap: 4,
        alignItems: 'center', position: 'relative', zIndex: 1,
      }} className="fade-up">
        {PHASES.map((phase, i) => (
          <React.Fragment key={phase.id}>
            <div
              title={`P${phase.num} ${phase.name}`}
              style={{
                padding: '6px 12px', borderRadius: 4,
                background: 'rgba(26,34,53,0.6)',
                border: `1px solid ${phase.colorBorder}`,
                fontSize: 9, fontFamily: 'DM Mono, monospace',
                color: phase.color, letterSpacing: '0.06em',
                whiteSpace: 'nowrap', cursor: 'default',
              }}
            >
              P{phase.num}
            </div>
            {i < PHASES.length - 1 && (
              <div style={{ width: 8, height: 1, background: 'rgba(42,58,80,0.5)' }} />
            )}
          </React.Fragment>
        ))}
      </div>

      {/* Existing projects grid */}
      {projects.length > 0 && (
        <div style={{ marginTop: 40, width: '100%', maxWidth: 700, position: 'relative', zIndex: 1 }} className="fade-up">
          <div className="section-label" style={{ marginBottom: 12 }}>RECENT PROJECTS</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 10 }}>
            {projects.slice().reverse().slice(0, 6).map(p => (
              <button key={p.id} onClick={() => onOpenProject(p)} style={{
                padding: '14px 16px', borderRadius: 6, textAlign: 'left',
                background: 'rgba(26,34,53,0.6)', border: '1px solid rgba(42,58,80,0.6)',
                cursor: 'pointer', transition: 'border-color 0.15s',
              }}
                onMouseEnter={e => e.currentTarget.style.borderColor = '#00c6a7'}
                onMouseLeave={e => e.currentTarget.style.borderColor = 'rgba(42,58,80,0.6)'}
              >
                <div style={{ fontFamily: 'Syne, sans-serif', fontWeight: 600, fontSize: 13, color: '#e2e8f0', marginBottom: 4 }}>
                  {p.name}
                </div>
                <div style={{ fontSize: 9, color: '#475569', fontFamily: 'DM Mono, monospace' }}>
                  {p.design_type || 'Hardware'} &middot; #{p.id}
                </div>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
