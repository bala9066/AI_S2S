import { useState, useEffect } from 'react';

interface LLMSettings {
  glm_api_key?: string;
  deepseek_api_key?: string;
  anthropic_api_key?: string;
  glm_base_url?: string;
  deepseek_base_url?: string;
  primary_model?: string;
  fast_model?: string;
}

interface Props {
  open: boolean;
  onClose: () => void;
  onSave: (settings: LLMSettings) => Promise<void>;
}

const DEFAULT_SETTINGS: LLMSettings = {
  glm_api_key: '',
  deepseek_api_key: '',
  anthropic_api_key: '',
  glm_base_url: 'https://api.z.ai/api/anthropic',
  deepseek_base_url: 'https://api.deepseek.com',
  primary_model: '',
  fast_model: '',
};

export default function LLMSettingsModal({ open, onClose, onSave }: Props) {
  const [settings, setSettings] = useState<LLMSettings>(DEFAULT_SETTINGS);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [showKeys, setShowKeys] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);

  // Load current settings on open
  useEffect(() => {
    if (open) {
      loadSettings();
    }
  }, [open]);

  const loadSettings = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await fetch('/api/v1/settings/llm');
      if (!res.ok) throw new Error('Failed to load settings');
      const data = await res.json();
      setSettings({
        glm_api_key: data.glm_api_key || '',
        deepseek_api_key: data.deepseek_api_key || '',
        anthropic_api_key: data.anthropic_api_key || '',
        glm_base_url: data.glm_base_url || 'https://api.z.ai/api/anthropic',
        deepseek_base_url: data.deepseek_base_url || 'https://api.deepseek.com',
        primary_model: data.primary_model || '',
        fast_model: data.fast_model || '',
      });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setError('');
    setSuccess(false);
    try {
      await onSave(settings);
      setSuccess(true);
      setTimeout(() => {
        onClose();
        setSuccess(false);
      }, 1500);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
    } finally {
      setSaving(false);
    }
  };

  const maskKey = (key?: string) => {
    if (!key) return '';
    if (key.length <= 8) return '•'.repeat(key.length);
    return key.slice(0, 6) + '•'.repeat(Math.min(key.length - 6, 12)) + key.slice(-4);
  };

  const monoFont = '"DM Mono", monospace';
  const syneFont = '"Syne", sans-serif';

  if (!open) return null;

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.65)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      zIndex: 1000,
    }}>
      <div style={{
        background: 'var(--panel)', border: '1px solid var(--border2)',
        borderRadius: 10, width: '90%', maxWidth: 580,
        maxHeight: '85vh', overflow: 'auto',
        boxShadow: '0 20px 60px rgba(0,0,0,0.5)',
      }}>
        {/* Header */}
        <div style={{
          padding: '18px 22px', borderBottom: '1px solid var(--border2)',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <div>
            <div style={{ fontFamily: syneFont, fontSize: 18, fontWeight: 700, color: 'var(--text)' }}>
              LLM Configuration
            </div>
            <div style={{ fontSize: 11, color: 'var(--text4)', marginTop: 3, fontFamily: monoFont }}>
              Configure your AI model API keys
            </div>
          </div>
          <button
            onClick={onClose}
            style={{
              width: 30, height: 30, borderRadius: 6, border: '1px solid var(--border2)',
              background: 'transparent', color: 'var(--text3)', cursor: 'pointer',
              fontSize: 16, display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}
            onMouseEnter={e => { e.currentTarget.style.background = 'var(--panel2)'; e.currentTarget.style.color = 'var(--text)'; }}
            onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--text3)'; }}
          >
            ×
          </button>
        </div>

        {/* Content */}
        <div style={{ padding: '20px 22px' }}>
          {loading ? (
            <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text3)' }}>
              Loading settings...
            </div>
          ) : (
            <>
              {error && (
                <div style={{
                  padding: '10px 14px', borderRadius: 6, background: 'rgba(220,38,38,0.12)',
                  border: '1px solid rgba(220,38,38,0.35)', color: '#dc2626',
                  fontSize: 12, marginBottom: 16, fontFamily: monoFont,
                }}>
                  ⚠ {error}
                </div>
              )}

              {success && (
                <div style={{
                  padding: '10px 14px', borderRadius: 6, background: 'rgba(0,198,167,0.12)',
                  border: '1px solid rgba(0,198,167,0.35)', color: 'var(--teal)',
                  fontSize: 12, marginBottom: 16, fontFamily: monoFont,
                }}>
                  ✓ Settings saved successfully!
                </div>
              )}

              {/* API Keys Section */}
              <div style={{ marginBottom: 20 }}>
                <div style={{
                  fontSize: 11, color: 'var(--text4)', letterSpacing: '0.1em',
                  marginBottom: 12, fontFamily: monoFont,
                }}>
                  API KEYS
                </div>

                {/* GLM */}
                <div style={{ marginBottom: 14 }}>
                  <label style={{ display: 'block', fontSize: 12, color: 'var(--text2)', marginBottom: 5, fontWeight: 500 }}>
                    GLM API Key (Z.AI)
                  </label>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <input
                      type={showKeys ? 'text' : 'password'}
                      value={settings.glm_api_key}
                      onChange={e => setSettings({ ...settings, glm_api_key: e.target.value })}
                      placeholder="Enter GLM API key"
                      style={{
                        flex: 1, padding: '9px 12px', borderRadius: 6,
                        background: 'var(--panel2)', border: '1px solid var(--border2)',
                        color: 'var(--text)', fontSize: 12, fontFamily: monoFont,
                        outline: 'none',
                      }}
                    />
                    <button
                      onClick={() => setShowKeys(!showKeys)}
                      style={{
                        padding: '8px 12px', borderRadius: 6, border: '1px solid var(--border2)',
                        background: 'var(--panel2)', color: 'var(--text3)', cursor: 'pointer',
                        fontSize: 11, fontFamily: monoFont,
                      }}
                    >
                      {showKeys ? '👁 Hide' : '👁 Show'}
                    </button>
                  </div>
                  <div style={{ fontSize: 10, color: 'var(--text4)', marginTop: 4 }}>
                    Get your key at <a href="https://open.bigmodel.cn" target="_blank" rel="noopener" style={{ color: 'var(--teal)' }}>open.bigmodel.cn</a>
                  </div>
                </div>

                {/* DeepSeek */}
                <div style={{ marginBottom: 14 }}>
                  <label style={{ display: 'block', fontSize: 12, color: 'var(--text2)', marginBottom: 5, fontWeight: 500 }}>
                    DeepSeek API Key
                  </label>
                  <input
                    type={showKeys ? 'text' : 'password'}
                    value={settings.deepseek_api_key}
                    onChange={e => setSettings({ ...settings, deepseek_api_key: e.target.value })}
                    placeholder="Enter DeepSeek API key"
                    style={{
                      width: '100%', boxSizing: 'border-box', padding: '9px 12px', borderRadius: 6,
                      background: 'var(--panel2)', border: '1px solid var(--border2)',
                      color: 'var(--text)', fontSize: 12, fontFamily: monoFont,
                      outline: 'none',
                    }}
                  />
                  <div style={{ fontSize: 10, color: 'var(--text4)', marginTop: 4 }}>
                    Get your key at <a href="https://platform.deepseek.com" target="_blank" rel="noopener" style={{ color: 'var(--teal)' }}>platform.deepseek.com</a>
                  </div>
                </div>

                {/* Anthropic */}
                <div style={{ marginBottom: 14 }}>
                  <label style={{ display: 'block', fontSize: 12, color: 'var(--text2)', marginBottom: 5, fontWeight: 500 }}>
                    Anthropic API Key (Claude)
                  </label>
                  <input
                    type={showKeys ? 'text' : 'password'}
                    value={settings.anthropic_api_key}
                    onChange={e => setSettings({ ...settings, anthropic_api_key: e.target.value })}
                    placeholder="Enter Anthropic API key"
                    style={{
                      width: '100%', boxSizing: 'border-box', padding: '9px 12px', borderRadius: 6,
                      background: 'var(--panel2)', border: '1px solid var(--border2)',
                      color: 'var(--text)', fontSize: 12, fontFamily: monoFont,
                      outline: 'none',
                    }}
                  />
                  <div style={{ fontSize: 10, color: 'var(--text4)', marginTop: 4 }}>
                    Get your key at <a href="https://console.anthropic.com" target="_blank" rel="noopener" style={{ color: 'var(--teal)' }}>console.anthropic.com</a>
                  </div>
                </div>
              </div>

              {/* Advanced Settings */}
              <div style={{ marginBottom: 16 }}>
                <div style={{
                  fontSize: 11, color: 'var(--text4)', letterSpacing: '0.1em',
                  marginBottom: 12, fontFamily: monoFont,
                }}>
                  ADVANCED
                </div>

                {/* GLM Base URL */}
                <div style={{ marginBottom: 12 }}>
                  <label style={{ display: 'block', fontSize: 12, color: 'var(--text2)', marginBottom: 5, fontWeight: 500 }}>
                    GLM Base URL
                  </label>
                  <input
                    type="text"
                    value={settings.glm_base_url}
                    onChange={e => setSettings({ ...settings, glm_base_url: e.target.value })}
                    style={{
                      width: '100%', boxSizing: 'border-box', padding: '9px 12px', borderRadius: 6,
                      background: 'var(--panel2)', border: '1px solid var(--border2)',
                      color: 'var(--text)', fontSize: 12, fontFamily: monoFont,
                      outline: 'none',
                    }}
                  />
                </div>

                {/* Primary Model */}
                <div style={{ marginBottom: 12 }}>
                  <label style={{ display: 'block', fontSize: 12, color: 'var(--text2)', marginBottom: 5, fontWeight: 500 }}>
                    Primary Model (optional override)
                  </label>
                  <input
                    type="text"
                    value={settings.primary_model}
                    onChange={e => setSettings({ ...settings, primary_model: e.target.value })}
                    placeholder="e.g., glm-4.7, deepseek-chat, claude-sonnet-4-6"
                    style={{
                      width: '100%', boxSizing: 'border-box', padding: '9px 12px', borderRadius: 6,
                      background: 'var(--panel2)', border: '1px solid var(--border2)',
                      color: 'var(--text)', fontSize: 12, fontFamily: monoFont,
                      outline: 'none',
                    }}
                  />
                  <div style={{ fontSize: 10, color: 'var(--text4)', marginTop: 4 }}>
                    Leave empty for auto-selection based on available keys
                  </div>
                </div>

                {/* Fast Model */}
                <div style={{ marginBottom: 12 }}>
                  <label style={{ display: 'block', fontSize: 12, color: 'var(--text2)', marginBottom: 5, fontWeight: 500 }}>
                    Fast Model (optional override)
                  </label>
                  <input
                    type="text"
                    value={settings.fast_model}
                    onChange={e => setSettings({ ...settings, fast_model: e.target.value })}
                    placeholder="e.g., glm-4.5-air, deepseek-chat"
                    style={{
                      width: '100%', boxSizing: 'border-box', padding: '9px 12px', borderRadius: 6,
                      background: 'var(--panel2)', border: '1px solid var(--border2)',
                      color: 'var(--text)', fontSize: 12, fontFamily: monoFont,
                      outline: 'none',
                    }}
                  />
                  <div style={{ fontSize: 10, color: 'var(--text4)', marginTop: 4 }}>
                    Leave empty for auto-selection based on available keys
                  </div>
                </div>
              </div>

              {/* Info Box */}
              <div style={{
                padding: '12px', borderRadius: 6, background: 'rgba(0,198,167,0.06)',
                border: '1px solid rgba(0,198,167,0.2)', fontSize: 11,
                color: 'var(--text2)', lineHeight: 1.6,
              }}>
                <div style={{ fontWeight: 600, marginBottom: 4, color: 'var(--teal)' }}>ℹ Priority Order</div>
                The system tries models in this order: DeepSeek → GLM → Anthropic → Ollama (local).
                Configure at least one API key to use AI features.
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div style={{
          padding: '14px 22px', borderTop: '1px solid var(--border2)',
          display: 'flex', gap: 10, justifyContent: 'flex-end',
        }}>
          <button
            onClick={onClose}
            disabled={saving}
            style={{
              padding: '9px 20px', borderRadius: 6, border: '1px solid var(--border2)',
              background: 'transparent', color: 'var(--text2)', cursor: saving ? 'not-allowed' : 'pointer',
              fontSize: 12, fontFamily: monoFont, fontWeight: 500,
            }}
            onMouseEnter={e => { if (!saving) e.currentTarget.style.background = 'var(--panel2)'; }}
            onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; }}
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            style={{
              padding: '9px 20px', borderRadius: 6, border: 'none',
              background: saving ? 'var(--panel3)' : 'var(--teal)',
              color: saving ? 'var(--text4)' : '#070b14',
              cursor: saving ? 'not-allowed' : 'pointer',
              fontSize: 12, fontFamily: monoFont, fontWeight: 600,
              opacity: saving ? 0.6 : 1,
              transition: 'all 0.15s',
            }}
          >
            {saving ? 'Saving...' : 'Save Settings'}
          </button>
        </div>
      </div>
    </div>
  );
}
