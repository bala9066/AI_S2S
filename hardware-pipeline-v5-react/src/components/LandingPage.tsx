interface Props {
  onCreate: () => void;
  onLoad: () => void;
}

export default function LandingPage({ onCreate, onLoad }: Props) {
  return (
    <div style={{
      minHeight: '100vh', background: 'var(--navy)',
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      position: 'relative', overflow: 'hidden',
    }}>
      {/* Grid background */}
      <div style={{
        position: 'absolute', inset: 0,
        backgroundImage: 'linear-gradient(#0c1524 1px, transparent 1px), linear-gradient(90deg, #0c1524 1px, transparent 1px)',
        backgroundSize: '52px 52px', opacity: 0.5, pointerEvents: 'none',
      }} />

      {/* Glow orb */}
      <div style={{
        position: 'absolute', top: '45%', left: '50%', transform: 'translate(-50%, -50%)',
        width: 600, height: 600, borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(0,198,167,0.12) 0%, transparent 70%)',
        pointerEvents: 'none',
      }} />

      {/* Content */}
      <div style={{ position: 'relative', textAlign: 'center', maxWidth: 560 }}>
        {/* Sub-brand */}
        <div style={{ fontSize: 10, color: 'var(--teal)', letterSpacing: '0.18em', marginBottom: 20, fontFamily: "'DM Mono', monospace" }}>
          DATA PATTERNS &middot; CODE KNIGHTS
        </div>

        {/* Hero headline */}
        <div style={{ fontFamily: "'Syne', sans-serif", fontSize: 52, fontWeight: 800, lineHeight: 1.05, marginBottom: 16 }}>
          Hardware{' '}
          <span style={{ color: 'var(--teal)', textShadow: '0 0 40px rgba(0,198,167,0.4)' }}>Pipeline</span>
        </div>

        {/* Tagline */}
        <div style={{ fontSize: 13, color: 'var(--text3)', marginBottom: 10, letterSpacing: '0.04em' }}>
          AI-Powered Hardware Design Studio
        </div>

        {/* Hackathon line */}
        <div style={{ fontSize: 10, color: 'var(--text4)', letterSpacing: '0.14em', marginBottom: 48, fontFamily: "'DM Mono', monospace" }}>
          DATA PATTERNS INDIA &middot; GREAT AI HACK-A-THON 2026
        </div>

        {/* Phase dots preview */}
        <div style={{ display: 'flex', gap: 6, justifyContent: 'center', marginBottom: 48 }}>
          {['#00c6a7','#3b82f6','#f59e0b','#8b5cf6','#475569','#00c6a7','#475569','#00c6a7','#3b82f6','#8b5cf6'].map((c, i) => (
            <div key={i} style={{
              width: 8, height: 8, borderRadius: '50%', background: c,
              opacity: 0.5 + (i / 20),
              boxShadow: `0 0 8px ${c}66`,
            }} />
          ))}
        </div>

        {/* CTA buttons */}
        <div style={{ display: 'flex', gap: 14, justifyContent: 'center' }}>
          <button onClick={onCreate} style={{
            background: 'var(--teal)', color: 'var(--navy)',
            border: 'none', borderRadius: 6, padding: '12px 32px',
            fontSize: 13, fontFamily: "'DM Mono', monospace", fontWeight: 500,
            cursor: 'pointer', letterSpacing: '0.06em',
            boxShadow: '0 0 24px rgba(0,198,167,0.35)',
            transition: 'all 0.2s',
          }}
            onMouseEnter={e => (e.currentTarget.style.boxShadow = '0 0 36px rgba(0,198,167,0.55)')}
            onMouseLeave={e => (e.currentTarget.style.boxShadow = '0 0 24px rgba(0,198,167,0.35)')}
          >
            + Create New Project
          </button>
          <button onClick={onLoad} style={{
            background: 'transparent', color: 'var(--text2)',
            border: '1px solid var(--panel3)', borderRadius: 6, padding: '12px 32px',
            fontSize: 13, fontFamily: "'DM Mono', monospace", fontWeight: 500,
            cursor: 'pointer', letterSpacing: '0.06em',
            transition: 'all 0.2s',
          }}
            onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--teal)'; e.currentTarget.style.color = 'var(--teal)'; }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--panel3)'; e.currentTarget.style.color = 'var(--text2)'; }}
          >
            Load Existing
          </button>
        </div>
      </div>
    </div>
  );
}
