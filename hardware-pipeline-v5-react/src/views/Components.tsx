
import type { Project } from '../types';

interface Props { project: Project | null; }

const MOCK_COMPONENTS = [
  { part: 'STM32H743VIT6', desc: 'ARM Cortex-M7 MCU, 480MHz', manuf: 'STMicroelectronics', pkg: 'LQFP-100', qty: 1, conf: 94, status: 'Recommended', grade: 'Industrial' },
  { part: 'TI DRV8305', desc: 'Three-Phase Gate Driver', manuf: 'Texas Instruments', pkg: 'HTSSOP-32', qty: 1, conf: 91, status: 'Recommended', grade: 'Automotive' },
  { part: 'INA240A1', desc: 'Current Sense Amplifier', manuf: 'Texas Instruments', pkg: 'SOT-23-5', qty: 3, conf: 88, status: 'Alternative', grade: 'Commercial' },
  { part: 'CSD19536KTT', desc: 'N-Channel MOSFET, 60V 100A', manuf: 'Texas Instruments', pkg: 'TO-220', qty: 6, conf: 92, status: 'Recommended', grade: 'Industrial' },
  { part: 'TPS54340', desc: 'Buck Converter 3.5A', manuf: 'Texas Instruments', pkg: 'HVSSOP-14', qty: 2, conf: 85, status: 'Recommended', grade: 'Commercial' },
  { part: 'ADC128S102', desc: '12-bit, 8-ch SPI ADC', manuf: 'Texas Instruments', pkg: 'TSSOP-16', qty: 1, conf: 87, status: 'Alternative', grade: 'Industrial' },
];

const gradeColor: Record<string, string> = {
  'Automotive': 'rgba(59,130,246,0.15)',
  'Industrial': 'rgba(0,198,167,0.12)',
  'Commercial': 'rgba(100,116,139,0.12)',
};
const gradeText: Record<string, string> = {
  'Automotive': 'var(--blue)',
  'Industrial': 'var(--teal)',
  'Commercial': 'var(--text3)',
};

export default function Components({ project }: Props) {
  if (!project) {
    return <div style={{ padding: '40px', fontFamily: '"DM Mono", monospace', fontSize: '13px', color: 'var(--text3)', textAlign: 'center' }}>Select a project to view components.</div>;
  }

  return (
    <div style={{ padding: '24px' }} className="fade-up">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <div>
          <div style={{ fontFamily: '"Syne", sans-serif', fontSize: '18px', fontWeight: 700, color: 'var(--text)' }}>
            Component <span style={{ color: 'var(--teal)' }}>BOM</span>
          </div>
          <div style={{ fontFamily: '"DM Mono", monospace', fontSize: '11px', color: 'var(--text3)', marginTop: '2px' }}>
            Selected Components · Top AI Matches
          </div>
        </div>
        <div style={{ fontFamily: '"DM Mono", monospace', fontSize: '11px', color: 'var(--teal)' }}>
          View all {MOCK_COMPONENTS.length} →
        </div>
      </div>

      <div style={{ background: 'var(--panel)', border: '1px solid var(--border)', borderRadius: '6px', overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--border)' }}>
              {['Part Number', 'Description', 'Manufacturer', 'Package', 'Qty', 'Grade', 'Confidence', 'Status'].map(h => (
                <th key={h} style={{ padding: '10px 14px', textAlign: 'left', fontFamily: '"DM Mono", monospace', fontSize: '9px', letterSpacing: '0.15em', textTransform: 'uppercase', color: 'var(--text3)', fontWeight: 500, background: 'var(--panel3)' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {MOCK_COMPONENTS.map((c, i) => (
              <tr key={i} style={{ borderBottom: '1px solid var(--border2)', transition: 'background 0.1s' }}
                onMouseEnter={e => (e.currentTarget.style.background = 'rgba(42,58,80,0.4)')}
                onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}>
                <td style={{ padding: '12px 14px', fontFamily: '"DM Mono", monospace', fontSize: '12px', color: 'var(--teal)', fontWeight: 500 }}>{c.part}</td>
                <td style={{ padding: '12px 14px', fontFamily: '"DM Mono", monospace', fontSize: '11px', color: 'var(--text2)' }}>{c.desc}</td>
                <td style={{ padding: '12px 14px', fontFamily: '"DM Mono", monospace', fontSize: '11px', color: 'var(--text3)' }}>{c.manuf}</td>
                <td style={{ padding: '12px 14px', fontFamily: '"DM Mono", monospace', fontSize: '11px', color: 'var(--text3)' }}>{c.pkg}</td>
                <td style={{ padding: '12px 14px', fontFamily: '"DM Mono", monospace', fontSize: '11px', color: 'var(--text)', textAlign: 'center' }}>{c.qty}</td>
                <td style={{ padding: '12px 14px' }}>
                  <span style={{ fontFamily: '"DM Mono", monospace', fontSize: '9px', padding: '2px 7px', borderRadius: '2px', background: gradeColor[c.grade], color: gradeText[c.grade], border: `1px solid ${gradeText[c.grade]}`, opacity: 0.9 }}>{c.grade}</span>
                </td>
                <td style={{ padding: '12px 14px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <div style={{ flex: 1, height: '4px', background: 'var(--panel2)', borderRadius: '2px' }}>
                      <div style={{ height: '100%', width: `${c.conf}%`, background: c.conf >= 90 ? 'var(--green)' : c.conf >= 80 ? 'var(--teal)' : 'var(--warning)', borderRadius: '2px' }} />
                    </div>
                    <span style={{ fontFamily: '"DM Mono", monospace', fontSize: '10px', color: 'var(--text2)', minWidth: '30px' }}>{c.conf}%</span>
                  </div>
                </td>
                <td style={{ padding: '12px 14px' }}>
                  <span className={`badge ${c.status === 'Recommended' ? 'badge-done' : 'badge-manual'}`}>{c.status}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
