import { useState, useEffect, useRef } from 'react';
import type { PhaseMeta, PhaseStatusValue } from '../types';

interface Props {
  phase: PhaseMeta;
  status: PhaseStatusValue;
  onRun: () => void;
  onStatusChange: () => void;
}

export default function FlowPanel({ phase, status, onRun, onStatusChange }: Props) {
  const [activeStep, setActiveStep] = useState(0);     // how many steps completed in animation
  const [progresses, setProgresses] = useState<number[]>([]);
  const [animating, setAnimating] = useState(false);
  const [done, setDone] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Reset when phase changes
  useEffect(() => {
    setActiveStep(0);
    setProgresses([]);
    setAnimating(false);
    setDone(false);
  }, [phase.id]);

  // Auto-animate when status becomes in_progress
  useEffect(() => {
    if (status === 'in_progress' && !animating && !done) {
      startAnimation();
    }
    if (status === 'completed' && !done) {
      setActiveStep(phase.subSteps.length);
      setProgresses(phase.subSteps.map(() => 100));
      setDone(true);
      setAnimating(false);
      onStatusChange();
    }
  }, [status]);

  const startAnimation = () => {
    if (animating) return;
    setAnimating(true);
    setDone(false);
    setActiveStep(0);
    setProgresses(phase.subSteps.map(() => 0));

    let step = 0;
    const runStep = () => {
      if (step >= phase.subSteps.length) {
        setDone(true);
        setAnimating(false);
        onStatusChange();
        return;
      }
      setActiveStep(step + 1);
      let pct = 0;
      if (timerRef.current) clearInterval(timerRef.current);
      timerRef.current = setInterval(() => {
        pct += 5;
        setProgresses(prev => {
          const next = [...prev];
          next[step] = Math.min(pct, 100);
          return next;
        });
        if (pct >= 100) {
          if (timerRef.current) clearInterval(timerRef.current);
          step++;
          setTimeout(runStep, 180);
        }
      }, 22);
    };
    runStep();
  };

  const handleRun = () => {
    if (phase.manual) return;
    onRun();
    startAnimation();
  };

  const isRunning = animating;
  const isComplete = done || status === 'completed';

  return (
    <div style={{
      width: 340, background: 'var(--panel)', borderLeft: '1px solid var(--border2)',
      display: 'flex', flexDirection: 'column', flexShrink: 0,
      height: '100vh', position: 'sticky', top: 0, overflowY: 'auto',
    }}>
      <div style={{ padding: '18px 20px' }}>
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
          <div>
            <div style={{ fontFamily: "'Syne', sans-serif", fontSize: 14, fontWeight: 800, marginBottom: 3, color: 'var(--text)' }}>
              Step-by-Step Execution Flow
            </div>
            <div style={{ fontSize: 11, color: 'var(--text4)' }}>
              {phase.subSteps.length} sub-steps &middot; {phase.time}
            </div>
          </div>

          {!phase.manual && (
            <button
              onClick={isRunning ? undefined : done ? () => { setDone(false); handleRun(); } : handleRun}
              disabled={isRunning}
              style={{
                background: isRunning ? 'var(--panel2)' : phase.color,
                color: isRunning ? 'var(--text4)' : 'var(--navy)',
                border: 'none', borderRadius: 5,
                padding: '8px 16px', fontSize: 11,
                fontFamily: "'DM Mono', monospace", fontWeight: 500,
                cursor: isRunning ? 'default' : 'pointer',
                transition: 'all 0.2s', flexShrink: 0,
                boxShadow: isRunning ? 'none' : `0 0 14px ${phase.color}44`,
              }}
            >
              {isRunning ? 'Running...' : isComplete ? 'Replay' : 'Run'}
            </button>
          )}
        </div>

        {/* Sub-steps */}
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          {phase.subSteps.map((step, i) => {
            const stepDone = i < activeStep;
            const stepActive = i === activeStep - 1 && isRunning;
            const pct = progresses[i] ?? 0;

            return (
              <div key={i} style={{
                display: 'flex', gap: 12, alignItems: 'flex-start',
                opacity: stepDone ? 1 : 0.22,
                transition: 'opacity 0.35s',
              }}>
                {/* Circle + connector */}
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', flexShrink: 0 }}>
                  <div style={{
                    width: 28, height: 28, borderRadius: '50%',
                    background: stepDone ? (stepActive ? `${phase.color}33` : `${phase.color}1a`) : '#141c2a',
                    border: `2px solid ${stepDone ? phase.color : 'var(--panel3)'}`,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontFamily: "'Syne', sans-serif", fontSize: 11, fontWeight: 800,
                    color: stepDone ? phase.color : 'var(--panel3)',
                    transition: 'all 0.3s',
                    boxShadow: stepActive ? `0 0 14px ${phase.color}55` : 'none',
                  }}>
                    {stepDone && !stepActive ? '✓' : i + 1}
                  </div>
                  {i < phase.subSteps.length - 1 && (
                    <div style={{
                      width: 2, height: 24, margin: '3px 0',
                      background: stepDone ? `${phase.color}44` : 'var(--panel2)',
                      transition: 'background 0.4s',
                    }} />
                  )}
                </div>

                {/* Content */}
                <div style={{ flex: 1, paddingBottom: 10 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                    <div style={{ fontSize: 12, fontWeight: 500, color: stepDone ? 'var(--text)' : 'var(--panel3)' }}>
                      {step.label}
                    </div>
                    <span style={{
                      fontSize: 10, flexShrink: 0, marginLeft: 6,
                      color: stepDone ? phase.color : 'var(--panel3)',
                      background: stepDone ? `${phase.color}15` : '#141c2a',
                      padding: '2px 7px', borderRadius: 3,
                      fontFamily: "'DM Mono', monospace",
                    }}>
                      {step.time}
                    </span>
                  </div>

                  {stepDone && (
                    <>
                      <div style={{ fontSize: 11, color: 'var(--text3)', marginBottom: 6, lineHeight: 1.5 }}>
                        {step.detail}
                      </div>
                      {/* Progress bar */}
                      <div style={{
                        height: 3, background: `${phase.color}22`,
                        borderRadius: 2, overflow: 'hidden',
                      }}>
                        <div style={{
                          height: '100%', width: `${pct}%`,
                          background: phase.color,
                          borderRadius: 2,
                          boxShadow: stepActive ? `0 0 8px ${phase.color}` : 'none',
                          transition: 'width 0.1s linear',
                        }} />
                      </div>
                    </>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* Completion summary */}
        {isComplete && (
          <div style={{
            marginTop: 14, padding: '14px 16px',
            background: `${phase.color}0d`,
            border: `1px solid ${phase.color}33`,
            borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          }}>
            <div style={{ display: 'flex', gap: 24 }}>
              <div>
                <div style={{ fontSize: 10, color: 'var(--text4)', marginBottom: 2 }}>TOTAL TIME</div>
                <div style={{ fontFamily: "'Syne', sans-serif", fontSize: 16, fontWeight: 800, color: phase.color }}>
                  {phase.time}
                </div>
              </div>
              <div>
                <div style={{ fontSize: 10, color: 'var(--text4)', marginBottom: 2 }}>SUB-STEPS</div>
                <div style={{ fontFamily: "'Syne', sans-serif", fontSize: 16, fontWeight: 800, color: phase.color }}>
                  {phase.subSteps.length}
                </div>
              </div>
            </div>
            {phase.auto && (
              <div style={{
                fontSize: 11, color: phase.color,
                background: `${phase.color}15`, border: `1px solid ${phase.color}44`,
                padding: '5px 12px', borderRadius: 5, fontFamily: "'DM Mono', monospace",
              }}>
                AUTO-COMPLETE
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
