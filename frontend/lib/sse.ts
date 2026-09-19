"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { API_BASE, getAccessToken, refreshAccessToken } from "./api";
import type { TimelineEvent } from "./types";

export type StreamState = "connecting" | "open" | "retrying" | "closed" | "error";

function parseBlock(block: string): { id?: string; data?: string } {
  const result: { id?: string; data?: string } = {};
  const data: string[] = [];
  for (const line of block.split(/\r?\n/)) {
    if (line.startsWith("id:")) result.id = line.slice(3).trim();
    if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
  }
  if (data.length) result.data = data.join("\n");
  return result;
}

export function useEventStream(filters: Record<string, string | undefined> = {}) {
  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [state, setState] = useState<StreamState>("connecting");
  const [retryCount, setRetryCount] = useState(0);
  const lastEventId = useRef<string | undefined>(undefined);
  const stableQuery = useMemo(
    () =>
      Object.entries(filters)
        .filter((entry): entry is [string, string] => Boolean(entry[1]))
        .sort(([left], [right]) => left.localeCompare(right)),
    [filters],
  );
  const queryKey = JSON.stringify(stableQuery);

  useEffect(() => {
    const controller = new AbortController();
    let stopped = false;
    let attempt = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let authRetried = false;
    lastEventId.current = undefined;

    const connect = async (): Promise<void> => {
      if (stopped) return;
      setState(attempt === 0 ? "connecting" : "retrying");
      const params = new URLSearchParams(stableQuery);
      const token = getAccessToken();
      const headers = new Headers({ Accept: "text/event-stream" });
      if (token) headers.set("Authorization", `Bearer ${token}`);
      if (lastEventId.current) headers.set("Last-Event-ID", lastEventId.current);

      try {
        const response = await fetch(`${API_BASE}/events/stream?${params.toString()}`, {
          headers,
          cache: "no-store",
          signal: controller.signal,
        });
        if (response.status === 401 && !authRetried) {
          authRetried = true;
          const refreshed = await refreshAccessToken();
          if (stopped) return;
          if (refreshed) return connect();
        }
        if (response.status === 401 || response.status === 403) {
          setState("error");
          return;
        }
        if (!response.ok || !response.body) throw new Error(`SSE returned ${response.status}`);
        setState("open");
        authRetried = false;
        attempt = 0;
        setRetryCount(0);
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (!stopped) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const blocks = buffer.split(/\r?\n\r?\n/);
          buffer = blocks.pop() ?? "";
          for (const raw of blocks) {
            const parsed = parseBlock(raw);
            if (parsed.id) lastEventId.current = parsed.id;
            if (!parsed.data) continue;
            try {
              const event = JSON.parse(parsed.data) as TimelineEvent;
              setEvents((current) => current.some((item) => item.event_id === event.event_id)
                ? current : [event, ...current].slice(0, 100));
            } catch {
              // Heartbeats and non-JSON control frames are intentionally ignored.
            }
          }
        }
        if (!stopped) throw new Error("SSE connection closed");
      } catch (error) {
        if (stopped || (error instanceof DOMException && error.name === "AbortError")) return;
        attempt += 1;
        setRetryCount(attempt);
        setState("retrying");
        const delay = Math.min(30_000, 1_000 * 2 ** Math.min(attempt - 1, 5));
        timer = setTimeout(() => void connect(), delay);
      }
    };

    queueMicrotask(() => {
      if (stopped) return;
      setEvents([]);
      void connect();
    });
    return () => {
      stopped = true;
      controller.abort();
      if (timer) clearTimeout(timer);
      setState("closed");
    };
    // stableQuery is represented by queryKey to avoid reconnecting on object identity changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queryKey]);

  return { events, state, retryCount, clear: () => setEvents([]) };
}
