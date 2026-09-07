"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  CalendarDays,
  CheckCircle2,
  Download,
  GanttChartSquare,
  Gauge,
  KanbanSquare,
  ListTodo,
  Loader2,
  Plus,
  RefreshCw,
  Rows3,
  Search,
  Users,
} from "lucide-react";
import { toast } from "sonner";

import { StatCard } from "@/components/common/stat-card";
import { TodayBriefing } from "@/components/dashboard/today-briefing";
import { KanbanBoard } from "@/components/kanban/kanban-board";
import { TaskDialog } from "@/components/kanban/task-dialog";
import { CalendarView } from "@/components/views/calendar-view";
import { TaskListView } from "@/components/views/task-list-view";
import { TimelineView } from "@/components/views/timeline-view";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { apiErrorMessage, authApi, taskApi } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import {
  cn,
    DASHBOARD_PERIODS,
    dashboardPeriodRange,
    formatDateOnly,
    taskInDashboardPeriod,
    isTopLevelTask,
    childrenOf,
    type DashboardPeriod,
} from "@/lib/utils";
import type { Department, Task, TaskStatus, User } from "@/types";

function exportToExcel(tasks: Task[]) {
  import("xlsx").then((XLSX) => {
    const rows = tasks.map((t) => ({
      업무번호: t.task_id,
      상위업무: t.parent_task_id ?? "",
      업무명: t.task_name,
      상태: t.status,
      담당자: t.assignee_name ?? "",
      부서: t.dept_name ?? "",
      시작일: t.start_date ?? "",
      종료일: t.due_date ?? "",
      진행률: t.progress,
      이슈: t.issues ?? "",
    }));
    const ws = XLSX.utils.json_to_sheet(rows);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, "업무목록");
    XLSX.writeFile(wb, `업무목록_${new Date().toISOString().slice(0, 10)}.xlsx`);
  });
}

type ViewMode = "kanban" | "list" | "timeline" | "calendar";

const VIEWS: { id: ViewMode; label: string; icon: typeof KanbanSquare; hint: string }[] = [
  {
    id: "kanban",
    label: "칸반",
    icon: KanbanSquare,
    hint: "카드를 드래그해 상태를 옮깁니다. 할당·진행중·완료는 진행률이 맞춰지고, 이슈 발생은 그대로 둡니다.",
  },
  {
    id: "list",
    label: "리스트",
    icon: Rows3,
    hint: "업무번호, 업무명, 담당자, 일정, 진행률을 표 형식으로 한눈에 확인합니다.",
  },
  {
    id: "timeline",
    label: "타임라인",
    icon: GanttChartSquare,
    hint: "착수일부터 마감일까지 기간을 막대로 보여줍니다. 막대를 클릭하면 수정할 수 있습니다.",
  },
  {
    id: "calendar",
    label: "캘린더",
    icon: CalendarDays,
    hint: "마감일 기준 월간 일정입니다. 점선 항목은 착수일을 뜻합니다.",
  },
];

export default function DashboardPage() {
  const { user } = useAuth();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [keyword, setKeyword] = useState("");
  const [assignee, setAssignee] = useState("all");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<Task | null>(null);
  const [view, setView] = useState<ViewMode>("kanban");
  const [teamView, setTeamView] = useState(false);
  const [period, setPeriod] = useState<DashboardPeriod>("monthly");
  const [prefsReady, setPrefsReady] = useState(false);
  const openedFromQuery = useRef<string | null>(null);
  const isMember = user?.role_level === "MEMBER";

  const loadTasks = useCallback(async () => {
    const data = await taskApi.list(isMember && teamView ? "team" : "mine");
    setTasks(data);
  }, [isMember, teamView]);

  useEffect(() => {
    const storedTeam = window.localStorage.getItem("alnote_team_view");
    const storedPeriod = window.localStorage.getItem("alnote_dashboard_period");
    setTeamView(storedTeam === "1");
    if (storedPeriod === "monthly" || storedPeriod === "halfyear" || storedPeriod === "yearly") {
      setPeriod(storedPeriod);
    }
    setPrefsReady(true);
  }, []);

  useEffect(() => {
    if (!prefsReady) return;
    let cancelled = false;
    setLoading(true);
    taskApi
      .list(isMember && teamView ? "team" : "mine")
      .then((taskList) => {
        if (cancelled) return;
        setTasks(taskList);
        setLoading(false);
      })
      .catch((error) => {
        if (!cancelled) {
          toast.error(apiErrorMessage(error, "데이터를 불러오지 못했습니다."));
          setLoading(false);
        }
      });
    authApi.users().then((userList) => {
      if (!cancelled) setUsers(userList);
    }).catch(() => undefined);
    authApi.departments().then((deptList) => {
      if (!cancelled) setDepartments(deptList);
    }).catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [prefsReady, isMember, teamView]);

  useEffect(() => {
    if (loading) return;
    const id = new URLSearchParams(window.location.search).get("task");
    if (!id || openedFromQuery.current === id) return;
    const found = tasks.find((task) => task.task_id === id);
    openedFromQuery.current = id;
    if (found) {
      setEditing(found);
      setDialogOpen(true);
      return;
    }
    toast.info(`${id} 업무를 현재 목록에서 찾지 못했습니다.`);
  }, [loading, tasks]);

  useEffect(() => {
    function onOpen(event: Event) {
      const id = (event as CustomEvent<string>).detail;
      if (!id) return;
      const found = tasks.find((task) => task.task_id === id);
      if (!found) return;
      openedFromQuery.current = id;
      setEditing(found);
      setDialogOpen(true);
    }
    window.addEventListener("alnote:open-task", onOpen);
    return () => window.removeEventListener("alnote:open-task", onOpen);
  }, [tasks]);

  async function handleRefresh() {
    setRefreshing(true);
    try {
      await loadTasks();
    } catch (error) {
      toast.error(apiErrorMessage(error));
    } finally {
      setRefreshing(false);
    }
  }

  /** 드래그 즉시 낙관적 반영 후 서버 응답으로 확정. 상위 이동 시 하점도 같이 맞춰진다. */
  async function handleMove(task: Task, status: TaskStatus) {
    const previous = tasks;
    setTasks((prev) =>
      prev.map((item) =>
        item.task_id === task.task_id || item.parent_task_id === task.task_id
          ? { ...item, status }
          : item,
      ),
    );
    try {
      const updated = await taskApi.updateStatus(task.task_id, status);
      await loadTasks();
      toast.success(`${updated.task_id} → ${status} (${updated.progress}%)`);
    } catch (error) {
      setTasks(previous);
      toast.error(apiErrorMessage(error, "상태 변경에 실패했습니다."));
    }
  }

  function openCreate() {
    setEditing(null);
    setDialogOpen(true);
  }

  function openEdit(task: Task) {
    setEditing(task);
    setDialogOpen(true);
  }

  function toggleTeamView() {
    const next = !teamView;
    setTeamView(next);
    window.localStorage.setItem("alnote_team_view", next ? "1" : "0");
  }

  function changePeriod(next: DashboardPeriod) {
    setPeriod(next);
    window.localStorage.setItem("alnote_dashboard_period", next);
  }

  const periodRange = useMemo(() => dashboardPeriodRange(period), [period]);

  const filtered = useMemo(() => {
    const query = keyword.trim().toLowerCase();
    const matches = (task: Task) => {
      if (!taskInDashboardPeriod(task, periodRange.start, periodRange.end)) return false;
      const matchKeyword =
        !query ||
        task.task_name.toLowerCase().includes(query) ||
        task.task_id.toLowerCase().includes(query) ||
        (task.issues ?? "").toLowerCase().includes(query);
      const matchAssignee =
        assignee === "all" ||
        (assignee === "mine" ? task.assigned_to === user?.user_id : task.assigned_to === assignee);
      return matchKeyword && matchAssignee;
    };

    const matching = tasks.filter(matches);
    const matchingIds = new Set(matching.map((task) => task.task_id));
    const withParents = tasks.filter(
      (task) =>
        matchingIds.has(task.task_id) || matching.some((item) => item.parent_task_id === task.task_id),
    );
    const orphans = matching.filter(
      (task) => task.parent_task_id && !tasks.some((item) => item.task_id === task.parent_task_id),
    );
    const board = [...withParents.filter(isTopLevelTask), ...orphans];
    const list = board.flatMap((task) =>
      isTopLevelTask(task) ? [task, ...childrenOf(tasks, task.task_id)] : [task],
    );
    return { board, list };
  }, [tasks, keyword, assignee, user?.user_id, periodRange]);

  const stats = useMemo(() => {
    const rows = filtered.board;
    const total = rows.length;
    const done = rows.filter((t) => t.status === "완료").length;
    const delayed = rows.filter((t) => t.is_delayed).length;
    const avg = total ? Math.round(rows.reduce((sum, t) => sum + t.progress, 0) / total) : 0;
    return { total, done, delayed, avg, rate: total ? Math.round((done / total) * 100) : 0 };
  }, [filtered]);

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">업무 진행 현황</h1>
          <p className="text-sm text-muted-foreground">
            {VIEWS.find((item) => item.id === view)?.hint}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={handleRefresh} disabled={refreshing}>
            <RefreshCw className={refreshing ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
            새로고침
          </Button>
          <Button onClick={openCreate}>
            <Plus className="h-4 w-4" />새 업무
          </Button>
        </div>
      </header>

      {isMember ? (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-950 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-100">
          <p>
            {teamView
              ? "소속 부서 업무를 조회 중입니다. 수정은 본인 담당 업무만 가능합니다."
              : "내 담당 업무만 표시됩니다. 부서 업무를 보려면 팀 조회를 켜 주세요."}
          </p>
          <Button
            variant={teamView ? "default" : "outline"}
            size="sm"
            className="h-7 text-xs"
            onClick={toggleTeamView}
          >
            <Users className="h-3.5 w-3.5" />
            {teamView ? "내 업무만 보기" : "팀 업무 조회"}
          </Button>
        </div>
      ) : null}

      {!loading ? <TodayBriefing delayed={tasks.filter((task) => task.is_delayed)} /> : null}

      {!loading ? (
        <p className="text-xs text-muted-foreground">
          {periodRange.label} · {formatDateOnly(periodRange.start)} ~ {formatDateOnly(periodRange.end)}
        </p>
      ) : null}

      {loading ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-20" />
          ))}
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard label="전체 업무" value={stats.total} icon={ListTodo} tone="blue" />
          <StatCard
            label="완료"
            value={stats.done}
            hint={`완료율 ${stats.rate}%`}
            icon={CheckCircle2}
            tone="emerald"
          />
          <StatCard
            label="지연"
            value={stats.delayed}
            hint="마감일 초과 & 미완료"
            icon={AlertTriangle}
            tone="red"
          />
          <StatCard label="평균 진행률" value={`${stats.avg}%`} icon={Gauge} tone="amber" />
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <div className="inline-flex rounded-lg border bg-card p-0.5 shadow-sm">
          {DASHBOARD_PERIODS.map((item) => {
            const active = period === item.value;
            return (
              <button
                key={item.value}
                type="button"
                onClick={() => changePeriod(item.value)}
                aria-pressed={active}
                className={cn(
                  "rounded-md px-3 py-1.5 text-xs font-medium transition",
                  active
                    ? "bg-primary text-primary-foreground shadow-sm"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground",
                )}
              >
                {item.label}
              </button>
            );
          })}
        </div>

        <div className="inline-flex rounded-lg border bg-card p-0.5 shadow-sm">
          {VIEWS.map((item) => {
            const Icon = item.icon;
            const active = view === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setView(item.id)}
                aria-pressed={active}
                className={cn(
                  "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition",
                  active
                    ? "bg-primary text-primary-foreground shadow-sm"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground",
                )}
              >
                <Icon className="h-3.5 w-3.5" />
                {item.label}
              </button>
            );
          })}
        </div>

        <div className="relative min-w-[200px] flex-1 sm:max-w-xs">
          <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            placeholder="업무명 · ID · 이슈 검색"
            className="pl-8"
          />
        </div>
        {!isMember || teamView ? (
          <Select value={assignee} onValueChange={setAssignee}>
            <SelectTrigger className="w-[190px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">전체 담당자</SelectItem>
              <SelectItem value="mine">내 업무만</SelectItem>
              {users.map((u) => (
                <SelectItem key={u.user_id} value={u.user_id}>
                  {u.user_name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : null}
        <span className="text-xs text-muted-foreground">
          {filtered.board.length}건 표시 중 (전체 {tasks.filter((task) => !task.parent_task_id).length}건)
        </span>
        <Button
          variant="outline"
          size="sm"
          className="h-8 gap-1.5 text-xs"
          onClick={() => exportToExcel(filtered.list)}
          title="현재 필터 결과를 Excel로 내보내기"
        >
          <Download className="h-3.5 w-3.5" />
          Excel
        </Button>
      </div>

      {loading ? (
        <div className="flex h-64 items-center justify-center">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : view === "kanban" ? (
        <KanbanBoard
          tasks={filtered.board.map((task) => ({
            ...task,
            children: childrenOf(tasks, task.task_id),
            child_count: childrenOf(tasks, task.task_id).length,
            progress_locked: childrenOf(tasks, task.task_id).length > 0,
          }))}
          onMove={handleMove}
          onEdit={openEdit}
          onSubtaskAdded={loadTasks}
        />
      ) : view === "list" ? (
        <TaskListView tasks={filtered.list} onEdit={openEdit} />
      ) : view === "timeline" ? (
        <TimelineView tasks={filtered.board} onEdit={openEdit} />
      ) : (
        <CalendarView tasks={filtered.board} onEdit={openEdit} />
      )}

      <TaskDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        task={editing}
        users={users}
        departments={departments}
        defaultDeptId={user?.dept_id ?? null}
        onSaved={loadTasks}
      />
    </div>
  );
}
