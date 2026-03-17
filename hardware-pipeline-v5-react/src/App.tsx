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
import Toast from './components/Toast';
import ChatView from './views/ChatView';
import DocumentsView from './views/DocumentsView';

export default function App() {
  const [mode, setMode] = useState<AppMode>('landing');
  const [modal, setModal] = useState<'create' | 'load' | null>(null);
  const [project, setProject] = useState<Project | null>(null);
  const [statuses, setStatuses] = useState<Statuses>({});
  const [selectedPhaseIdx, setSelectedPhaseIdx] = useState(0);
  const [tab, setTab] = useState<CenterTab>('documents');
  const [toast, setToast] = useState<string | null>(null);
  const [completedIds, setCompletedIds] = useState<string[]>([]);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  // Raw status entries with updated_at timestamps — used for staleness detection
  const [statusesRaw, setStatusesRaw] = useState<StatusesRaw>({});

  // Reactive polling speed — 2s when running, 5s when idle
  const [hasRunning, setHasRunning] = useState(false);

  // Refs to prevent duplicate pipeline starts
  const pipelineStartedRef = useRef(false);
  const prevP1StatusRef = useRef<string | undefined>(undefined);

  // Ref to handleP1Complete so refreshStatuses can call it without circular dep
  const handleP1CompleteRef = useRef<() => void>(() => {});

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

      setStatuses(s);
      setStatusesRaw(raw);
      const done = PHASES.filter(p => s[p.id] === 'completed').map(p => p.id);
      setCompletedIds(done);
      const running = Object.values(s).some(v => v === 'in_progress');
      setHasRunning(running);

      // NOTE: We no longer auto-start the pipeline from the status poll.
      // The user must explicitly click "Approve & Start Pipeline" in ChatView.
      // Auto-start only happens when loading an existing project (handleLoadProject).
    } catch (_) { /* silent */ }
  }, [project]);

  // Reactive polling: re-creates interval when hasRunning changes
  useEffect(() => {
    if (!project) return;
    refreshStatuses();
    const interval = setInterval(refreshStatuses, hasRunning ? 2000 : 8000);
    return () => clearInterval(interval);
  }, [project, refreshStatuses, hasRunning]);

  // Auto-advance: when any phase becomes in_progress, jump to it in the left panel
  // so the right panel shows live details for the running phase.
  useEffect(() => {
    if (!project) return;
    const runningIdx = PHASES.findIndex(p => statuses[p.id] === 'in_progress');
    if (runningIdx >= 0 && runningIdx !== selectedPhaseIdx) {
      setSelectedPhaseIdx(runningIdx);
    }
  }, [statuses]);

  // Called by ChatView "Approve & Start Pipeline" button,
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
      // Force fast polling immediately — don't wait 5s for the interval to notice
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

  // Reset pipeline-started guard when project changes
  useEffect(() => {
    pipelineStartedRef.current = false;
    prevP1StatusRef.current = undefined;
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

  const handleRunPipeline = useCallback(async () => {
    if (!project) return;
    try {
      await api.runPipeline(project.id);
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
    setChatMessages([]);
    pipelineStartedRef.current = false;
    prevP1StatusRef.current = undefined;
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
      setTab(PHASES[idx].id === 'P1' ? 'chat' : 'details');

      // Auto-start pipeline if P1 is done but P2-P8 are all still pending
      // (handles page reload or returning to a partially-run project)
      const autoPhaseIds = ['P2', 'P3', 'P4', 'P6', 'P8a', 'P8b', 'P8c'];
      const p2Plus = autoPhaseIds.map(id => s[id] || 'pending');
      const noneStarted = p2Plus.every(st => st === 'pending' || st === 'failed');
      if (s['P1'] === 'completed' && noneStarted && !running) {
        pipelineStartedRef.current = true;
        // Slight delay so state settles before firing
        setTimeout(() => {
          api.runPipeline(p.id)
            .then(() => { setHasRunning(true); })
            .catch(() => { /* user can click Run Pipeline in topbar */ });
        }, 800);
      }
    } catch (_) { setTab('documents'); }
  };

  const handleSelectPhase = (idx: number) => {
    const phase = PHASES[idx];
    if (phase.manual) {
      showToast(`Completed externally in ${phase.externalTool || 'external EDA tool'}`);
      return;
    }
    if (!isUnlocked(phase, completedIds) && phase.id !== 'P1') {
      // Find the actual blocking AI phase (skip manual phases in the chain)
      const blockingPhase = [...PHASES].slice(0, idx).reverse().find(p => !p.manual);
      const toastMsg = blockingPhase
        ? `Complete ${blockingPhase.code} \u2014 ${blockingPhase.name} first`
        : 'Complete the previous phase first';
      showToast(toastMsg);
      return;
    }
    setSelectedPhaseIdx(idx);
    setTab(phase.id === 'P1' ? 'chat' : 'documents');
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
      />

      {/* Center Content */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', background: '#080c17' }}>
        <MiniTopbar
          project={project}
          phases={PHASES}
          statuses={statuses}
          onRunPipeline={handleRunPipeline}
          pipelineRunning={hasRunning}
        />
        <div className="fade-up" key={selectedPhaseIdx} style={{ flex: 1, overflowY: 'auto' }}>
          <PhaseHeader
            phase={selectedPhase}
            status={selectedStatus}
            tab={tab}
            onTabChange={setTab}
            onExecute={() => handleExecutePhase(selectedPhase.id)}
            pipelineRunning={hasRunning}
            isStale={stalePhaseIds.includes(selectedPhase?.id)}
          />
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
            {/* DocumentsView: always mounted for the active phase, hidden when on chat tab.
                This prevents the file list and content cache from being lost when switching
                between the Chat and Documents tabs. */}
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
      {toast && <Toast message={toast} />}
    </div>
  );
}
