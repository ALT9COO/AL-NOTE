import axios, { AxiosError } from "axios";

import type {
  AdminDepartment,
  AdminDepartmentPayload,
  AdminUser,
  AdminUserCreatePayload,
  AdminUserUpdatePayload,
  AgendaSubmitResult,
  AiProvider,
  AiStatus,
  AnalyticsSummary,
  CalendarApp,
  CalendarAppPayload,
  CalendarConnection,
  CalendarEventCreated,
  CalendarEventCreatePayload,
  CalendarEventsResult,
  Collaborator,
  ConnectionTestResult,
  Department,
  IntegrationList,
  IntegrationPayload,
  LoginResponse,
  Meeting,
  MeetingDraft,
  MeetingParseResult,
  Period,
  ReportEmailResult,
  ReportResult,
  SavedReportSummary,
  Task,
  TaskAlert,
  TaskPayload,
  TaskStatus,
  TaskUpdateProposal,
  UsageSummary,
  User,
} from "@/types";

export const TOKEN_KEY = "ainote_token";
export const USER_ID_KEY = "ainote_user_id";
export const REMEMBER_KEY = "ainote_remember";

export function getStoredToken() {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY) ?? window.sessionStorage.getItem(TOKEN_KEY);
}

export function setStoredToken(token: string, remember: boolean) {
  window.localStorage.removeItem(TOKEN_KEY);
  window.sessionStorage.removeItem(TOKEN_KEY);
  const store = remember ? window.localStorage : window.sessionStorage;
  store.setItem(TOKEN_KEY, token);
  window.localStorage.setItem(REMEMBER_KEY, remember ? "1" : "0");
}

export function clearStoredToken() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(TOKEN_KEY);
  window.sessionStorage.removeItem(TOKEN_KEY);
}

function apiBaseUrl() {
  // 브라우저는 화면 주소(3001)만 사용한다. /api 는 Next 가 내부 FastAPI 로 넘긴다.
  if (typeof window !== "undefined") {
    return "";
  }
  return process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
}

export const api = axios.create({
  headers: { "Content-Type": "application/json" },
});

api.interceptors.request.use((config) => {
  config.baseURL = apiBaseUrl();
  if (typeof window !== "undefined") {
    const token = getStoredToken();
    if (token) config.headers.Authorization = `Bearer ${token}`;
  }
  if (config.responseType === "blob") {
    config.headers.setContentType(null, false);
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401 && typeof window !== "undefined") {
      clearStoredToken();
      if (!window.location.pathname.startsWith("/login")) {
        window.location.href = "/login?reason=expired";
      }
    }
    return Promise.reject(error);
  },
);

function apiErrorDetail(error: unknown): unknown {
  if (!axios.isAxiosError(error)) return undefined;
  const data = error.response?.data as { detail?: unknown } | Blob | string | undefined;
  if (typeof Blob !== "undefined" && data instanceof Blob) return undefined;
  if (typeof data === "string") {
    try {
      return (JSON.parse(data) as { detail?: unknown }).detail;
    } catch {
      return data;
    }
  }
  return data && typeof data === "object" ? data.detail : undefined;
}

/** Axios 오류에서 백엔드의 detail 메시지를 추출한다. */
export function apiErrorMessage(error: unknown, fallback = "요청 처리 중 오류가 발생했습니다.") {
  if (axios.isAxiosError(error)) {
    const detail = apiErrorDetail(error);
    if (typeof detail === "string" && detail.trim()) return detail;
    if (detail && typeof detail === "object" && "message" in detail) {
      const message = (detail as { message?: unknown }).message;
      if (typeof message === "string" && message.trim()) return message;
    }
    if (error.code === "ERR_NETWORK" || error.code === "ECONNABORTED") {
      return "백엔드 서버에 연결할 수 없습니다. 서버가 꺼져 있거나, 큰 파일 처리 중 연결이 끊긴 경우입니다.";
    }
  }
  return fallback;
}

/** 전사는 실패했지만 음성 파일은 초안으로 보관된 경우. */
export function transcribeArchiveFromError(error: unknown): {
  draft_id: number;
  message: string;
} | null {
  const detail = apiErrorDetail(error);
  if (!detail || typeof detail !== "object") return null;
  const draftId = Number((detail as { draft_id?: unknown }).draft_id);
  if (!Number.isFinite(draftId) || draftId <= 0) return null;
  const message = (detail as { message?: unknown }).message;
  return {
    draft_id: draftId,
    message:
      typeof message === "string" && message.trim()
        ? message
        : "음성 파일을 회의실에 보관했습니다.",
  };
}

export type TranscriptResult = {
  transcript: string;
  mock: boolean;
  draft_id?: number | null;
  has_audio?: boolean;
  audio_name?: string | null;
  audio_size?: number | null;
  stt_status?: string;
  stt_error?: string | null;
};

/** 업로드 직후 전사가 백그라운드면 초안 상태를 폴링한다. */
export async function finishTranscription(result: TranscriptResult): Promise<TranscriptResult> {
  if (result.stt_status !== "transcribing" || !result.draft_id) return result;
  const draft = await meetingApi.waitForStt(result.draft_id);
  return {
    transcript: draft.transcript ?? "",
    mock: Boolean(draft.stt_mock),
    draft_id: draft.draft_id,
    has_audio: draft.has_audio,
    audio_name: draft.audio_name,
    audio_size: draft.audio_size,
    stt_status: draft.stt_status,
    stt_error: draft.stt_error,
  };
}

// --------------------------------------------------------------------------- //
// Auth
// --------------------------------------------------------------------------- //
export const authApi = {
  login: (user_id: string, password: string, remember = true) =>
    api
      .post<LoginResponse>("/api/auth/login", { user_id, password, remember })
      .then((r) => r.data),
  me: () => api.get<User>("/api/auth/me").then((r) => r.data),
  changePassword: (current_password: string, new_password: string) =>
    api
      .post<{ message: string }>("/api/auth/password", { current_password, new_password })
      .then((r) => r.data),
  users: () => api.get<User[]>("/api/auth/users").then((r) => r.data),
  departments: () => api.get<Department[]>("/api/auth/departments").then((r) => r.data),
};

// --------------------------------------------------------------------------- //
// Tasks
// --------------------------------------------------------------------------- //
export const taskApi = {
  list: (scope: "mine" | "team" = "mine") =>
    api.get<Task[]>("/api/tasks", { params: { scope } }).then((r) => r.data),
  get: (taskId: string) => api.get<Task>(`/api/tasks/${taskId}`).then((r) => r.data),
  create: (payload: TaskPayload) => api.post<Task>("/api/tasks", payload).then((r) => r.data),
  update: (taskId: string, payload: Partial<TaskPayload>) =>
    api.patch<Task>(`/api/tasks/${taskId}`, payload).then((r) => r.data),
  updateStatus: (taskId: string, status: TaskStatus, progress?: number) =>
    api
      .patch<Task>(`/api/tasks/${taskId}/status`, { status, progress })
      .then((r) => r.data),
  addComment: (taskId: string, body: string) =>
    api.post<Task>(`/api/tasks/${taskId}/comments`, { body }).then((r) => r.data),
  remove: (taskId: string) => api.delete(`/api/tasks/${taskId}`).then(() => undefined),
  listDeleted: () => api.get<Task[]>("/api/tasks/deleted").then((r) => r.data),
  restore: (taskId: string) =>
    api.post<Task>(`/api/tasks/${taskId}/restore`).then((r) => r.data),
  alerts: () => api.get<TaskAlert[]>("/api/tasks/alerts").then((r) => r.data),
};

// --------------------------------------------------------------------------- //
// Meetings
// --------------------------------------------------------------------------- //
export const meetingApi = {
  transcribe: (file: Blob, filename = "recording.webm") => {
    const form = new FormData();
    form.append("file", file, filename);
    return api
      .post<TranscriptResult>(
        "/api/meetings/transcribe",
        form,
        {
        headers: { "Content-Type": "multipart/form-data" },
        timeout: 10 * 60 * 1000,
        maxBodyLength: Infinity,
        maxContentLength: Infinity,
      },
      )
      .then((r) => r.data);
  },
  parse: (transcript: string, context?: { event_title?: string; attendees?: string[] }) =>
    api
      .post<MeetingParseResult>("/api/meetings/parse", { transcript, ...context })
      .then((r) => r.data),
  submit: (payload: {
    title: string;
    transcript: string;
    summary_bullets: string[];
    agenda_items: MeetingParseResult["agenda_items"];
    action_items: MeetingParseResult["action_items"];
    risks: string[];
    task_updates: TaskUpdateProposal[];
    event_key?: string | null;
    event_start?: string | null;
    event_location?: string | null;
    participants?: Collaborator[];
    viewers?: Collaborator[];
    draft_id?: number | null;
  }) => api.post<AgendaSubmitResult>("/api/meetings/submit", payload).then((r) => r.data),
  list: () => api.get<Meeting[]>("/api/meetings").then((r) => r.data),
  get: (meetingId: number) => api.get<Meeting>(`/api/meetings/${meetingId}`).then((r) => r.data),
  listDrafts: () => api.get<MeetingDraft[]>("/api/meetings/drafts").then((r) => r.data),
  getDraft: (draftId: number) =>
    api.get<MeetingDraft>(`/api/meetings/drafts/${draftId}`).then((r) => r.data),
  retryTranscribe: (draftId: number) =>
    api.post<MeetingDraft>(`/api/meetings/drafts/${draftId}/transcribe`).then((r) => r.data),
  waitForStt: async (draftId: number) => {
    const deadline = Date.now() + 10 * 60 * 1000;
    while (Date.now() < deadline) {
      const draft = await meetingApi.getDraft(draftId);
      if (draft.stt_status !== "transcribing") return draft;
      await new Promise((resolve) => setTimeout(resolve, 2000));
    }
    throw new Error("전사 대기 시간이 초과되었습니다.");
  },
  createDraft: (payload: {
    title?: string;
    transcript: string;
    parsed?: MeetingParseResult | null;
    event?: unknown;
    step?: number;
  }) => api.post<MeetingDraft>("/api/meetings/drafts", payload).then((r) => r.data),
  updateDraft: (
    draftId: number,
    payload: {
      title?: string;
      transcript?: string;
      parsed?: MeetingParseResult | null;
      event?: unknown;
      step?: number;
    },
  ) => api.patch<MeetingDraft>(`/api/meetings/drafts/${draftId}`, payload).then((r) => r.data),
  deleteDraft: (draftId: number) =>
    api.delete(`/api/meetings/drafts/${draftId}`).then(() => undefined),
  updateAccess: (meetingId: number, payload: { participants: Collaborator[]; viewers: Collaborator[] }) =>
    api
      .patch<Meeting>(`/api/meetings/${meetingId}/access`, payload)
      .then((r) => r.data),
  audioBlob: async (kind: "meeting" | "draft", id: number) => {
    const response = await api.get<Blob>(
      kind === "draft" ? `/api/meetings/drafts/${id}/audio` : `/api/meetings/${id}/audio`,
      {
        responseType: "blob",
        headers: { Accept: "audio/*,application/octet-stream" },
      },
    );
    const blob = response.data;
    const mime = String(response.headers["content-type"] || blob.type || "");
    if (mime.includes("json") || mime.includes("text/html")) {
      const text = await blob.text();
      try {
        const parsed = JSON.parse(text) as { detail?: unknown };
        const detail = parsed.detail;
        const message =
          typeof detail === "string"
            ? detail
            : detail && typeof detail === "object" && "message" in detail
              ? String((detail as { message?: unknown }).message || "음성을 불러오지 못했습니다.")
              : "음성을 불러오지 못했습니다.";
        throw new Error(message);
      } catch (error) {
        if (error instanceof Error && error.message !== "음성을 불러오지 못했습니다.") throw error;
        throw new Error("음성을 불러오지 못했습니다.");
      }
    }
    return blob.type ? blob : new Blob([blob], { type: mime.split(";")[0] || "audio/webm" });
  },
};

// --------------------------------------------------------------------------- //
// Calendar (사용자별 Microsoft 365 연동)
// --------------------------------------------------------------------------- //
export function calendarRedirectUri() {
  if (typeof window === "undefined") return "";
  return `${window.location.origin}/api/calendar/callback`;
}

export const calendarApi = {
  connection: () => api.get<CalendarConnection>("/api/calendar/connection").then((r) => r.data),
  loginUrl: (redirectUri?: string) =>
    api
      .get<{ url: string; expires_in: number }>("/api/calendar/login-url", {
        params: {
          redirect_uri: redirectUri || calendarRedirectUri(),
          origin: typeof window !== "undefined" ? window.location.origin : undefined,
        },
      })
      .then((r) => r.data),
  disconnect: () => api.delete("/api/calendar/connection").then(() => undefined),
  sync: () => api.post<CalendarConnection>("/api/calendar/sync").then((r) => r.data),
  events: (params: { days_back?: number; days_ahead?: number; sample?: boolean }) =>
    api.get<CalendarEventsResult>("/api/calendar/events", { params }).then((r) => r.data),
  createEvent: (payload: CalendarEventCreatePayload) =>
    api.post<CalendarEventCreated>("/api/calendar/events", payload).then((r) => r.data),
  // ADMIN — Azure 앱 등록 정보
  app: () => api.get<CalendarApp>("/api/calendar/app").then((r) => r.data),
  saveApp: (payload: CalendarAppPayload) =>
    api.put<CalendarApp>("/api/calendar/app", payload).then((r) => r.data),
  deleteApp: () => api.delete("/api/calendar/app").then(() => undefined),
};

// --------------------------------------------------------------------------- //
// Analytics & system
// --------------------------------------------------------------------------- //
export const analyticsApi = {
  summary: (period: Period, deptId?: number | null) =>
    api
      .get<AnalyticsSummary>("/api/analytics/summary", {
        params: { period, dept_id: deptId ?? undefined },
      })
      .then((r) => r.data),
  report: (period: Period, deptId?: number | null) =>
    api
      .post<ReportResult>("/api/analytics/report", { period, dept_id: deptId ?? null })
      .then((r) => r.data),
  listReports: () =>
    api.get<SavedReportSummary[]>("/api/analytics/reports").then((r) => r.data),
  getReport: (reportId: number) =>
    api.get<ReportResult>(`/api/analytics/reports/${reportId}`).then((r) => r.data),
  deleteReport: (reportId: number) =>
    api.delete(`/api/analytics/reports/${reportId}`).then(() => undefined),
  emailReport: (payload: {
    period: Period;
    dept_id?: number | null;
    to: string[];
    markdown?: string;
  }) => api.post<ReportEmailResult>("/api/analytics/report/email", payload).then((r) => r.data),
};

// --------------------------------------------------------------------------- //
// Admin (ADMIN 전용)
// --------------------------------------------------------------------------- //
export const adminApi = {
  users: () => api.get<AdminUser[]>("/api/admin/users").then((r) => r.data),
  createUser: (payload: AdminUserCreatePayload) =>
    api.post<AdminUser>("/api/admin/users", payload).then((r) => r.data),
  updateUser: (userId: string, payload: AdminUserUpdatePayload) =>
    api.patch<AdminUser>(`/api/admin/users/${userId}`, payload).then((r) => r.data),
  deleteUser: (userId: string, reassignTo?: string | null) =>
    api
      .delete(`/api/admin/users/${userId}`, {
        params: reassignTo ? { reassign_to: reassignTo } : undefined,
      })
      .then(() => undefined),
  departments: () => api.get<AdminDepartment[]>("/api/admin/departments").then((r) => r.data),
  createDepartment: (payload: { dept_name: string; parent_dept_id: number | null }) =>
    api.post<AdminDepartment>("/api/admin/departments", payload).then((r) => r.data),
  updateDepartment: (deptId: number, payload: AdminDepartmentPayload) =>
    api.patch<AdminDepartment>(`/api/admin/departments/${deptId}`, payload).then((r) => r.data),
  deleteDepartment: (deptId: number) =>
    api.delete(`/api/admin/departments/${deptId}`).then(() => undefined),
  integrations: () => api.get<IntegrationList>("/api/admin/integrations").then((r) => r.data),
  saveIntegration: (provider: AiProvider, payload: IntegrationPayload) =>
    api.patch<IntegrationList>(`/api/admin/integrations/${provider}`, payload).then((r) => r.data),
  testIntegration: (provider: AiProvider, model?: string) =>
    api
      .post<ConnectionTestResult>(
        `/api/admin/integrations/${provider}/test`,
        undefined,
        model ? { params: { model } } : undefined,
      )
      .then((r) => r.data),
  usage: (days = 7, limit = 20) =>
    api
      .get<UsageSummary>("/api/admin/usage", { params: { days, limit } })
      .then((r) => r.data),
  clearUsage: () => api.delete("/api/admin/usage").then(() => undefined),
};

export const systemApi = {
  health: () =>
    api.get<{ status: string; ai: AiStatus }>("/api/health").then((r) => r.data),
};
