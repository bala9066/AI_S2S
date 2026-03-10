import { useState } from "react";
import type { Project } from '../types';

interface Props { project: Project | null; }

const MOCK_VIOLATIONS = [
  { rule: 'MISRA-C:2012 Rule 14.4', severity: 'Required', file: 'motor_ctrl.c', line: 47, desc: 'The controlling expression of an if statement shall be essentially Boolean' },
  { rule: 'MISRA-C:2012 Rule 11.3', severity: 'Required', file: 'pwm_driver.c', line: 23, desc: 'A cast shall not be performed between a pointer to object type and a pointer to different object type' },
  { rule: 'MISRA-C:2012 Rule 8.7', severity: 'Advisory', file: 'adc_handler.c', line: 112, desc: 'Functions and objects should not be defined with external linkage if they are referenced in only one translation unit' },
  { rule: 'MISRA-C:2012 Rule 15.5', severity: 'Advisory', file: 'motor_ctrl.c', line: 89, desc: 'A function should have a single point of exit at the end' },
];

const MOCK_DIFF = `@@ -44,8 +44,8 @@ void motor_set_speed(float speed) {
 
 void motor_update_control(void) {
   float error = target_speed - current_speed;
-  if (error > DEADBAND) {          // ⚠ MISRA 14.4: not essentially Boolean
+  if (error > (float)DEADBAND) {   // ✓ Fixed: explicit float comparison
     pid_output = pid_calculate(error);
   }
   
@@ -20,6 +20,6 @@ void pwm_init(void) {
   TIM1->ARR = PWM_PERIOD;
-  uint8_t *ptr = (uint8_t*)&TIM1->CCR1;  // ⚠ MISRA 11.3
+  volatile uint32_t *ptr = &TIM1->CCR1;   // ✓ Fixed: correct pointer type
 }`;

export default function CodeReview({ project }: Props) {
  const [activeFile] = useState("motor_ctrl.c");

  if (!project) {
    return <div style={{ padding: '40px', fontFamily: '"DM Mono", monospace', fontSize: '13px', color: 'var(--text3)', textAlign: 'center' }}>Select a project to view code review.</div>;
  }

  const required = MOCK_VIOLATIONS.filter(v => v.severity === 'Required').length;
  const advisory = MOCK_VIOLATIONS.filter(v => v.severity === 'Advisory').length;

  return (
    <div style={{ padding: '24px' }} className="fade-up">
      <div style={{ marginBottom: '20px' }}>
        <div style={{ fontFamily: '"Syne", sans-serif', fontSize: '18px', fontWeight: 700, color: 'var(--text)' }}>
          Code <span style={{ color: 'var(--teal)' }}>Review</span>
        </div>
        <div style={{ fontFamily: '"DM Mono", monospace', fontSize: '11px', color: 'var(--text3)', marginTop: '2px' }}>
          MISRA-C:2012 + Clang-Tidy Static Analysis
        </div>
      </div>

      {/* Summary */}
      <div style={{ display: 'flex', gap: '12px', marginBottom: '20px' }}>
        {[
          { label: 'REQUIRED', value: required, color: 'var(--danger)' },
          { label: 'ADVISORY', value: advisory, color: 'var(--warning)' },
          { label: 'FILES CHECKED', value: 3, color: 'var(--teal)' },
          { label: 'SCORE', value: '78/100', color: 'var(--blue)' },
        ].map(s => (
          <div key={s.label} style={{ flex: 1, background: 'var(--panel)', border: '1px solid var(--border)', borderRadius: '4px', padding: '10px 14px' }}>
            <div className="section-label" style={{ marginBottom: '4px' }}>{s.label}</div>
            <div style={{ fontFamily: '"Syne", sans-serif', fontSize: '20px', fontWeight: 700, color: s.color }}>{s.value}</div>
          </div>
        ))}
      </div>

      {/* Violations */}
      <div style={{ background: 'var(--panel)', border: '1px solid var(--border)', borderRadius: '6px', marginBottom: '20px', overflow: 'hidden' }}>
        <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', fontFamily: '"DM Mono", monospace', fontSize: '11px', color: 'var(--text2)', display: 'flex', justifyContent: 'space-between' }}>
          <span>MISRA VIOLATIONS</span>
          <span style={{ color: 'var(--text3)' }}>{MOCK_VIOLATIONS.length} total</span>
        </div>
        {MOCK_VIOLATIONS.map((v, i) => (
          <div key={i} style={{ padding: '12px 16px', borderBottom: i < MOCK_VIOLATIONS.length - 1 ? '1px solid var(--border2)' : 'none', display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
            <span style={{ fontFamily: '"DM Mono", monospace', fontSize: '9px', padding: '2px 6px', borderRadius: '2px', background: v.severity === 'Required' ? 'rgba(220,38,38,0.12)' : 'rgba(245,158,11,0.1)', color: v.severity === 'Required' ? 'var(--danger)' : 'var(--warning)', border: `1px solid ${v.severity === 'Required' ? 'rgba(220,38,38,0.3)' : 'rgba(245,158,11,0.3)'}`, flexShrink: 0, marginTop: '1px' }}>
              {v.severity.toUpperCase()}
            </span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontFamily: '"DM Mono", monospace', fontSize: '11px', color: 'var(--teal)', marginBottom: '2px' }}>{v.rule}</div>
              <div style={{ fontFamily: '"DM Mono", monospace', fontSize: '11px', color: 'var(--text2)', lineHeight: 1.5 }}>{v.desc}</div>
            </div>
            <div style={{ fontFamily: '"DM Mono", monospace', fontSize: '10px', color: 'var(--text3)', flexShrink: 0, textAlign: 'right' }}>
              <div>{v.file}</div>
              <div style={{ color: 'var(--text4)' }}>line {v.line}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Diff */}
      <div style={{ background: 'var(--panel)', border: '1px solid var(--border)', borderRadius: '6px', overflow: 'hidden' }}>
        <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', fontFamily: '"DM Mono", monospace', fontSize: '11px', color: 'var(--text2)' }}>
          AI SUGGESTED FIXES — {activeFile}
        </div>
        <div style={{ padding: '16px', overflow: 'auto' }}>
          <pre style={{ fontFamily: '"JetBrains Mono", monospace', fontSize: '12px', lineHeight: 1.7, margin: 0 }}>
            {MOCK_DIFF.split('\n').map((line, i) => {
              const color = line.startsWith('+') ? '#10b981' : line.startsWith('-') ? 'var(--danger)' : line.startsWith('@@') ? 'var(--blue)' : 'var(--text2)';
              const bg = line.startsWith('+') ? 'rgba(16,185,129,0.06)' : line.startsWith('-') ? 'rgba(220,38,38,0.06)' : 'transparent';
              return <span key={i} style={{ display: 'block', color, background: bg }}>{line}</span>;
            })}
          </pre>
        </div>
      </div>
    </div>
  );
}
