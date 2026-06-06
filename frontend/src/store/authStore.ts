import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { Agent } from '../types';
import { setAuth, clearAuth } from '../api/client';

interface AuthState {
  agent: Agent | null;
  isAuthenticated: boolean;
  mustChangePassword: boolean;
  setAuth: (agent: Agent, access: string, refresh: string, mustChange?: boolean) => void;
  logout: () => void;
  updateAgent: (agent: Partial<Agent>) => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      agent: null,
      isAuthenticated: false,
      mustChangePassword: false,

      setAuth: (agent, access, refresh, mustChange = false) => {
        setAuth(access, refresh);
        set({ agent, isAuthenticated: true, mustChangePassword: mustChange });
      },

      logout: () => {
        clearAuth();
        set({ agent: null, isAuthenticated: false, mustChangePassword: false });
      },

      updateAgent: (updates) =>
        set((s) => ({ agent: s.agent ? { ...s.agent, ...updates } : null })),
    }),
    {
      name: 'dialeasypro-auth',
      partialize: (s) => ({ agent: s.agent, isAuthenticated: s.isAuthenticated }),
    }
  )
);
