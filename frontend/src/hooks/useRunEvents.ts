import { useState, useEffect } from 'react';
import { openRunStream, type StreamEvent } from '../lib/api';

/**
 * Accumulates live WebSocket events for a run into local state.
 * Separate from useRunStream (which only invalidates React Query caches).
 * Returns the full event array, capped at maxEvents to prevent memory growth.
 */
export function useRunEvents(runId: string | null, maxEvents = 300): StreamEvent[] {
  const [events, setEvents] = useState<StreamEvent[]>([]);

  useEffect(() => {
    if (!runId) { setEvents([]); return; }
    setEvents([]);

    const stop = openRunStream(runId, (evt) => {
      setEvents((prev) => [...prev.slice(-(maxEvents - 1)), evt]);
    });

    return stop;
  }, [runId, maxEvents]);

  return events;
}
