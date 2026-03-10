import React, { useState } from 'react';
import { api } from '../api';
import type { Project } from '../types';

interface Props {
  onCreated: (p: Project) => void;
}

export default function NewProject({ onCreated }: Props) {
  const [name, setName] = useState('');
  const [productId, setProductId] = useState('');
  const [description, setDescription] = useState('');
  const [designType, setDesignType] = useState('Digital');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const inputStyle: React.CSSProperties = {
    width: '100%', background: 'var(--navy)', border: '1px solid var(--border)',
    borderRadius: '4px', padding: '12px 14px', color: 'var(--text)',
    fontFamily: '"DM Mono", monospace', fontSize: '13px', outline: 'none',
  };

  const labelStyle: React.CSSProperties = {
    display: 'block', fontFamily: '"DM Mono", monospace', fontSize: '9px',
    letterSpacing: '0.18em', textTransform: 'uppercase', color: 'var(--text3)', marginBottom: '8px',
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) { setError('Project name is required'); return; }
    setLoading(true); setError('');
    try {
      const p = await api.createProject({ name, description, design_type: designType });
      onCreated(p);
    } catch (err: any) {
      setError(err.message || 'Failed to create project');
      setLoading(false);
    }
  };

  return (
    <div style={{ padding: '40px', maxWidth: '600px' }} className="fade-up">
      <div style={{ marginBottom: '32px' }}>
        <div style={{ fontFamily: '"DM Mono", monospace', fontSize: '9px', letterSpacing: '0.2em', color: 'var(--teal)', textTransform: 'uppercase', marginBottom: '8px' }}>New Hardware Project</div>
        <h2 style={{ fontFamily: '"Syne", sans-serif', fontSize: '28px', fontWeight: 800, color: 'var(--text)' }}>
          Configure <span style={{ color: 'var(--teal)' }}>Project</span>
        </h2>
        <p style={{ fontFamily: '"DM Mono", monospace', fontSize: '12px', color: 'var(--text3)', marginTop: '8px' }}>
          Define your hardware design project to begin the AI-assisted pipeline.
        </p>
      </div>

      <form onSubmit={handleSubmit}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <div>
            <label style={labelStyle}>Project Name *</label>
            <input
              style={inputStyle}
              placeholder="e.g. BLDC Motor Driver v2"
              value={name}
              onChange={e => setName(e.target.value)}
              onFocus={e => e.target.style.borderColor = 'var(--teal)'}
              onBlur={e => e.target.style.borderColor = 'var(--border)'}
            />
          </div>
          {/* Product ID field removed — backend rejects it */}
          <div>
            <label style={labelStyle}>Description</label>
            <textarea
              style={{ ...inputStyle, minHeight: '100px', resize: 'vertical' }}
              placeholder="Describe the hardware project, key requirements, target specs…"
              value={description}
              onChange={e => setDescription(e.target.value)}
              onFocus={e => (e.target as HTMLTextAreaElement).style.borderColor = 'var(--teal)'}
              onBlur={e => (e.target as HTMLTextAreaElement).style.borderColor = 'var(--border)'}
            />
          </div>
          <div>
            <label style={labelStyle}>Design Type</label>
            <select
              style={{ ...inputStyle, cursor: 'pointer' }}
              value={designType}
              onChange={e => setDesignType(e.target.value)}
            >
              <option value="Digital">Digital</option>
              <option value="RF">RF / Wireless</option>
              <option value="Mixed Signal">Mixed Signal</option>
              <option value="Power">Power Electronics</option>
            </select>
          </div>
        </div>

        {error && (
          <div style={{ marginTop: '16px', padding: '10px 14px', background: 'rgba(220,38,38,0.08)', border: '1px solid rgba(220,38,38,0.3)', borderRadius: '4px', color: 'var(--danger)', fontFamily: '"DM Mono", monospace', fontSize: '12px' }}>
            {error}
          </div>
        )}

        <div style={{ display: 'flex', gap: '12px', marginTop: '28px' }}>
          <button
            type="submit"
            disabled={loading}
            style={{
              flex: 1, padding: '14px', background: loading ? 'rgba(0,198,167,0.15)' : 'var(--teal)',
              border: '1px solid var(--teal)', borderRadius: '4px',
              color: loading ? 'var(--teal)' : '#070b14',
              fontFamily: '"DM Mono", monospace', fontSize: '12px', letterSpacing: '0.12em',
              fontWeight: 700, cursor: loading ? 'not-allowed' : 'pointer', transition: 'all 0.15s',
            }}
          >
            {loading ? 'Creating…' : 'CREATE & START →'}
          </button>
        </div>
      </form>
    </div>
  );
}
