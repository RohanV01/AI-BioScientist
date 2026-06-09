import type { ReactNode } from 'react';
import Sidebar from './Sidebar';
import TopBar from './TopBar';
import Inspector from './Inspector';
import { useAppStore } from '../store';

export default function Layout({ children }: { children: ReactNode }) {
  const inspectorOpen = useAppStore((s) => s.inspectorOpen);

  return (
    <div className="flex h-dvh w-full relative overflow-hidden">
      <Sidebar />
      <div
        className="flex flex-col flex-1 transition-all duration-300"
        style={{ marginLeft: 'var(--spacing-sidebar)' }}
      >
        <TopBar />
        <main
          className="flex-1 overflow-y-auto pt-16 transition-all duration-300"
          style={{
            paddingRight: inspectorOpen ? 'var(--spacing-inspector)' : '0',
          }}
        >
          <div className="p-6">{children}</div>
        </main>
      </div>
      <Inspector />
    </div>
  );
}
