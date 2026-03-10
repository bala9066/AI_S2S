import type { PhaseMeta } from '../types';

interface Props { phase: PhaseMeta; }

const MetricCard = ({ label, value, color }: { label: string; value: string; color: string }) => (
  <div style={{
    background: `${color}08`, border: `1px solid ${color}22`,
    borderRadius: 8, padding: '18px 20px', flex: 1, minWidth: 140,
  }}>
    <div style={{ fontSize: 10, color: 'var(--text4)', letterSpacing: '0.12em', marginBottom: 10 }}>{label}</div>
    <div style={{ fontFamily: "'Syne', sans-serif", fontSize: 18, fontWeight: 800, color, lineHeight: 1.2 }}>{value}</div>
  </div>
);

export default function MetricsView({ phase }: Props) {
  const m = phase.metrics;
  return (
    <div style={{ paddingTop: 20 }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
        <MetricCard label="TIME SAVED" value={m.timeSaved} color={phase.color} />
        <MetricCard label="ERROR REDUCTION" value={m.errorReduction} color={phase.color} />
        <MetricCard label="CONFIDENCE" value={m.confidence} color={phase.color} />
        <MetricCard label="ANNUAL COST IMPACT" value={m.costImpact} color={phase.color} />
      </div>
    </div>
  );
}
