import { useEffect, useMemo, useState, useSyncExternalStore } from "react";

import { liveSocketUrl } from "./api";
import { LiveStore } from "./store";
import type { LiveMessage } from "./types";

export type Connection = "connecting" | "open" | "closed";

const RECONNECT_MS = 1500;

/** Opens the live WebSocket (truth channel only in Simulation View) and feeds a LiveStore. */
export function useLiveConnection(truth: boolean): { store: LiveStore; connection: Connection } {
  const store = useMemo(() => new LiveStore(), []);
  const [connection, setConnection] = useState<Connection>("connecting");

  useEffect(() => {
    let socket: WebSocket | null = null;
    let retry: ReturnType<typeof setTimeout> | null = null;
    let closed = false;

    const open = () => {
      setConnection("connecting");
      socket = new WebSocket(liveSocketUrl(truth));
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
  }, [store, truth]);

  return { store, connection };
}

/** Re-render when the store publishes (throttled by the store). */
export function useLiveRevision(store: LiveStore): number {
  return useSyncExternalStore(store.subscribe, store.getRevision);
}
