import { createClient } from "redis";

// Server-side session/transaction storage. Redis in shared deployments; in-memory only for a single local process.
export interface SessionStore {
  get<T>(key: string): Promise<T | null>;
  set(key: string, value: unknown, ttlSeconds: number): Promise<void>;
  take<T>(key: string): Promise<T | null>;
  del(key: string): Promise<void>;
}

class MemoryStore implements SessionStore {
  private data = new Map<string, { value: string; expires: number }>();

  async get<T>(key: string): Promise<T | null> {
    const hit = this.data.get(key);
    if (!hit) return null;
    if (hit.expires < Date.now()) {
      this.data.delete(key);
      return null;
    }
    return JSON.parse(hit.value) as T;
  }

  async set(key: string, value: unknown, ttlSeconds: number): Promise<void> {
    this.data.set(key, {
      value: JSON.stringify(value),
      expires: Date.now() + ttlSeconds * 1000,
    });
  }

  async take<T>(key: string): Promise<T | null> {
    const value = await this.get<T>(key);
    this.data.delete(key);
    return value;
  }

  async del(key: string): Promise<void> {
    this.data.delete(key);
  }
}

class RedisStore implements SessionStore {
  private client: ReturnType<typeof createClient>;
  private ready: Promise<unknown>;

  constructor(url: string) {
    this.client = createClient({ url });
    this.client.on("error", () => undefined);
    this.ready = this.client.connect();
  }

  async get<T>(key: string): Promise<T | null> {
    await this.ready;
    const raw = await this.client.get(key);
    return raw ? (JSON.parse(raw) as T) : null;
  }

  async set(key: string, value: unknown, ttlSeconds: number): Promise<void> {
    await this.ready;
    await this.client.set(key, JSON.stringify(value), { EX: ttlSeconds });
  }

  async take<T>(key: string): Promise<T | null> {
    await this.ready;
    const raw = await this.client.getDel(key);
    return raw ? (JSON.parse(raw) as T) : null;
  }

  async del(key: string): Promise<void> {
    await this.ready;
    await this.client.del(key);
  }
}

const holder = globalThis as unknown as { __vlaStore?: SessionStore };

export function sessionStore(): SessionStore {
  if (!holder.__vlaStore) {
    const url = process.env.REDIS_SESSION_URL;
    holder.__vlaStore = url ? new RedisStore(url) : new MemoryStore();
  }
  return holder.__vlaStore;
}
