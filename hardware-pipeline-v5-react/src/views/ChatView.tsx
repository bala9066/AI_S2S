import { useState, useRef, useEffect } from 'react';
import type { Project, PhaseMeta } from '../types';
import { api } from '../api';

interface Message { role: 'user' | 'ai'; text: string; }

interface Props {
  project: Project | null;
  phase: PhaseMeta;
  onStatusChange: () => void;
}

const SUGGESTIONS = [
  'Design a 3-phase BLDC motor driver for 24V / 10A with CAN bus',
  'RF front-end for 2.4GHz with LNA, mixer, and VGA',
  'Power management IC for IoT device on 3.7V Li-Ion',
  'FPGA-based digital signal processing board',
];

export default function ChatView({ project, phase, onStatusChange }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [displayed, setDisplayed] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, displayed]);

  const sendMessage = async (text: string) => {
    if (!project || !text.trim() || loading) return;
    const userMsg: Message = { role: 'user', text };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setLoading(true);
    setDisplayed('');

    try {
      await api.chat(project.id, text, (fullText) => {
        // Typewriter animation
        let i = 0;
        const interval = setInterval(() => {
          i += 2;
          setDisplayed(fullText.slice(0, i));
          if (i >= fullText.length) {
            clearInterval(interval);
            setMessages(prev => [...prev, { role: 'ai', text: fullText }]);
            setDisplayed('');
            setLoading(false);
            onStatusChange();
          }
        }, 12);
      });
    } catch {
      setMessages(prev => [...prev, { role: 'ai', text: 'Error connecting to backend. Make sure FastAPI is running on port 8000.' }]);
      setDisplayed('');
      setLoading(false);
    }
  };

  return (
    <div style={{ paddingTop: 20, display: 'flex', flexDirection: 'column', minHeight: 400 }}>
      {/* Messages */}
      <div style={{ flex: 1, marginBottom: 16 }}>
        {messages.length === 0 && !loading && (
          <div style={{ marginBottom: 24 }}>
            <div style={{ fontSize: 13, color: 'var(--text3)', marginBottom: 16 }}>
              Describe your hardware design. Claude will extract requirements, select components, and generate a BOM.
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {SUGGESTIONS.map((s, i) => (
                <button key={i} onClick={() => sendMessage(s)} style={{
                  fontSize: 11, padding: '6px 14px', borderRadius: 20,
                  background: `${phase.color}10`, border: `1px solid ${phase.color}33`,
                  color: phase.color, cursor: 'pointer', fontFamily: "'DM Mono', monospace",
                  transition: 'all 0.15s',
                }}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} style={{
            marginBottom: 16,
            display: 'flex',
            justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
          }}>
            <div style={{
              maxWidth: '80%', padding: '11px 15px', borderRadius: 8,
              fontSize: 13, lineHeight: 1.6, whiteSpace: 'pre-wrap',
              background: msg.role === 'user' ? `${phase.color}18` : 'var(--panel2)',
              border: `1px solid ${msg.role === 'user' ? phase.color + '33' : 'var(--panel3)'}`,
              color: msg.role === 'user' ? 'var(--text)' : 'var(--text2)',
            }}>
              {msg.text}
            </div>
          </div>
        ))}

        {/* Streaming display */}
        {loading && (
          <div style={{ marginBottom: 16 }}>
            <div style={{
              maxWidth: '80%', padding: '11px 15px', borderRadius: 8,
              fontSize: 13, lineHeight: 1.6, whiteSpace: 'pre-wrap',
              background: 'var(--panel2)', border: '1px solid var(--panel3)',
              color: 'var(--text2)',
            }}>
              {displayed || (
                <span style={{ color: 'var(--text4)' }}>Thinking<span style={{ animation: 'blink 1s step-end infinite' }}>...</span></span>
              )}
              {displayed && <span style={{ animation: 'blink 0.7s step-end infinite', color: phase.color }}>|</span>}
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div style={{ display: 'flex', gap: 10, alignItems: 'flex-end' }}>
        <textarea
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(input); } }}
          placeholder="Describe your hardware design..."
          disabled={loading}
          rows={3}
          style={{
            flex: 1, background: '#060a10',
            border: '1px solid var(--panel3)', borderRadius: 6,
            padding: '10px 13px', fontSize: 13,
            color: 'var(--text)', fontFamily: "'DM Mono', monospace",
            resize: 'none', transition: 'border-color 0.2s',
          }}
        />
        <button
          onClick={() => sendMessage(input)}
          disabled={!input.trim() || loading || !project}
          style={{
            padding: '10px 20px', borderRadius: 6, border: 'none',
            background: input.trim() && !loading ? phase.color : 'var(--panel2)',
            color: input.trim() && !loading ? 'var(--navy)' : 'var(--text4)',
            fontSize: 12, fontFamily: "'DM Mono', monospace", fontWeight: 500,
            cursor: input.trim() && !loading ? 'pointer' : 'default',
            transition: 'all 0.15s', alignSelf: 'stretch',
          }}
        >
          Send
        </button>
      </div>
    </div>
  );
}
