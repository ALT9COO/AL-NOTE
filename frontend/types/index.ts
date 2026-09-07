export type TaskStatus = "할당" | "진행중" | "이슈 발생" | "완료";
export type RoleLevel = "ADMIN" | "LEADER" | "MEMBER";
export type Period = "weekly" | "monthly" | "quarterly" | "yearly";

export interface User {
  user_id: string;
  user_name: string;
  role_level: RoleLevel;
  job_title?: string;
  dept_id: number | null;
  dept_name: string | null;
  is_using_default_password?: boolean;
}

export interface Department {
  dept_id: number;
  dept_name: string;
  parent_dept_id: number | null;
}

export interface AdminUser extends User {
  created_at: string | null;
  task_count: number;
  is_self: boolean;
}

export interface AdminUserCreatePayload {
  user_id: string;
  user_name: string;
  password: string;
  role_level: RoleLevel;
  job_title?: string;
  dept_id: number | null;
}

export interface AdminUserUpdatePayload {
  user_name?: string;
  password?: string;
  role_level?: RoleLevel;
  job_title?: string;
  dept_id?: number | null;
}

export interface AdminDepartment extends Department {
  parent_dept_name: string | null;
  user_count: number;
  task_count: number;
  child_count: number;
  depth: number;
}

export interface AdminDepartmentPayload {
  dept_name?: string;
  parent_dept_id?: number | null;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export interface Collaborator {
  kind: "user" | "dept";
  user_id?: string | null;
  user_name?: string | null;
  dept_id?: number | null;
  dept_name?: string | null;
}

export interface TaskActivity {
  activity_id: number;
  kind: string;
  body: string;
  progress: number | null;
  status: TaskStatus | null;
  user_id: string | null;
  user_name: string | null;
  created_at: string;
}

export interface Task {
  task_id: string;
  task_name: string;
  description: string;
  status: TaskStatus;
  progress: number;
  dept_id: number | null;
  dept_name: string | null;
  assigned_to: string | null;
  assignee_name: string | null;
  start_date: string | null;
  due_date: string | null;
  issues: string;
  updated_at: string | null;
  is_delayed: boolean;
  can_edit: boolean;
  is_collaborator?: boolean;
  latest_comment_at?: string | null;
  collaborators?: Collaborator[];
  viewers?: Collaborator[];
  activities?: TaskActivity[];
  deleted_at?: string | null;
  deleted_by?: string | null;
  deleted_by_name?: string | null;
  purge_on?: string | null;
  parent_task_id?: string | null;
  child_count?: number;
  progress_locked?: boolean;
  children?: Task[];
}

export interface TaskPayload {
  task_name: string;
  description?: string;
  status?: TaskStatus;
  progress?: number;
  dept_id?: number | null;
  assigned_to?: string | null;
  start_date?: string | null;
  due_date?: string | null;
  issues?: string;
  collaborators?: Collaborator[];
  viewers?: Collaborator[];
  parent_task_id?: string | null;
}

export interface AgendaItem {
  topic: string;
  discussion: string;
  decision: string;
}

export interface ActionItem {
  title: string;
  assignee: string;
  due_date: string;
  note: string;
}

export interface TaskUpdateProposal {
  task_id: string;
  task_name: string;
  assignee: string;
  status: TaskStatus;
  progress: number;
  issues: string;
  due_date: string;
  is_new: boolean;
  change_note?: string;
}

export interface MeetingParseResult {
  meeting_title: string;
  summary_bullets: string[];
  agenda_items: AgendaItem[];
  action_items: ActionItem[];
  task_updates: TaskUpdateProposal[];
  risks: string[];
  mock: boolean;
}

export interface MeetingDraft {
  draft_id: number;
  title: string;
  transcript: string;
  parsed: MeetingParseResult | null;
  event: CalendarEvent | null;
  step: number;
  created_at: string;
  updated_at: string;
  has_audio?: boolean;
  audio_name?: string | null;
  audio_size?: number | null;
  stt_status?: "idle" | "transcribing" | "done" | "error" | string;
  stt_error?: string | null;
  stt_mock?: boolean;
}

export interface TaskAlert {
  task_id: string;
  task_name: string;
  assignee_name?: string | null;
  due_date?: string | null;
  days_left: number;
  is_delayed: boolean;
}

export interface AgendaSubmitResult {
  meeting_id: number;
  updated: string[];
  created: string[];
  skipped: string[];
  tasks: Task[];
}

export interface Meeting {
  meeting_id: number;
  title: string;
  created_by: string | null;
  author_name: string | null;
  dept_name: string | null;
  ai_summary: string;
  raw_transcript: string;
  created_at: string;
  event_key: string | null;
  event_start: string | null;
  event_location: string;
  task_ids: string[];
  participants?: Collaborator[];
  viewers?: Collaborator[];
  can_manage?: boolean;
  has_audio?: boolean;
  audio_name?: string | null;
  audio_size?: number | null;
}

// --------------------------------------------------------------------------- //
// 캘린더 연동 (사용자별 Microsoft 365 / Graph)
// --------------------------------------------------------------------------- //
export interface CalendarConnection {
  connected: boolean;
  app_configured: boolean;
  provider: string;
  account_name: string;
  account_email: string;
  needs_reauth: boolean;
  connected_at: string | null;
  last_synced_at: string | null;
  last_sync_ok: boolean | null;
  last_sync_message: string;
  event_count: number;
  can_write?: boolean;
  can_mail?: boolean;
  missing_scopes?: string[];
}

export interface CalendarApp {
  configured: boolean;
  source: "db" | "env" | "none";
  client_id: string;
  tenant_id: string;
  redirect_uri: string;
  suggested_redirect_uris?: string[];
  client_secret_masked: string;
  scopes: string[];
  updated_by: string | null;
  updated_at: string | null;
}

export interface CalendarAppPayload {
  client_id: string;
  client_secret?: string;
  tenant_id: string;
  redirect_uri: string;
}

export interface CalendarAttendee {
  name: string;
  email: string;
}

export interface CalendarEvent {
  event_key: string;
  uid: string;
  title: string;
  start: string;
  end: string | null;
  all_day: boolean;
  location: string;
  organizer: string;
  attendees: CalendarAttendee[];
  online_url: string;
  is_cancelled: boolean;
  description: string;
  matched_user_ids: string[];
  meeting_id: number | null;
  meeting_title: string | null;
}

export interface CalendarEventsResult {
  connection: CalendarConnection;
  range_start: string;
  range_end: string;
  events: CalendarEvent[];
  sample: boolean;
}

export interface CalendarEventCreatePayload {
  title: string;
  start: string;
  end: string;
  location?: string;
  body?: string;
  attendees?: { name: string; email: string }[];
}

export interface CalendarEventCreated {
  id: string;
  web_link: string;
  title: string;
  start: string | null;
  end: string | null;
}

export interface StatusCount {
  status: TaskStatus;
  count: number;
}

export interface AssigneeStat {
  assignee: string;
  total: number;
  done: number;
  delayed: number;
  avg_progress: number;
}

export interface DeptStat {
  dept_name: string;
  total: number;
  avg_progress: number;
  delayed: number;
}

export interface TrendPoint {
  label: string;
  completed: number;
  created: number;
}

export interface WeekCompareRow {
  task_id: string;
  task_name: string;
  assignee_name: string;
  last_week: string;
  this_week: string;
  last_progress?: number | null;
  this_progress?: number | null;
  delta?: number | null;
}

export interface WeekOverWeek {
  last_start: string;
  last_end: string;
  last_total: number;
  last_completed: number;
  last_delayed: number;
  last_avg_progress: number;
  last_completion_rate: number;
  rows: WeekCompareRow[];
}

export interface AnalyticsSummary {
  period: Period;
  start_date: string;
  end_date: string;
  scope_label: string;
  total: number;
  completed: number;
  delayed: number;
  with_issues: number;
  avg_progress: number;
  completion_rate: number;
  status_counts: StatusCount[];
  by_assignee: AssigneeStat[];
  by_dept: DeptStat[];
  trend: TrendPoint[];
  tasks: Task[];
  week_over_week?: WeekOverWeek | null;
}

export interface ReportResult {
  report_id?: number | null;
  period?: Period;
  anchor?: string | null;
  dept_id?: number | null;
  period_label: string;
  scope_label: string;
  report_markdown: string;
  mock: boolean;
  created_at?: string | null;
}

export interface SavedReportSummary {
  report_id: number;
  period: Period;
  period_label: string;
  scope_label: string;
  mock: boolean;
  created_at: string;
}

export interface ReportEmailResult {
  sent_to: string[];
  subject: string;
}

export interface AiStatus {
  provider: AiProvider;
  provider_label: string;
  stt_ready: boolean;
  llm_ready: boolean;
  mock_mode: boolean;
  text_model: string;
  stt_model: string;
}

// --------------------------------------------------------------------------- //
// API 연동 · 사용량
// --------------------------------------------------------------------------- //
export type AiProvider = "openai" | "anthropic" | "google";

export interface Integration {
  provider: AiProvider;
  label: string;
  description: string;
  models: string[];
  default_model: string;
  supports_stt: boolean;
  key_hint: string;
  console_url: string;
  text_model: string;
  has_key: boolean;
  masked_key: string;
  is_active: boolean;
  last_test_ok: boolean | null;
  last_test_message: string;
  last_tested_at: string | null;
  updated_at: string | null;
  updated_by: string | null;
}

export interface IntegrationList {
  providers: Integration[];
  active_provider: AiProvider;
  active_model: string;
  llm_ready: boolean;
  stt_ready: boolean;
  mock_mode: boolean;
}

export interface IntegrationPayload {
  api_key?: string;
  text_model?: string;
  activate?: boolean;
}

export interface ConnectionTestResult {
  provider: AiProvider;
  ok: boolean;
  message: string;
  latency_ms: number;
  model: string;
}

export interface UsageTotals {
  calls: number;
  success: number;
  error: number;
  mock: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usd: number;
  avg_latency_ms: number;
}

export interface UsageByProvider {
  provider: string;
  label: string;
  calls: number;
  total_tokens: number;
  cost_usd: number;
  avg_latency_ms: number;
  error_calls: number;
  is_active: boolean;
}

export interface UsageByFeature {
  feature: string;
  calls: number;
  total_tokens: number;
  cost_usd: number;
}

export interface UsageDailyPoint {
  date: string;
  calls: number;
  total_tokens: number;
  cost_usd: number;
}

export interface UsageLog {
  usage_id: number;
  created_at: string;
  provider: string;
  model: string;
  feature: string;
  status: "success" | "error" | "mock";
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usd: number;
  latency_ms: number;
  error_message: string;
  user_id: string | null;
}

export interface UsageSummary {
  generated_at: string;
  range_days: number;
  totals: UsageTotals;
  today: UsageTotals;
  by_provider: UsageByProvider[];
  by_feature: UsageByFeature[];
  daily: UsageDailyPoint[];
  recent: UsageLog[];
}
