import { useState, useEffect, useCallback, useRef } from 'react';
import type { Project, Statuses, StatusesRaw, AppMode, CenterTab } from './types';
import type { ChatMessage } from './views/ChatView';
import { PHASES, isUnlocked } from './data/phases';
import { api } from './api';
import LandingPage from './components/LandingPage';
import LeftPanel from './components/LeftPanel';
import MiniTopbar from './components/MiniTopbar';
import PhaseHeader from './components/PhaseHeader';
import CreateProjectModal from './components/CreateProjectModal';
import LoadProjectModal from './components/LoadProjectModal';
import LLMSettingsModal from './components/LLMSettingsModal';
import Toast from './components/Toast';
import ChatView from './views/ChatView';
import DocumentsView from './views/DocumentsView';

export default function App() {
  const [theme, setTheme] = useState<'dark' | 'light'>(() => {
    return (localStorage.getItem('hw-pipeline-theme') as 'dark' | 'light') || 'dark';
  });

  // Apply data-theme to <html> so CSS vars cascade everywhere
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('hw-pipeline-theme', theme);
  }, [theme]);

  const toggleTheme = () => setTheme(t => t === 'dark' ? 'light' : 'dark');

  const [mode, setMode] = useState<AppMode>('landing');
  const [modal, setModal] = useState<'create' | 'load' | null>(null);
  const [llmSettingsOpen, setLLMSettingsOpen] = useState(false);
  const [project, setProject] = useState<Project | null>(null);
  const [statuses, setStatuses] = useState<Statuses>({});
  const [selectedPhaseIdx, setSelectedPhaseIdx] = useState(0);
  const [tab, setTab] = useState<CenterTab>('documents');
  const [toast, setToast] = useState<string | null>(null);
  const [completedIds, setCompletedIds] = useState<string[]>([]);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  // Raw status entries with updated_at timestamps — used for staleness detection
  const [statusesRaw, setStatusesRaw] = useState<StatusesRaw>({});

  // Reactive polling speed — 2s when running, 3s during active pipeline, 8s fully idle
  const [hasRunning, setHasRunning] = useState(false);
  // True from the moment runPipeline is called until all auto phases are done.
  // Keeps polling at 2s even in the brief gap between consecutive phases.
  const pipelineActiveRef = useRef(false);

  // Refs to prevent duplicate pipeline starts
  const pipelineStartedRef = useRef(false);
  const prevP1StatusRef = useRef<string | undefined>(undefined);
  // Track previous statuses for completion toast detection
  const prevStatusesRef = useRef<Statuses>({});

  // Ref to handleP1Complete so refreshStatuses can call it without circular dep
  const handleP1CompleteRef = useRef<() => void>(() => {});

  // Tracks which phase ID was last auto-advanced to, so we only jump once per
  // new running phase. Without this, every 2-3s poll overrides the user's
  // manual phase selection while the pipeline is running.
  const autoAdvancedToRef = useRef<string | null>(null);

  // ── F5 / reload persistence ─────────────────────────────────────────────────
  // Restore last-used project from sessionStorage so F5 doesn't send the user
  // back to the landing page.
  useEffect(() => {
    const saved = sessionStorage.getItem('hw-pipeline-project-id');
    if (saved) {
      api.getProject(parseInt(saved))
        .then(p => handleLoadProject(p))
        .catch(() => sessionStorage.removeItem('hw-pipeline-project-id'));
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (project) {
      sessionStorage.setItem('hw-pipeline-project-id', String(project.id));
    } else {
      sessionStorage.removeItem('hw-pipeline-project-id');
    }
  }, [project]);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3500);
  };

  // Poll phase statuses — also detects P1 completion as backup trigger
  const refreshStatuses = useCallback(async () => {
    if (!project) return;
    try {
      const [s, raw] = await Promise.all([
        api.getStatus(project.id),
        api.getStatusRaw(project.id),
      ]);
      prevP1StatusRef.current = s['P1'];

      // Detect newly completed phases for toast notifications
      const prev = prevStatusesRef.current;
      const newlyCompleted = PHASES.filter(
        p => s[p.id] === 'completed' && prev[p.id] !== 'completed' && prev[p.id] !== undefined
      );
      if (newlyCompleted.length > 0) {
        const phase = newlyCompleted[0]; // toast one at a time
        showToast(`${phase.code} \u2014 ${phase.name} complete \u2713`);
      }
      prevStatusesRef.current = s;

      setStatuses(s);
      setStatusesRaw(raw);
      const done = PHASES.filter(p => s[p.id] === 'completed').map(p => p.id);
      setCompletedIds(done);
      const running = Object.values(s).some(v => v === 'in_progress');
      setHasRunning(running);

      // Clear pipelineActive once all auto phases have a terminal status (completed / failed)
      // and nothing is currently in_progress — this returns polling to idle speed.
      if (pipelineActiveRef.current && !running) {
        const autoPhases = PHASES.filter(p => p.auto && p.id !== 'P1');
        const allDone = autoPhases.every(p => s[p.id] === 'completed' || s[p.id] === 'failed');
        if (allDone) pipelineActiveRef.current = false;
      }

      // NOTE: We no longer auto-start the pipeline from the status poll.
      // The user must explicitly click "Approve & Run" in ChatView.
    } catch (_) { /* silent */ }
  }, [project]);

  // Reactive polling:
  //   2s  — while a phase is actively in_progress
  //   2s  — while pipelineActive (brief gap between consecutive phases)
  //   3s  — short idle (project loaded but pipeline not running)
  useEffect(() => {
    if (!project) return;
    refreshStatuses();
    const isFast = hasRunning || pipelineActiveRef.current;
    const interval = setInterval(refreshStatuses, isFast ? 2000 : 3000);
    return () => clearInterval(interval);
  }, [project, refreshStatuses, hasRunning]);

  // Page Visibility API — when user comes back to Chrome after minimizing/switching,
  // fire an immediate refresh so the UI catches up instantly instead of waiting
  // for the next throttled timer tick (browsers slow background tabs to ~1 min).
  useEffect(() => {
    if (!project) return;
    const onVisible = () => {
      if (document.visibilityState === 'visible') refreshStatuses();
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => document.removeEventListener('visibilitychange', onVisible);
  }, [project, refreshStatuses]);

  // Auto-advance: when a NEW phase becomes in_progress, jump to it once.
  // Uses a ref to remember the last auto-advanced phase so subsequent polls
  // (every 2-3s) do NOT override the user's manual navigation.
  // If the user manually moves to P1 while P2 is running, they stay there.
  useEffect(() => {
    if (!project) return;
    const runningPhase = PHASES.find(p => statuses[p.id] === 'in_progress');
    if (runningPhase) {
      // Only auto-jump on the FIRST time we detect this particular phase running
      if (runningPhase.id !== autoAdvancedToRef.current) {
        autoAdvancedToRef.current = runningPhase.id;
        const idx = PHASES.findIndex(p => p.id === runningPhase.id);
        setSelectedPhaseIdx(idx);
        setTab('documents');
      }
      // If the same phase is still running, do nothing — user keeps their selection
    } else {
      // No phase running — reset so the next phase that starts can auto-advance
      autoAdvancedToRef.current = null;
    }
  }, [statuses]);

  // Called by ChatView "Approve & Run" button,
  // AND by status-poll fallback via handleP1CompleteRef
  const handleP1Complete = useCallback(async () => {
    if (!project) return;
    showToast('Phase 1 complete \u2014 starting full pipeline...');
    // Switch to Documents tab so user sees generated files immediately
    setTab('documents');
    try {
      console.log('[Pipeline] Calling runPipeline for project', project.id);
      const resp = await api.runPipeline(project.id);
      console.log('[Pipeline] runPipeline response:', resp);
      // Mark pipeline active — keeps polling at 2s throughout the full run
      pipelineActiveRef.current = true;
      // Force fast polling immediately — don't wait for the interval to notice
      setHasRunning(true);
      // Poll aggressively for first ~10s to catch the in_progress transition fast
      setTimeout(() => refreshStatuses(), 1000);
      setTimeout(() => refreshStatuses(), 2500);
      setTimeout(() => refreshStatuses(), 4500);
      setTimeout(() => refreshStatuses(), 7000);
    } catch (err) {
      console.error('[Pipeline] runPipeline FAILED:', err);
      showToast('Could not auto-start pipeline: ' + (err instanceof Error ? err.message : 'unknown error'));
    }
  }, [project, refreshStatuses]);

  // Keep ref in sync with latest handleP1Complete
  useEffect(() => {
    handleP1CompleteRef.current = handleP1Complete;
  }, [handleP1Complete]);

  // Reset pipeline-started guard and status history when project changes.
  // NOTE: pipelineStartedRef is intentionally NOT reset to false here —
  // handleLoadProject sets it correctly after reading statuses from the DB.
  // Resetting it here would race with the async status fetch and cause
  // the guard to be false during the window where statuses haven't loaded yet.
  useEffect(() => {
    pipelineActiveRef.current = false;
    prevP1StatusRef.current = undefined;
    prevStatusesRef.current = {};
  }, [project]);

  const handleExecutePhase = useCallback(async (phaseId: string) => {
    if (!project) return;
    try {
      await api.executePhase(project.id, phaseId);
      setHasRunning(true);
      // Aggressive polls to catch transition quickly
      setTimeout(() => refreshStatuses(), 800);
      setTimeout(() => refreshStatuses(), 2000);
      setTimeout(() => refreshStatuses(), 4000);
      showToast(`${phaseId} started`);
    } catch {
      showToast(`Failed to execute ${phaseId}. Check backend.`);
    }
  }, [project, refreshStatuses]);

  const handleRerunStale = useCallback(async (staleIds: string[]) => {
    if (!project || staleIds.length === 0) return;
    try {
      await api.resetAndRerun(project.id, staleIds);
      setHasRunning(true);
      setTab('documents');
      showToast(`Re-running ${staleIds.length} stale phase${staleIds.length > 1 ? 's' : ''}...`);
      setTimeout(() => refreshStatuses(), 800);
      setTimeout(() => refreshStatuses(), 2000);
      setTimeout(() => refreshStatuses(), 4000);
    } catch {
      showToast('Could not re-run stale phases. Check backend.');
    }
  }, [project, refreshStatuses]);

  const handleRunPipeline = useCallback(async () => {
    if (!project) return;
    try {
      await api.runPipeline(project.id);
      pipelineActiveRef.current = true;
      setHasRunning(true);
      setTab('documents');
      showToast('Pipeline started — running P2 → P8c...');
      setTimeout(() => refreshStatuses(), 800);
      setTimeout(() => refreshStatuses(), 2000);
      setTimeout(() => refreshStatuses(), 4000);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '';
      if (msg.includes('400') || msg.includes('Phase 1 must be completed')) {
        showToast('P1 must be completed first. Use the Chat tab to finish Phase 1.');
      } else {
        showToast('Could not start pipeline. Check backend.');
      }
    }
  }, [project, refreshStatuses]);

  const handleCreateProject = async (name: string, description: string, design_type: string) => {
    try {
      const p = await api.createProject({ name, description, design_type });
      setProject(p);
      setModal(null);
      setMode('pipeline');
      setSelectedPhaseIdx(0);
      setTab('chat');
      setChatMessages([]);
      pipelineStartedRef.current = false;
      prevP1StatusRef.current = undefined;
    } catch {
      showToast('Failed to create project');
    }
  };

  const handleLoadProject = async (p: Project) => {
    setProject(p);
    setModal(null);
    setMode('pipeline');
    // pipelineStartedRef will be set correctly after statuses load below —
    // do NOT reset it to false here yet (set at end of try block instead).
    prevP1StatusRef.current = undefined;
    try {
      // Restore P1 chat history from DB so F5 doesn't blank the conversation
      api.getConversationHistory(p.id)
        .then(history => {
          if (history.length > 0) {
            const restored: ChatMessage[] = history.map(m => ({
              role: m.role === 'assistant' ? 'ai' : 'user',
              text: m.content,
            }));
            setChatMessages(restored);
          } else {
            setChatMessages([]);
          }
        })
        .catch(() => setChatMessages([]));
    } catch (_) { setChatMessages([]); }
    try {
      const s = await api.getStatus(p.id);
      setStatuses(s);
      const done = PHASES.filter(ph => s[ph.id] === 'completed').map(ph => ph.id);
      setCompletedIds(done);
      const running = Object.values(s).some(v => v === 'in_progress');
      setHasRunning(running);
      const firstIncomplete = PHASES.findIndex(ph => !ph.manual && !done.includes(ph.id));
      const idx = firstIncomplete >= 0 ? firstIncomplete : 0;
      setSelectedPhaseIdx(idx);
      // P1: chat if still pending, documents if already complete
      const landingPhase = PHASES[idx];
      if (landingPhase.id === 'P1') {
        setTab(s['P1'] === 'completed' ? 'documents' : 'chat');
      } else {
        setTab('documents');
      }

      // IMPORTANT: restore pipelineStartedRef from DB state so "Approve & Run"
      // cannot fire a second runPipeline call if the pipeline already ran.
      // If ANY non-P1 AI phase has ever been touched (in_progress/completed/failed),
      // the pipeline was already started — block the guard.
      pipelineStartedRef.current = PHASES.some(
        ph => !ph.manual && ph.id !== 'P1' &&
          (s[ph.id] === 'in_progress' || s[ph.id] === 'completed' || s[ph.id] === 'failed')
      );
    } catch (_) { setTab('documents'); }
  };

  const handleSaveLLMSettings = async (settings: {
    glm_api_key?: string;
    deepseek_api_key?: string;
    anthropic_api_key?: string;
    glm_base_url?: string;
    deepseek_base_url?: string;
    primary_model?: string;
    fast_model?: string;
  }) => {
    const res = await fetch('/api/v1/settings/llm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(settings),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Failed to save settings');
    }
    return await res.json();
  };

  const handleSelectPhase = (idx: number) => {
    const phase = PHASES[idx];
    if (phase.manual) {
      showToast(`Completed externally in ${phase.externalTool || 'external EDA tool'}`);
      return;
    }
    const phaseStatus = statuses[phase.id] || 'pending';
    // Always allow navigation to completed or failed phases (user may want to view docs or retry)
    const alreadyRan = phaseStatus === 'completed' || phaseStatus === 'failed';
    if (!alreadyRan && !isUnlocked(phase, completedIds) && phase.id !== 'P1') {
      // Find the actual blocking AI phase (skip manual phases in the chain)
      const blockingPhase = [...PHASES].slice(0, idx).reverse().find(p => !p.manual);
      const toastMsg = blockingPhase
        ? `Complete ${blockingPhase.code} \u2014 ${blockingPhase.name} first`
        : 'Complete the previous phase first';
      showToast(toastMsg);
      return;
    }
    setSelectedPhaseIdx(idx);
    // P1: go to Chat if pending (user still designing), Documents if complete (can review outputs)
    // All other phases: always go to Documents
    if (phase.id === 'P1') {
      const p1Done = phaseStatus === 'completed';
      setTab(p1Done ? 'documents' : 'chat');
    } else {
      setTab('documents');
    }
  };

  const selectedPhase = PHASES[selectedPhaseIdx];
  const selectedStatus = statuses[selectedPhase?.id] || 'pending';

  // Staleness: a downstream phase is "stale" if P1 was re-approved AFTER that phase last ran.
  // We compare updated_at timestamps: if P1.updated_at > phase.updated_at, the phase is stale.
  const stalePhaseIds: string[] = (() => {
    const p1Updated = statusesRaw['P1']?.updated_at;
    if (!p1Updated) return [];
    const p1Time = new Date(p1Updated).getTime();
    return PHASES
      .filter(p => !p.manual && p.id !== 'P1' && statuses[p.id] === 'completed')
      .filter(p => {
        const phaseUpdated = statusesRaw[p.id]?.updated_at;
        if (!phaseUpdated) return false;
        return p1Time > new Date(phaseUpdated).getTime();
      })
      .map(p => p.id);
  })();

  if (mode === 'landing') {
    return (
      <>
        <LandingPage
          onCreate={() => setModal('create')}
          onLoad={() => setModal('load')}
          theme={theme}
          onToggleTheme={toggleTheme}
        />
        {modal === 'create' && (
          <CreateProjectModal
            onConfirm={handleCreateProject}
            onCancel={() => setModal(null)}
          />
        )}
        {modal === 'load' && (
          <LoadProjectModal
            onSelect={handleLoadProject}
            onCancel={() => setModal(null)}
          />
        )}
        {toast && <Toast message={toast} />}
      </>
    );
  }

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden', background: 'var(--navy)', fontFamily: "'DM Mono', monospace" }}>
      {/* Left Panel */}
      <LeftPanel
        phases={PHASES}
        selectedIdx={selectedPhaseIdx}
        statuses={statuses}
        completedIds={completedIds}
        stalePhaseIds={stalePhaseIds}
        onSelect={handleSelectPhase}
        onLanding={() => {
          setMode('landing');
          setProject(null);
          setStatuses({});
          setCompletedIds([]);
          setChatMessages([]);
          setHasRunning(false);
          pipelineStartedRef.current = false;
          prevP1StatusRef.current = undefined;
        }}
        onNewProject={() => setModal('create')}
        onLoadProject={() => setModal('load')}
        onLLMSettings={() => setLLMSettingsOpen(true)}
      />

      {/* Center Content */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', background: 'var(--navy)' }}>
        <MiniTopbar
          project={project}
          phases={PHASES}
          statuses={statuses}
          stalePhaseIds={stalePhaseIds}
          onRunPipeline={handleRunPipeline}
          onRerunStale={handleRerunStale}
          pipelineRunning={hasRunning}
          theme={theme}
          onToggleTheme={toggleTheme}
        />
        <div style={{ flex: 1, overflowY: 'auto' }}>
          <div className="fade-up" key={selectedPhaseIdx}>
          <PhaseHeader
            phase={selectedPhase}
            status={selectedStatus}
            tab={tab}
            onTabChange={setTab}
            onExecute={() => handleExecutePhase(selectedPhase.id)}
            pipelineRunning={hasRunning}
            isStale={stalePhaseIds.includes(selectedPhase?.id)}
            pipelineStarted={Object.entries(statuses).some(
              ([k, v]) => k !== 'P1' && (v === 'completed' || v === 'in_progress' || v === 'failed')
            )}
          />
          </div>
          <div style={{ padding: '0 26px 26px' }}>
            {/* ChatView: only for P1 — kept mounted while on P1 so state is preserved */}
            {selectedPhase.id === 'P1' && (
              <div style={{ display: tab === 'chat' ? 'block' : 'none' }}>
                <ChatView
                  project={project}
                  phase={selectedPhase}
                  phaseStatus={statuses['P1'] || 'pending'}
                  pipelineStarted={Object.entries(statuses).some(
                    ([k, v]) => k !== 'P1' && (v === 'completed' || v === 'in_progress')
                  )}
                  messages={chatMessages}
                  onMessages={setChatMessages}
                  onStatusChange={refreshStatuses}
                  onPhaseComplete={() => {
                    if (!pipelineStartedRef.current) {
                      pipelineStartedRef.current = true;
                      handleP1Complete();
                    }
                  }}
                />
              </div>
            )}
            {/* DocumentsView: always mounted, never remounted on phase switch.
                Phase changes propagate via props so the file cache is preserved. */}
            <div style={{ display: tab === 'documents' ? 'block' : 'none' }}>
              <DocumentsView project={project} phase={selectedPhase} status={selectedStatus} pipelineRunning={hasRunning} />
            </div>
          </div>
        </div>
      </div>

      {modal === 'create' && (
        <CreateProjectModal
          onConfirm={handleCreateProject}
          onCancel={() => setModal(null)}
        />
      )}
      {modal === 'load' && (
        <LoadProjectModal
          onSelect={handleLoadProject}
          onCancel={() => setModal(null)}
        />
      )}
      <LLMSettingsModal
        open={llmSettingsOpen}
        onClose={() => setLLMSettingsOpen(false)}
        onSave={handleSaveLLMSettings}
      />
      {toast && <Toast message={toast} />}
    </div>
  );
}
