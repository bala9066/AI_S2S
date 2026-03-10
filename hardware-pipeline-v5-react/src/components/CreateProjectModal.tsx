import { useState } from 'react';

interface Props {
  onConfirm: (name: string, description: string, design_type: string) => void;
  onCancel: () => void;
}

export default function CreateProjectModal({ onConfirm, onCancel }: Props) {
  const [name, setName] = useState('');
  const [desc, setDesc] = useState('');
  const [dtype, setDtype] = useState('rf');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async () => {
    if (!name.trim()) return;
    setLoading(true);
    await onConfirm(name.trim(), desc.trim(), dtype);
    setLoading(false);
  };

  const inputStyle = {
    width: '100%', background: '#060a10', border: '1px solid var(--panel3)',
    borderRadius: 5, padding: '10px 13px', fontSize: 13,
    color: 'var(--text)', fontFamily: "'DM Mono', monospace",
    transition: 'border-color 0.2s',
  } as React.CSSProperties;

  const labelStyle = {
    fontSize: 10, color: 'var(--text3)', letterSpacing: '0.12em', marginBottom: 6, display: 'block',
  } as React.CSSProperties;

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(7,11,20,0.88)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100,
    }}>
      <div style={{
        background: 'var(--panel)', border: '1px solid var(--panel2)',
        borderRadius: 10, padding: 30, width: 460,
        boxShadow: '0 24px 60px rgba(0,0,0,0.7)',
      }}>
        <div style={{ fontFamily: "'Syne', sans-serif", fontSize: 17, fontWeight: 800, marginBottom: 6 }}>
          New Project
        </div>
        <div style={{ fontSize: 12, color: 'var(--text3)', marginBottom: 24 }}>
          Configure your hardware design project
        </div>

        <div style={{ marginBottom: 16 }}>
          <label style={labelStyle}>PROJECT NAME</label>
          <input
            style={inputStyle}
            placeholder="e.g. BLDC Motor Driver v2"
            value={name}
            onChange={e => setName(e.target.value)}
            autoFocus
          />
        </div>

        <div style={{ marginBottom: 16 }}>
          <label style={labelStyle}>DESCRIPTION</label>
          <textarea
            style={{ ...inputStyle, minHeight: 80, resize: 'vertical' }}
            placeholder="Describe the hardware design..."
            value={desc}
            onChange={e => setDesc(e.target.value)}
          />
        </div>

        <div style={{ marginBottom: 28 }}>
          <label style={labelStyle}>DESIGN TYPE</label>
          <div style={{ display: 'flex', gap: 10 }}>
            {['rf', 'digital'].map(dt => (
              <button key={dt} onClick={() => setDtype(dt)} style={{
                flex: 1, padding: '9px 0', borderRadius: 5, cursor: 'pointer',
                fontSize: 12, fontFamily: "'DM Mono', monospace",
                background: dtype === dt ? 'rgba(0,198,167,0.15)' : '#060a10',
                border: `1px solid ${dtype === dt ? 'var(--teal)' : 'var(--panel3)'}`,
                color: dtype === dt ? 'var(--teal)' : 'var(--text3)',
                transition: 'all 0.15s',
              }}>
                {dt.toUpperCase()}
              </button>
            ))}
          </div>
        </div>

        <div style={{ display: 'flex', gap: 10 }}>
          <button onClick={onCancel} style={{
            flex: 1, padding: '10px 0', borderRadius: 5, cursor: 'pointer',
            fontSize: 12, fontFamily: "'DM Mono', monospace",
            background: 'transparent', border: '1px solid var(--panel3)',
            color: 'var(--text3)', transition: 'all 0.15s',
          }}>
            Cancel
          </button>
          <button onClick={handleSubmit} disabled={!name.trim() || loading} style={{
            flex: 2, padding: '10px 0', borderRadius: 5, cursor: name.trim() && !loading ? 'pointer' : 'default',
            fontSize: 12, fontFamily: "'DM Mono', monospace", fontWeight: 500,
            background: name.trim() && !loading ? 'var(--teal)' : 'var(--panel2)',
            border: 'none', color: name.trim() && !loading ? 'var(--navy)' : 'var(--text4)',
            transition: 'all 0.15s',
          }}>
            {loading ? 'Creating...' : 'CREATE & START →'}
          </button>
        </div>
      </div>
    </div>
  );
}
