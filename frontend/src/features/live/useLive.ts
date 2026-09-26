import { useEffect, useMemo, useState, useSyncExternalStore } from "react";

import { liveSocketUrl } from "./api";
import { LiveStore } from "./store";
import type { LiveMessage } from "./types";

export type Connection = "connecting" | "open" | "closed";

const RECONNECT_MS = 1500;

/**
 * Opens the live WebSocket (truth channel only in Simulation View) and feeds a LiveStore.
 * Live Simulation v2 passes its own socket path and store class.
 */
export function useLiveConnection<S extends LiveStore = LiveStore>(
  truth: boolean,
  options: { path?: string; createStore?: () => S } = {},
): { store: S; connection: Connection } {
  const { path = "/ws/live", createStore } = options;
  // eslint-disable-next-line react-hooks/exhaustive-deps -- the store lives for the page's lifetime
  const store = useMemo(() => (createStore ? createStore() : new LiveStore()) as S, []);
  const [connection, setConnection] = useState<Connection>("connecting");

  useEffect(() => {
    let socket: WebSocket | null = null;
    let retry: ReturnType<typeof setTimeout> | null = null;
    let closed = false;

    const open = () => {
      setConnection("connecting");
      socket = new WebSocket(liveSocketUrl(truth, path));
      socket.onopen = () => setConnection("open");
      socket.onmessage = (event: MessageEvent<string>) => store.apply(JSON.parse(event.data) as LiveMessage);
      socket.onclose = () => {
        setConnection("closed");
        if (!closed) retry = setTimeout(open, RECONNECT_MS);
      };
    };
    open();
    return () => {
      closed = true;
      if (retry) clearTimeout(retry);
      socket?.close();
    };
  }, [store, truth, path]);

  return { store, connection };
}

/** Re-render when the store publishes (throttled by the store). */
export function useLiveRevision(store: LiveStore): number {
  return useSyncExternalStore(store.subscribe, store.getRevision);
}
