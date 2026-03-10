import { useState } from "react";
import type { Project, Statuses, TabId } from '../types';

interface Props { project: Project | null; statuses: Statuses; setTab: (t: TabId) => void; }

const MOCK_NETLIST = {
  nodes: [
    { id: 'MCU1', type: 'MCU', part: 'STM32H743', pins: 100 },
    { id: 'DRV1', type: 'GATE_DRIVER', part: 'DRV8305', pins: 32 },
    { id: 'Q1', type: 'MOSFET', part: 'CSD19536', pins: 3 },
    { id: 'Q2', type: 'MOSFET', part: 'CSD19536', pins: 3 },
    { id: 'Q3', type: 'MOSFET', part: 'CSD19536', pins: 3 },
    { id: 'ADC1', type: 'ADC', part: 'ADC128S102', pins: 16 },
    { id: 'PWR1', type: 'POWER', part: 'TPS54340', pins: 14 },
  ],
  edges: [
    { from: 'MCU1', to: 'DRV1', net: 'SPI_CONTROL' },
    { from: 'DRV1', to: 'Q1', net: 'GATE_A_H' },
    { from: 'DRV1', to: 'Q2', net: 'GATE_B_H' },
    { from: 'DRV1', to: 'Q3', net: 'GATE_C_H' },
    { from: 'MCU1', to: 'ADC1', net: 'SPI2_SENSE' },
    { from: 'PWR1', to: 'MCU1', net: 'VCC_3V3' },
    { from: 'PWR1', to: 'DRV1', net: 'VCC_5V' },
  ],
};

export default function Netlist({ project, statuses, setTab }: Props) {
  const [view, setView] = useState<'diagram' | 'json'>('diagram');
  const p4Status = statuses['P4']?.status;

  if (!project) {
    return <div style={{ padding: '40px', fontFamily: '"DM Mono", monospace', fontSize: '13px', color: 'var(--text3)', textAlign: 'center' }}>Select a project to view netlist.</div>;
  }

  if (!p4Status || p4Status === 'pending') {
    return (
      <div style={{ padding: '40px', textAlign: 'center' }}>
        <div style={{ fontFamily: '"DM Mono", monospace', fontSize: '13px', color: 'var(--text3)', marginBottom: '16px' }}>
          Phase 4 has not run yet. Go to Pipeline tab and click Run P4.
        </div>
        <button onClick={() => setTab('pipeline')} style={{ padding: '10px 20px', background: 'var(--teal)', border: 'none', borderRadius: '4px', color: '#070b14', fontFamily: '"DM Mono", monospace', fontSize: '11px', fontWeight: 700, cursor: 'pointer' }}>
          GO TO PIPELINE
        </button>
      </div>
    );
  }

  if (p4Status === 'in_progress') {
    return (
      <div style={{ padding: '40px', textAlign: 'center' }}>
        <div className="spin-slow" style={{ width: '32px', height: '32px', border: '3px solid var(--teal)', borderTopColor: 'transparent', borderRadius: '50%', margin: '0 auto 16px' }} />
        <div style={{ fontFamily: '"DM Mono", monospace', fontSize: '13px', color: 'var(--text3)' }}>Netlist generation in progress...</div>
      </div>
    );
  }

  return (
    <div style={{ padding: '24px' }} className="fade-up">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <div>
          <div style={{ fontFamily: '"Syne", sans-serif', fontSize: '18px', fontWeight: 700, color: 'var(--text)' }}>
            Netlist <span style={{ color: 'var(--teal)' }}>Viewer</span>
          </div>
          <div style={{ fontFamily: '"DM Mono", monospace', fontSize: '11px', color: 'var(--text3)', marginTop: '2px' }}>
            {MOCK_NETLIST.nodes.length} nodes x {MOCK_NETLIST.edges.length} edges
          </div>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          {(['diagram', 'json'] as const).map(v => (
            <button key={v} onClick={() => setView(v)} style={{
              padding: '7px 14px', background: view === v ? 'rgba(0,198,167,0.12)' : 'none',
              border: "1px solid " + (view === v ? 'var(--teal-border)' : 'var(--border)'),
              borderRadius: '4px', color: view === v ? 'var(--teal)' : 'var(--text2)',
              fontFamily: '"DM Mono", monospace', fontSize: '10px', letterSpacing: '0.08em', cursor: 'pointer',
            }}>
              {v.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      <div style={{ display: 'flex', gap: '12px', marginBottom: '20px' }}>
        {[
          { label: 'NODES', value: MOCK_NETLIST.nodes.length },
          { label: 'NETS', value: MOCK_NETLIST.edges.length },
          { label: 'MCU', value: 1 },
          { label: 'DRC ERRORS', value: 0 },
        ].map(s => (
          <div key={s.label} style={{ flex: 1, background: 'var(--panel)', border: '1px solid var(--border)', borderRadius: '4px', padding: '10px 14px' }}>
            <div className="section-label" style={{ marginBottom: '4px' }}>{s.label}</div>
            <div style={{ fontFamily: '"Syne", sans-serif', fontSize: '18px', fontWeight: 700, color: s.label === 'DRC ERRORS' ? 'var(--green)' : 'var(--teal)' }}>{s.value}</div>
          </div>
        ))}
      </div>

      {view === 'diagram' ? (
        <div style={{ background: 'var(--panel)', border: '1px solid var(--border)', borderRadius: '6px', padding: '20px' }}>
          <div className="section-label" style={{ marginBottom: '12px' }}>COMPONENT NODES</div>
          <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap', justifyContent: 'center', padding: '20px 0' }}>
            {MOCK_NETLIST.nodes.map(node => {
              const typeColors: Record<string, string> = {
                MCU: 'var(--teal)', GATE_DRIVER: 'var(--blue)', MOSFET: 'var(--warning)', ADC: 'var(--green)', POWER: '#a78bfa'
              };
              const c = typeColors[node.type] || 'var(--border)';
              return (
                <div key={node.id} style={{
                  background: 'var(--panel2)', border: "1px solid " + c,
                  borderRadius: '6px', padding: '12px 16px', textAlign: 'center', minWidth: '100px',
                }}>
                  <div style={{ fontFamily: '"DM Mono", monospace', fontSize: '9px', color: c, letterSpacing: '0.1em', marginBottom: '4px' }}>{node.type}</div>
                  <div style={{ fontFamily: '"Syne", sans-serif', fontSize: '13px', fontWeight: 700, color: 'var(--text)' }}>{node.id}</div>
                  <div style={{ fontFamily: '"DM Mono", monospace', fontSize: '10px', color: 'var(--text3)', marginTop: '2px' }}>{node.part}</div>
                  <div style={{ fontFamily: '"DM Mono", monospace', fontSize: '9px', color: 'var(--text4)', marginTop: '2px' }}>{node.pins} pins</div>
                </div>
              );
            })}
          </div>
          <div style={{ marginTop: '16px', borderTop: '1px solid var(--border)', paddingTop: '16px' }}>
            <div className="section-label" style={{ marginBottom: '8px' }}>NETS</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
              {MOCK_NETLIST.edges.map((e, i) => (
                <div key={i} style={{ fontFamily: '"DM Mono", monospace', fontSize: '10px', padding: '3px 8px', background: 'var(--panel3)', borderRadius: '3px', color: 'var(--text2)', border: '1px solid var(--border2)' }}>
                  {e.from} to {e.to}: <span style={{ color: 'var(--teal)' }}>{e.net}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : (
        <div style={{ background: 'var(--panel3)', border: '1px solid var(--border)', borderRadius: '6px', padding: '20px', overflow: 'auto' }}>
          <pre style={{ fontFamily: '"JetBrains Mono", monospace', fontSize: '12px', color: 'var(--text2)', margin: 0, lineHeight: 1.7 }}>
            {JSON.stringify(MOCK_NETLIST, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
