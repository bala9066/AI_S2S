import React, { useState, useEffect } from 'react';
import type { Project } from '../types';
import { api } from '../api';

export default function DesignChat({ project }: { project: Project | null }) {
    const [messages, setMessages] = useState<{ role: 'user' | 'assistant', content: string }[]>([]);
    const [input, setInput] = useState('');
    const [loading, setLoading] = useState(false);

    // Initialize messages from the loaded project's conversation history
    useEffect(() => {
        if (project && project.conversation_history) {
            setMessages(project.conversation_history.map((msg: any) => ({
                role: msg.role === 'user' ? 'user' : 'assistant',
                content: msg.content
            })));
        } else {
            setMessages([]);
        }
    }, [project]);

    const handleSend = async (forcedMsg?: string) => {
        if (!project) return;
        const msg = forcedMsg || input.trim();
        if (!msg) return;

        if (!forcedMsg) {
            setMessages(prev => [...prev, { role: 'user', content: msg }]);
            setInput('');
        }
        setLoading(true);

        try {
            await api.chat(project.id, msg, (token) => {
                setMessages(prev => {
                    const last = prev[prev.length - 1];
                    if (last && last.role === 'assistant') {
                        return [...prev.slice(0, -1), { role: 'assistant', content: token }];
                    } else {
                        return [...prev, { role: 'assistant', content: token }];
                    }
                });
            });
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
        }
    };

    const handleApprove = () => {
        handleSend('Approved. Please generate the full requirements documents.');
    };

    const handleClear = () => {
        setMessages([]);
    };

    return (
        <div style={{
            display: 'flex',
            flexDirection: 'column',
            height: '100%',
            maxWidth: 1000,
            margin: '0 auto',
            position: 'relative',
            background: 'rgba(10, 14, 26, 0.4)',
            borderRadius: '8px 8px 0 0',
            border: '1px solid rgba(42, 58, 80, 0.3)',
            borderBottom: 'none'
        }}>
            {/* Design Chat Header */}
            <div style={{
                padding: '16px 24px',
                borderBottom: '1px solid rgba(42, 58, 80, 0.6)',
                background: 'rgba(13, 17, 23, 0.8)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                borderRadius: '8px 8px 0 0'
            }}>
                <div>
                    <h3 style={{ margin: 0, fontSize: 13, fontFamily: 'Syne, sans-serif', color: '#00c6a7', letterSpacing: '0.05em' }}>
                        HARDWARE DESIGN SESSION
                    </h3>
                    <p style={{ margin: '4px 0 0', fontSize: 10, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
                        Phase 1: Requirements Capture & Architecture
                    </p>
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                    <div className="badge badge-running" style={{ fontSize: 9 }}>ACTIVE SESSION</div>
                </div>
            </div>

            {/* The Chat Window itself */}
            <div style={{ flex: 1, overflowY: 'auto', padding: '24px', display: 'flex', flexDirection: 'column', gap: 20 }}>
                {messages.length === 0 ? (
                    <div style={{
                        flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                        color: '#475569', textAlign: 'center', opacity: 0.8
                    }}>
                        <div style={{ fontSize: 40, marginBottom: 16 }}>💬</div>
                        <div style={{ fontSize: 14, fontWeight: 600, color: '#94a3b8', marginBottom: 8 }}>Ready for Design Specifications</div>
                        <div style={{ fontSize: 12, maxWidth: 300, lineHeight: 1.5 }}>
                            Briefly describe your hardware goal. Use "SHALL" statements for strict requirements.
                        </div>
                    </div>
                ) : (
                    messages.map((m, i) => {
                        const isUser = m.role === 'user';
                        const hasMermaid = m.content.includes('```mermaid');

                        return (
                            <div key={i} className="fade-up" style={{
                                alignSelf: isUser ? 'flex-end' : 'flex-start',
                                maxWidth: '85%',
                                display: 'flex',
                                flexDirection: 'column',
                                alignItems: isUser ? 'flex-end' : 'flex-start'
                            }}>
                                <div style={{
                                    fontSize: 9,
                                    color: isUser ? '#4fc3f7' : '#c9a84c',
                                    marginBottom: 6,
                                    fontWeight: 700,
                                    letterSpacing: '0.1em',
                                    textTransform: 'uppercase',
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: 6
                                }}>
                                    {isUser ? 'Engineer Input' : 'AI Architect Output'}
                                    <span style={{ fontSize: 10, opacity: 0.6 }}>— {new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                                </div>
                                <div style={{
                                    padding: '16px 20px',
                                    borderRadius: isUser ? '16px 4px 16px 16px' : '4px 16px 16px 16px',
                                    background: isUser ? 'rgba(7, 89, 133, 0.15)' : 'rgba(201, 168, 76, 0.1)',
                                    border: `1px solid ${isUser ? 'rgba(79,195,247,0.3)' : 'rgba(201,168,76,0.3)'}`,
                                    boxShadow: isUser ? '0 4px 12px rgba(0,0,0,0.1)' : '0 4px 12px rgba(0,0,0,0.15)',
                                    color: '#e2e8f0',
                                    fontSize: 13,
                                    lineHeight: 1.62,
                                    whiteSpace: 'pre-wrap',
                                    fontFamily: '"Inter", sans-serif'
                                }}>
                                    {m.content}
                                    {hasMermaid && (
                                        <div style={{
                                            marginTop: 16,
                                            padding: '12px',
                                            background: 'rgba(0,0,0,0.4)',
                                            borderRadius: 8,
                                            border: '1px dashed rgba(201,168,76,0.5)',
                                            display: 'flex',
                                            alignItems: 'center',
                                            gap: 12
                                        }}>
                                            <div style={{ fontSize: 24 }}>📊</div>
                                            <div style={{ flex: 1 }}>
                                                <div style={{ fontWeight: 600, fontSize: 11, color: '#c9a84c' }}>SYSTEM ARCHITECTURE DIAGRAM</div>
                                                <div style={{ fontSize: 10, color: '#94a3b8' }}>Rendered visual is available in the Documents tab.</div>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            </div>
                        );
                    })
                )}
                {loading && (
                    <div style={{ alignSelf: 'flex-start', display: 'flex', alignItems: 'center', gap: 12, padding: '8px 16px' }}>
                        <span className="spin-slow" style={{ display: 'inline-block', width: 14, height: 14, border: `2px solid rgba(201,168,76,0.2)`, borderTopColor: '#c9a84c', borderRadius: '50%' }} />
                        <span style={{ fontSize: 12, color: '#c9a84c', fontFamily: 'DM Mono, monospace', letterSpacing: '0.05em' }}>AI ARCHITECT IS THINKING...</span>
                    </div>
                )}
            </div>

            {/* Input area */}
            <div style={{
                background: 'rgba(13, 17, 23, 0.9)',
                borderTop: '1px solid rgba(42,58,80,0.8)',
                padding: '24px',
                borderRadius: '0 0 8px 8px'
            }}>
                <textarea
                    value={input}
                    onChange={e => setInput(e.target.value)}
                    onKeyDown={e => {
                        if (e.key === 'Enter' && !e.shiftKey) {
                            e.preventDefault();
                            handleSend();
                        }
                    }}
                    placeholder="Provide design instructions or query component specs..."
                    rows={3}
                    style={{
                        width: '100%',
                        background: 'rgba(7, 11, 20, 0.8)',
                        border: '1px solid #2a3548',
                        color: '#dce6f0',
                        padding: '16px',
                        outline: 'none',
                        resize: 'none',
                        fontSize: 13,
                        fontFamily: '"Inter", sans-serif',
                        borderRadius: 8,
                        marginBottom: 16,
                        transition: 'all 0.2s',
                        boxShadow: 'inset 0 2px 4px rgba(0,0,0,0.4)'
                    }}
                    onFocus={(e) => {
                        e.target.style.borderColor = '#00c6a7';
                        e.target.style.background = 'rgba(7, 11, 20, 1)';
                    }}
                    onBlur={(e) => {
                        e.target.style.borderColor = '#2a3548';
                        e.target.style.background = 'rgba(7, 11, 20, 0.8)';
                    }}
                />

                <div style={{ display: 'flex', gap: 12, justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ display: 'flex', gap: 10 }}>
                        <button
                            onClick={handleApprove}
                            disabled={loading || messages.length < 2}
                            style={{
                                padding: '10px 18px',
                                borderRadius: 6,
                                cursor: (loading || messages.length < 2) ? 'not-allowed' : 'pointer',
                                background: 'rgba(16, 185, 129, 0.1)',
                                border: '1px solid rgba(16, 185, 129, 0.3)',
                                color: '#10b981',
                                fontSize: 11,
                                fontWeight: 600,
                                fontFamily: 'DM Mono, monospace',
                                display: 'flex',
                                alignItems: 'center',
                                gap: 8,
                                transition: 'all 0.2s'
                            }}
                            onMouseEnter={e => { if (!loading && messages.length >= 2) (e.currentTarget as HTMLElement).style.background = 'rgba(16, 185, 129, 0.2)'; }}
                            onMouseLeave={e => { if (!loading && messages.length >= 2) (e.currentTarget as HTMLElement).style.background = 'rgba(16, 185, 129, 0.1)'; }}
                        >
                            <span>✓</span> APPROVE DRAFT
                        </button>
                        <button
                            onClick={handleClear}
                            disabled={loading || messages.length === 0}
                            style={{
                                padding: '10px 18px',
                                borderRadius: 6,
                                cursor: (loading || messages.length === 0) ? 'not-allowed' : 'pointer',
                                background: 'rgba(244, 63, 94, 0.05)',
                                border: '1px solid rgba(244, 63, 94, 0.2)',
                                color: '#f43f5e',
                                fontSize: 11,
                                fontWeight: 500,
                                fontFamily: 'DM Mono, monospace',
                                transition: 'all 0.2s'
                            }}
                            onMouseEnter={e => { if (!loading && messages.length > 0) (e.currentTarget as HTMLElement).style.background = 'rgba(244, 63, 94, 0.1)'; }}
                            onMouseLeave={e => { if (!loading && messages.length > 0) (e.currentTarget as HTMLElement).style.background = 'rgba(244, 63, 94, 0.05)'; }}
                        >
                            CLEAR CHAT
                        </button>
                    </div>

                    <button
                        onClick={() => handleSend()}
                        disabled={loading || !input.trim()}
                        style={{
                            padding: '10px 28px',
                            background: (loading || !input.trim()) ? 'rgba(42,58,80,0.5)' : '#00c6a7',
                            color: '#070b14',
                            border: 'none',
                            borderRadius: 6,
                            cursor: (loading || !input.trim()) ? 'not-allowed' : 'pointer',
                            fontSize: 12,
                            fontWeight: 700,
                            fontFamily: 'DM Mono, monospace',
                            display: 'flex',
                            alignItems: 'center',
                            gap: 10,
                            transition: 'all 0.2s',
                            boxShadow: (loading || !input.trim()) ? 'none' : '0 4px 12px rgba(0, 198, 167, 0.3)'
                        }}
                        onMouseEnter={e => { if (!loading && input.trim()) (e.currentTarget as HTMLElement).style.transform = 'translateY(-1px)'; }}
                        onMouseLeave={e => { if (!loading && input.trim()) (e.currentTarget as HTMLElement).style.transform = 'translateY(0)'; }}
                    >
                        SEND MESSAGE <span>→</span>
                    </button>
                </div>
            </div>
        </div>
    );
}