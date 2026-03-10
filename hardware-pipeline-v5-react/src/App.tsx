import { useState, useEffect, useCallback } from 'react';
import type { Project, Statuses, AppMode, CenterTab } from './types';
import { PHASES, isUnlocked } from './data/phases';
import { api } from './api';
import LandingPage from './components/LandingPage';
import LeftPanel from './components/LeftPanel';
import MiniTopbar from './components/MiniTopbar';
import PhaseHeader from './components/PhaseHeader';
import FlowPanel from './components/FlowPanel';
import CreateProjectModal from './components/CreateProjectModal';
import LoadProjectModal from './components/LoadProjectModal';
import Toast from './components/Toast';
import ChatView from './views/ChatView';
import DetailsView from './views/DetailsView';
import MetricsView from './views/MetricsView';
import DocumentsView from './views/DocumentsView';

export default function App() {
  const [mode, setMode] = useState<AppMode>('landing');
  const [modal, setModal] = useState<'create' | 'load' | null>(null);
  const [project, setProject] = useState<Project | null>(null);
  const [statuses, setStatuses] = useState<Statuses>({});
  const [selectedPhaseIdx, setSelectedPhaseIdx] = useState(0);
  const [tab, setTab] = useState<CenterTab>('details');
  const [toast, setToast] = useState<string | null>(null);
  const [completedIds, setCompletedIds] = useState<string[]>([]);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3000);
  };

  // Poll phase statuses while a project is loaded
  const refreshStatuses = useCallback(async () => {
    if (!project) return;
    try {
      const s = await api.getStatus(project.id);
      setStatuses(s);
      const done = PHASES.filter(p => s[p.id] === 'completed').map(p => p.id);
      setCompletedIds(done);
    } catch (_) { /* silent */ }
  }, [project]);

  useEffect(() => {
    if (!project) return;
    refreshStatuses();
    const hasRunning = Object.values(statuses).some(v => v === 'in_progress');
    const interval = setInterval(refreshStatuses, hasRunning ? 2000 : 5000);
    return () => clearInterval(interval);
  }, [project, refreshStatuses]);

  const handleCreateProject = async (name: string, description: string, design_type: string) => {
    try {
      const p = await api.createProject({ name, description, design_type });
      setProject(p);
      setModal(null);
      setMode('pipeline');
      setSelectedPhaseIdx(0);
      setTab('details');
    } catch (e) {
      showToast('Failed to create project');
    }
  };

  const handleLoadProject = async (p: Project) => {
    setProject(p);
    setModal(null);
    setMode('pipeline');
    // Auto-select first incomplete AI phase
    try {
      const s = await api.getStatus(p.id);
      setStatuses(s);
      const done = PHASES.filter(ph => s[ph.id] === 'completed').map(ph => ph.id);
      setCompletedIds(done);
      const firstIncomplete = PHASES.findIndex(ph => !ph.manual && !done.includes(ph.id));
      setSelectedPhaseIdx(firstIncomplete >= 0 ? firstIncomplete : 0);
    } catch (_) { /* silent */ }
    setTab('details');
  };

  const handleSelectPhase = (idx: number) => {
    const phase = PHASES[idx];
    if (phase.manual) {
      showToast(`Completed externally in ${phase.externalTool || 'external EDA tool'}`);
      return;
    }
    if (!isUnlocked(phase, completedIds) && phase.id !== 'P1') {
      const prevPhase = PHASES[idx - 1];
      showToast(`Complete ${prevPhase.code} — ${prevPhase.name} first`);
      return;
    }
    setSelectedPhaseIdx(idx);
    setTab(phase.id === 'P1' ? 'chat' : 'details');
  };

  const handleRunPhase = async () => {
    if (!project) return;
    const phase = PHASES[selectedPhaseIdx];
    try {
      await api.executePhase(project.id, phase.id);
      refreshStatuses();
    } catch (_) {
      showToast('Failed to start phase');
    }
  };

  const selectedPhase = PHASES[selectedPhaseIdx];
  const selectedStatus = statuses[selectedPhase?.id] || 'pending';

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

  // Pipeline view
  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden', background: 'var(--navy)', fontFamily: "'DM Mono', monospace" }}>
      {/* Left Panel */}
      <LeftPanel
        phases={PHASES}
        selectedIdx={selectedPhaseIdx}
        statuses={statuses}
        completedIds={completedIds}
        onSelect={handleSelectPhase}
        onLanding={() => { setMode('landing'); setProject(null); setStatuses({}); setCompletedIds([]); }}
      />

      {/* Center Content */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', background: '#080c17' }}>
        <MiniTopbar
          project={project}
          phases={PHASES}
          statuses={statuses}
        />
        <div className="fade-up" key={selectedPhaseIdx} style={{ flex: 1, overflowY: 'auto' }}>
          <PhaseHeader
            phase={selectedPhase}
            status={selectedStatus}
            tab={tab}
            onTabChange={setTab}
          />
          <div style={{ padding: '0 26px 26px' }}>
            {tab === 'chat' && selectedPhase.id === 'P1' && (
              <ChatView project={project} phase={selectedPhase} onStatusChange={refreshStatuses} />
            )}
            {tab === 'details' && (
              <DetailsView phase={selectedPhase} />
            )}
            {tab === 'metrics' && (
              <MetricsView phase={selectedPhase} />
            )}
            {tab === 'documents' && (
              <DocumentsView project={project} phase={selectedPhase} status={selectedStatus} />
            )}
          </div>
        </div>
      </div>

      {/* Right Panel — Flow */}
      <FlowPanel
        phase={selectedPhase}
        status={selectedStatus}
        onRun={handleRunPhase}
        onStatusChange={refreshStatuses}
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
    </div>
  );
}
