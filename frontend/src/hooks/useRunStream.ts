import { useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { openRunStream, type StreamEvent } from '../lib/api';

/**
 * Subscribe to a run's WebSocket event stream.
 * Automatically invalidates React Query caches when relevant events arrive.
 * Safe to call when runId is null (no-ops).
 */
export function useRunStream(runId: string | null) {
  const qc = useQueryClient();
  const stopRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    if (!runId) return;

    const stop = openRunStream(runId, (evt: StreamEvent) => {
      switch (evt.type) {
        case 'targets_ready':
          qc.invalidateQueries({ queryKey: ['targets', runId] });
          break;

        case 'phase':
          // Refresh run detail so phase status pills update
          qc.invalidateQueries({ queryKey: ['run', runId] });
          qc.invalidateQueries({ queryKey: ['runs'] });
          if ((evt.status as string) === 'completed') {
            // Phase output is now available — refresh candidates if relevant
            qc.invalidateQueries({ queryKey: ['candidates', runId] });
          }
          break;

        case 'run':
          qc.invalidateQueries({ queryKey: ['run', runId] });
          qc.invalidateQueries({ queryKey: ['runs'] });
          if ((evt.status as string) === 'completed') {
            qc.invalidateQueries({ queryKey: ['targets', runId] });
            qc.invalidateQueries({ queryKey: ['candidates', runId] });
            qc.invalidateQueries({ queryKey: ['compute', runId] });
          }
          break;

        default:
          break;
      }
    });

    stopRef.current = stop;
    return () => stop();
  }, [runId, qc]);
}
