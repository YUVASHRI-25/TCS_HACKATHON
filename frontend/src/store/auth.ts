import { create } from "zustand";
import type { Schemas } from "@/api/client";

export type User = Schemas["UserOut"];

interface AuthState {
  token: string | null;
  user: User | null;
  signIn: (token: string, user: User) => void;
  signOut: () => void;
}

const KEY = "trace.session";

function load(): { token: string | null; user: User | null } {
  try {
    const raw = sessionStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as { token: string; user: User }) : { token: null, user: null };
  } catch {
    return { token: null, user: null };
  }
}

/** Session token lives in sessionStorage: it ends when the tab closes. */
export const useAuth = create<AuthState>((set) => ({
  ...load(),
  signIn: (token, user) => {
    try {
      sessionStorage.setItem(KEY, JSON.stringify({ token, user }));
    } catch {
      /* storage unavailable: keep in memory */
    }
    set({ token, user });
  },
  signOut: () => {
    try {
      sessionStorage.removeItem(KEY);
    } catch {
      /* ignore */
    }
    set({ token: null, user: null });
  },
}));
