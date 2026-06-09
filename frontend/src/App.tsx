import { lazy, Suspense } from 'react';
import Layout from './components/Layout';
import Sidebar from './components/Sidebar';
import { useAppStore } from './store';
import NewExperiment from './views/NewExperiment';
import Home from './views/Home';
const RunMonitor = lazy(() => import('./views/RunMonitor'));

const Phase1TargetID    = lazy(() => import('./views/Phase1TargetID'));
const Phase2Validation  = lazy(() => import('./views/Phase2Validation'));
const Phase3Routing     = lazy(() => import('./views/Phase3Routing'));
const Phase4Repurposing = lazy(() => import('./views/Phase4Repurposing'));
const Phase5DeNovoSM   = lazy(() => import('./views/Phase5DeNovoSM'));
const Phase6Biologics  = lazy(() => import('./views/Phase6Biologics'));
const Phase7MPO        = lazy(() => import('./views/Phase7MPO'));
const Phase9Packaging  = lazy(() => import('./views/Phase9Packaging'));

const PHASE_VIEWS: Record<number, React.ComponentType> = {
  1: Phase1TargetID,
  2: Phase2Validation,
  3: Phase3Routing,
  4: Phase4Repurposing,
  5: Phase5DeNovoSM,
  6: Phase6Biologics,
  7: Phase7MPO,
  8: Phase9Packaging,
};

function PhaseLoader() {
  return (
    <div className="flex items-center justify-center h-64">
      <span className="material-symbols-outlined text-4xl text-[var(--color-outline)] animate-spin">
        progress_activity
      </span>
    </div>
  );
}

export default function App() {
  const { activeRunId, activePhase, homeTab } = useAppStore();

  // Scene 1 — no active run → home or new-experiment
  if (!activeRunId) {
    return (
      <div className="flex h-dvh w-full relative overflow-hidden">
        <Sidebar />
        <div
          className="flex flex-col flex-1 overflow-hidden h-full"
          style={{ marginLeft: 'var(--spacing-sidebar)' }}
        >
          {homeTab === 'dashboard' ? <Home /> : <NewExperiment />}
        </div>
      </div>
    );
  }

  // Scene 2 — run exists but no phase selected → mission control
  if (activePhase === 0) {
    return (
      <Layout>
        <Suspense fallback={<PhaseLoader />}>
          <RunMonitor />
        </Suspense>
      </Layout>
    );
  }

  // Scene 3 — phase selected → phase results view
  const View = PHASE_VIEWS[activePhase] ?? Phase1TargetID;
  return (
    <Layout>
      <Suspense fallback={<PhaseLoader />}>
        <View />
      </Suspense>
    </Layout>
  );
}
