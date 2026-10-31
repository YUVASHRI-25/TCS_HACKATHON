import { create } from "zustand";

interface UiState {
  paletteOpen: boolean;
  setPalette: (open: boolean) => void;
  evidence: { caseId: string; eid: string } | null;
  openEvidence: (caseId: string, eid: string) => void;
  closeEvidence: () => void;
  reviewer: string;
  setReviewer: (name: string) => void;
  chatCase: string | null;
  openChat: (caseId: string) => void;
  closeChat: () => void;
}

const savedReviewer = (() => {
  try {
    return localStorage.getItem("trace.reviewer") ?? "";
  } catch {
    return "";
  }
})();

export const useUi = create<UiState>((set) => ({
  paletteOpen: false,
  setPalette: (paletteOpen) => set({ paletteOpen }),
  evidence: null,
  openEvidence: (caseId, eid) => set({ evidence: { caseId, eid } }),
  closeEvidence: () => set({ evidence: null }),
  chatCase: null,
  openChat: (chatCase) => set({ chatCase }),
  closeChat: () => set({ chatCase: null }),
  reviewer: savedReviewer,
  setReviewer: (reviewer) => {
    try {
      localStorage.setItem("trace.reviewer", reviewer);
    } catch {
      /* storage unavailable: keep in memory only */
    }
    set({ reviewer });
  },
}));
