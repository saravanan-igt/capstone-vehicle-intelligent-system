"use client";

import { useCallback, useEffect, useState } from "react";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly details: unknown,
    public readonly correlationId: string | null,
  ) {
    super(message);
  }
}

type Options = {
  method?: "GET" | "POST" | "PATCH";
  json?: unknown;
  file?: File;
  headers?: Record<string, string>;
};

export async function api<T>(path: string, opts: Options = {}): Promise<T> {
  const res = await fetch(`/api/bff/${path.replace(/^\//, "")}`, {
    method: opts.method ?? "GET",
    headers: {
      "X-Requested-With": "vla",
      ...(opts.json !== undefined
        ? { "Content-Type": "application/json" }
        : {}),
      ...(opts.file
        ? {
            "Content-Type": opts.file.type,
            "X-Filename": encodeURIComponent(opts.file.name),
          }
        : {}),
      ...opts.headers,
    },
    body:
      opts.file ??
      (opts.json !== undefined ? JSON.stringify(opts.json) : undefined),
    cache: "no-store",
    credentials: "same-origin",
  });
  const text = await res.text();
  const body: unknown = text ? JSON.parse(text) : null;
  if (!res.ok) {
    const err = (
      body as {
        error?: {
          code?: string;
          message?: string;
          details?: unknown;
          correlation_id?: string;
        };
      }
    )?.error;
    throw new ApiError(
      res.status,
      err?.code ?? "HTTP_ERROR",
      err?.message ?? `Request failed (${res.status})`,
      err?.details,
      err?.correlation_id ?? null,
    );
  }
  return body as T;
}

export function useApi<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState<boolean>(path !== null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    if (path === null) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    api<T>(path)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        if (e instanceof ApiError && e.status === 401) {
          window.location.href = "/login";
          return;
        }
        setError(
          e instanceof ApiError
            ? e
            : new ApiError(0, "NETWORK", "Network error", null, null),
        );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [path, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return { data, error, loading, reload, setData };
}
