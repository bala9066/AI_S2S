import React, { useState, useEffect } from 'react';
import type { Project, Statuses } from '../types';
import { getPhase } from '../phaseData';

interface Props {
  project: Project | null;
  statuses: Statuses;
  activePhase: string;
}

export function RightPanel({ project, statuses, activePhase }: Props) {
  const phase = getPhase(activePhase);
  if (!phase || !project) {
    return (
      <aside style={{
        width: 300, minWidth: 300, height: 'calc(100vh - 56px)',
        background: 'linear-gradient(180deg, #0a0e1a 0%, #070b14 100%)',
        borderLeft: '1px solid rgba(42,58,80,0.8)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 24,
      }}>
        <div style={{ textAlign: 'center', color: '#475569', fontSize: 11 }}>
          Select a project & phase to view execution flow
        </div>
      </aside>
    );
  }

  const st = statuses[phase.id]?.status || 'pending';
  const isRunning = st === 'in_progress';
  const isCompleted = st === 'completed';

  const [currentStepIdx, setCurrentStepIdx] = useState(0);

  useEffect(() => {
    if (!isRunning) {
      if (isCompleted) setCurrentStepIdx(phase.subSteps.length);
      else setCurrentStepIdx(0);
      return;
    }

    // Simulate real-time step progression while phase is running
    const interval = setInterval(() => {
      setCurrentStepIdx(prev => {
        if (prev < phase.subSteps.length - 1) return prev + 1;
        return prev;
      });
    }, 3500); // advance visually every 3.5s

    return () => clearInterval(interval);
  }, [isRunning, isCompleted, phase.id, phase.subSteps.length]);

  return (
    <aside style={{
      width: 300, minWidth: 300, height: 'calc(100vh - 56px)',
      background: 'linear-gradient(180deg, #0a0e1a 0%, #070b14 100%)',
      borderLeft: '1px solid rgba(42,58,80,0.8)',
      display: 'flex', flexDirection: 'column',
      overflow: 'hidden',
    }}>
      {/* Header */}
      <div style={{
        padding: '16px 16px 12px',
        borderBottom: '1px solid rgba(42,58,80,0.6)',
      }}>
        <div style={{ fontSize: 9, color: '#475569', letterSpacing: '0.16em', textTransform: 'uppercase', fontFamily: 'DM Mono, monospace', marginBottom: 6 }}>
          STEP-BY-STEP EXECUTION FLOW
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{
            width: 8, height: 8, borderRadius: '50%',
            background: phase.color,
            boxShadow: isRunning ? `0 0 8px ${phase.color}` : 'none',
          }} className={isRunning ? 'blink' : ''} />
          <div style={{ fontFamily: 'Syne, sans-serif', fontWeight: 600, fontSize: 13, color: phase.color }}>
            P{phase.num} &middot; {phase.name}
          </div>
        </div>
        <div style={{
          marginTop: 6, fontSize: 10, color: '#64748b',
        }}>
          {isRunning ? 'Executing...' : isCompleted ? 'All steps completed' : st === 'failed' ? 'Failed' : 'Pending execution'}
        </div>
      </div>

      {/* Sub-steps flow */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '12px 16px' }}>
        {phase.subSteps.map((step, idx) => {
          // Determine step status based on real-time polling simulation
          let stepStatus: 'done' | 'active' | 'pending' = 'pending';
          if (isCompleted) stepStatus = 'done';
          else if (isRunning) {
            if (idx < currentStepIdx) stepStatus = 'done';
            else if (idx === currentStepIdx) stepStatus = 'active';
            else stepStatus = 'pending';
          }

          const stepColor = stepStatus === 'done' ? phase.color
            : stepStatus === 'active' ? phase.color
              : '#475569';

          return (
            <div key={idx} style={{ display: 'flex', gap: 12, marginBottom: 4 }}>
              {/* Vertical line + dot */}
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', width: 20 }}>
                <div style={{
                  width: 12, height: 12, borderRadius: '50%', flexShrink: 0,
                  background: stepStatus === 'done' ? phase.colorDim : stepStatus === 'active' ? phase.colorDim : 'rgba(42,58,80,0.3)',
                  border: `1px solid ${stepStatus !== 'pending' ? phase.colorBorder : 'rgba(42,58,80,0.5)'}`,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 7, color: stepColor,
                }}>
                  {stepStatus === 'done' ? '\u2713' : stepStatus === 'active' ? '\u25CF' : (idx + 1)}
                </div>
                {idx < phase.subSteps.length - 1 && (
                  <div style={{
                    width: 1, flex: 1, minHeight: 16,
                    background: stepStatus === 'done' ? phase.colorBorder : 'rgba(42,58,80,0.4)',
                  }} />
                )}
              </div>
              {/* Step content */}
              <div style={{ flex: 1, paddingBottom: 12 }}>
                <div style={{
                  fontSize: 11, fontFamily: 'DM Mono, monospace',
                  color: stepStatus === 'pending' ? '#475569' : '#e2e8f0',
                  fontWeight: stepStatus === 'active' ? 600 : 400,
                }}>
                  {step.name}
                </div>
                <div style={{
                  fontSize: 9, color: stepStatus === 'active' ? phase.color : '#3a4d63',
                  marginTop: 2, fontFamily: 'DM Mono, monospace',
                }}>
                  {step.time}
                  {stepStatus === 'active' && <span className="blink" style={{ marginLeft: 6 }}>&#x2588;</span>}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Phase info footer */}
      <div style={{
        padding: '12px 16px',
        borderTop: '1px solid rgba(42,58,80,0.6)',
        fontSize: 9, color: '#475569', fontFamily: 'DM Mono, monospace',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
          <span>TYPE</span>
          <span style={{ color: phase.isAI ? phase.color : '#f59e0b' }}>
            {phase.isAI ? '\uD83E\uDD16 AI-POWERED' : '\uD83D\uDC64 ENGINEER'}
          </span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <span>STEPS</span>
          <span style={{ color: '#94a3b8' }}>{phase.subSteps.length}</span>
        </div>
        {phase.externalTool && (
          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4 }}>
            <span>TOOL</span>
            <span style={{ color: '#f59e0b' }}>{phase.externalTool}</span>
          </div>
        )}
      </div>
    </aside>
  );
}

export default RightPanel;
