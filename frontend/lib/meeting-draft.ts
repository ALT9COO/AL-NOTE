import type { CalendarEvent, MeetingParseResult } from "@/types";

export const DRAFT_STORAGE_KEY = "alnote_meeting_draft";

export type LocalDraft = {
  draftId: number | null;
  step: number;
  transcript: string;
  parsed: MeetingParseResult | null;
  event: CalendarEvent | null;
};

export function readLocalDraft(): LocalDraft | null {
  try {
    const raw = window.localStorage.getItem(DRAFT_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as LocalDraft) : null;
  } catch {
    return null;
  }
}

export function writeLocalDraft(draft: LocalDraft) {
  try {
    if (!draft.transcript.trim() && draft.step <= 1 && !draft.event && !draft.draftId) {
      window.localStorage.removeItem(DRAFT_STORAGE_KEY);
      return;
    }
    window.localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(draft));
  } catch {
    /* quota / private mode */
  }
}

export function clearLocalDraft() {
  try {
    window.localStorage.removeItem(DRAFT_STORAGE_KEY);
  } catch {
    /* ignore */
  }
}
