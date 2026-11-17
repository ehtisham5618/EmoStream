import { useSyncExternalStore } from "react";

/** Tiny external store: keeps shared UI state without adding a state library. */
export function createStore<T>(initial: T) {
  let state = initial;
  const listeners = new Set<() => void>();
  return {
    get: () => state,
    set(next: Partial<T> | ((s: T) => Partial<T>)) {
      const patch = typeof next === "function" ? next(state) : next;
      state = { ...state, ...patch };
      listeners.forEach((l) => l());
    },
    subscribe(l: () => void) {
      listeners.add(l);
      return () => listeners.delete(l);
    },
  };
}

export function useStore<T, S>(store: ReturnType<typeof createStore<T>>, selector: (s: T) => S, serverValue?: T): S {
  return useSyncExternalStore(
    store.subscribe,
    () => selector(store.get()),
    () => selector(serverValue ?? store.get()),
  );
}
