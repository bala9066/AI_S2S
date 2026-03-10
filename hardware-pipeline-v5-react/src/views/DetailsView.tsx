import type { PhaseMeta } from '../types';

interface Props { phase: PhaseMeta; }

const SectionLabel = ({ text }: { text: string }) => (
  <div style={{ fontSize: 10, color: 'var(--text4)', letterSpacing: '0.14em', marginBottom: 10, marginTop: 22, borderBottom: '1px solid var(--border2)', paddingBottom: 6 }}>
    {text}
  </div>
);

const BulletList = ({ items, color }: { items: string[]; color: string }) => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
    {items.map((item, i) => (
      <div key={i} style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
        <div style={{ width: 5, height: 5, borderRadius: '50%', background: color, marginTop: 5, flexShrink: 0 }} />
        <div style={{ fontSize: 12, color: 'var(--text2)', lineHeight: 1.5 }}>{item}</div>
      </div>
    ))}
  </div>
);

export default function DetailsView({ phase }: Props) {
  return (
    <div style={{ paddingTop: 20 }}>
      <SectionLabel text="INPUTS" />
      <BulletList items={phase.inputs} color={phase.color} />

      <SectionLabel text="OUTPUTS" />
      <BulletList items={phase.outputs} color={phase.color} />

      <SectionLabel text="TOOLS" />
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
        {phase.tools.map((tool, i) => (
          <span key={i} style={{
            fontSize: 11, padding: '4px 12px', borderRadius: 4,
            background: `${phase.color}10`,
            border: `1px solid ${phase.color}33`,
            color: phase.color,
            fontFamily: "'DM Mono', monospace",
          }}>
            {tool}
          </span>
        ))}
      </div>
    </div>
  );
}
