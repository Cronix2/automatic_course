import { create } from "zustand";
import { api } from "../api/client";

export interface CategoryStatus { ok: boolean; message: string; }
export interface SettingsStatus {
  thm: CategoryStatus;
  providers: CategoryStatus;
  local_models: CategoryStatus;
  overall_ok: boolean;
}

interface State {
  status: SettingsStatus | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}

export const useSettingsStore = create<State>((set) => ({
  status: null,
  loading: false,
  error: null,
  refresh: async () => {
    set({ loading: true, error: null });
    try {
      const s = await api<SettingsStatus>("/api/settings/status");
      set({ status: s, loading: false });
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
    }
  },
}));
