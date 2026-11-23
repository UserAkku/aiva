import { useCallback, useEffect, useRef, useState } from "react";

export interface BusEvent {
  type: string;
  ts: number;
  [key: string]: any;
}

/** Live event stream from the server's event bus (/api/events), with auto-reconnect. */
export function useEvents(max = 300): BusEvent[] {
  const [events, setEvents] = useState<BusEvent[]>([]);
  useEffect(() => {
    let ws: WebSocket | null = null;
    let timer = 0;
    let stopped = false;
    const connect = () => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${location.host}/api/events`);
      ws.onmessage = (e) => {
        const data = JSON.parse(e.data);
        if (data.type === "hello") setEvents(data.recent ?? []);
        else setEvents((prev) => [...prev.slice(-(max - 1)), data]);
      };
      ws.onclose = () => {
        if (!stopped) timer = window.setTimeout(connect, 2000);
      };
    };
    connect();
    return () => {
      stopped = true;
      clearTimeout(timer);
      ws?.close();
    };
  }, [max]);
  return events;
}

/** Fetch on mount + whenever `deps` change; exposes reload(). */
export function useLoad<T>(loader: () => Promise<T>, deps: unknown[] = [], intervalMs = 0) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const loaderRef = useRef(loader);
  loaderRef.current = loader;
  const reload = useCallback(async () => {
    try {
      setData(await loaderRef.current());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    void reload();
    if (!intervalMs) return;
    const id = window.setInterval(() => void reload(), intervalMs);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reload, intervalMs, ...deps]);
  return { data, error, loading, reload, setData };
}
