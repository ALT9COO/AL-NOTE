"use client";

import { useCallback, useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import {
  AlertTriangle,
  CheckCircle2,
  FileBarChart,
  Gauge,
  History,
  ListTodo,
  Loader2,
  Mail,
  Sparkles,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";

import { ReportMailDialog } from "@/components/analytics/report-mail-dialog";
import {
  AssigneeBarChart,
  DeptBarChart,
  StatusPieChart,
  TrendAreaChart,
} from "@/components/analytics/charts";
import { WeekCompareCard } from "@/components/analytics/week-compare";
import { StatCard } from "@/components/common/stat-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { analyticsApi, apiErrorMessage, authApi } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { formatDateTime } from "@/lib/utils";
import type { AnalyticsSummary, Department, Period, ReportResult, SavedReportSummary } from "@/types";

const PERIODS: { value: Period; label: string }[] = [
  { value: "weekly", label: "주간" },
  { value: "monthly", label: "월간" },
  { value: "quarterly", label: "분기" },
  { value: "yearly", label: "연간" },
];

export default function AnalyticsPage() {
  const { user } = useAuth();
  const [period, setPeriod] = useState<Period>("weekly");
  const [deptId, setDeptId] = useState("all");
  const [departments, setDepartments] = useState<Department[]>([]);
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [report, setReport] = useState<ReportResult | null>(null);
  const [savedReports, setSavedReports] = useState<SavedReportSummary[]>([]);
  const [activeReportId, setActiveReportId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [loadingReport, setLoadingReport] = useState(false);
  const [mailOpen, setMailOpen] = useState(false);

  useEffect(() => {
    authApi.departments().then(setDepartments).catch(() => undefined);
  }, []);

  const loadSavedReports = useCallback(async () => {
    try {
      const rows = await analyticsApi.listReports();
      setSavedReports(rows);
    } catch {
      /* 목록 실패는 조용히 무시 */
    }
  }, []);

  useEffect(() => {
    void loadSavedReports();
  }, [loadSavedReports]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await analyticsApi.summary(period, deptId === "all" ? null : Number(deptId));
      setSummary(data);
    } catch (error) {
      toast.error(apiErrorMessage(error, "통계를 불러오지 못했습니다."));
    } finally {
      setLoading(false);
    }
  }, [period, deptId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleReport() {
    setGenerating(true);
    try {
      const data = await analyticsApi.report(period, deptId === "all" ? null : Number(deptId));
      setReport(data);
      setActiveReportId(data.report_id ?? null);
      await loadSavedReports();
      toast.success("AI 리포트를 생성하고 저장했습니다.");
    } catch (error) {
      toast.error(apiErrorMessage(error, "리포트 생성에 실패했습니다."));
    } finally {
      setGenerating(false);
    }
  }

  async function openSavedReport(reportId: number) {
    setLoadingReport(true);
    try {
      const data = await analyticsApi.getReport(reportId);
      setReport(data);
      setActiveReportId(reportId);
    } catch (error) {
      toast.error(apiErrorMessage(error, "저장된 리포트를 불러오지 못했습니다."));
    } finally {
      setLoadingReport(false);
    }
  }

  async function discardSavedReport(reportId: number) {
    try {
      await analyticsApi.deleteReport(reportId);
      setSavedReports((prev) => prev.filter((item) => item.report_id !== reportId));
      if (activeReportId === reportId) {
        setReport(null);
        setActiveReportId(null);
      }
      toast.success("저장된 리포트를 삭제했습니다.");
    } catch (error) {
      toast.error(apiErrorMessage(error, "리포트 삭제에 실패했습니다."));
    }
  }

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">AI 경영 리포트</h1>
          <p className="text-sm text-muted-foreground">
            {user?.role_level === "ADMIN"
              ? "전사 범위의 업무 통계와 AI 요약 보고서를 확인합니다."
              : "권한 범위 내 업무 통계와 AI 요약 보고서를 확인합니다."}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Select value={period} onValueChange={(value) => setPeriod(value as Period)}>
            <SelectTrigger className="w-[130px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {PERIODS.map((item) => (
                <SelectItem key={item.value} value={item.value}>
                  {item.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={deptId} onValueChange={setDeptId}>
            <SelectTrigger className="w-[170px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">전체 부서</SelectItem>
              {departments.map((dept) => (
                <SelectItem key={dept.dept_id} value={String(dept.dept_id)}>
                  {dept.dept_name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button onClick={handleReport} disabled={generating || loading}>
            {generating ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Sparkles className="h-4 w-4" />
            )}
            AI 리포트 생성
          </Button>
        </div>
      </header>

      {loading || !summary ? (
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-20" />
            ))}
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <Skeleton className="h-[320px]" />
            <Skeleton className="h-[320px]" />
          </div>
        </div>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <Badge variant="secondary">{summary.scope_label}</Badge>
            <span>
              {summary.start_date} ~ {summary.end_date}
            </span>
          </div>

          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard label="집계 업무" value={summary.total} icon={ListTodo} tone="blue" />
            <StatCard
              label="완료"
              value={summary.completed}
              hint={`완료율 ${summary.completion_rate}%`}
              icon={CheckCircle2}
              tone="emerald"
            />
            <StatCard
              label="지연"
              value={summary.delayed}
              hint={`이슈 등록 ${summary.with_issues}건`}
              icon={AlertTriangle}
              tone="red"
            />
            <StatCard label="평균 진행률" value={`${summary.avg_progress}%`} icon={Gauge} tone="amber" />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <StatusPieChart data={summary.status_counts} />
            <TrendAreaChart data={summary.trend} />
            <AssigneeBarChart data={summary.by_assignee} />
            <DeptBarChart data={summary.by_dept} />
          </div>

          {summary.week_over_week ? <WeekCompareCard summary={summary} /> : null}

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-base">
                <History className="h-4 w-4 text-primary" />
                저장된 AI 리포트
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <p className="text-xs text-muted-foreground">
                생성한 경영 리포트는 서버에 저장됩니다. PC를 껐다 켜도 여기서 다시 열람할 수 있습니다.
              </p>
              {savedReports.length ? (
                savedReports.map((item) => (
                  <div
                    key={item.report_id}
                    className={`flex flex-wrap items-center gap-2 rounded-lg border px-3 py-2 ${
                      activeReportId === item.report_id ? "border-primary/40 bg-primary/5" : "bg-muted/30"
                    }`}
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{item.period_label}</p>
                      <p className="text-[11px] text-muted-foreground">
                        {formatDateTime(item.created_at)} · {item.scope_label}
                        {item.mock ? " · 샘플" : ""}
                      </p>
                    </div>
                    <Button
                      size="sm"
                      variant={activeReportId === item.report_id ? "default" : "outline"}
                      disabled={loadingReport}
                      onClick={() => void openSavedReport(item.report_id)}
                    >
                      {loadingReport && activeReportId === item.report_id ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <FileBarChart className="h-3.5 w-3.5" />
                      )}
                      열람
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => void discardSavedReport(item.report_id)}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                ))
              ) : (
                <div className="rounded-lg border border-dashed px-4 py-6 text-sm text-muted-foreground">
                  아직 저장된 AI 리포트가 없습니다. 상단의 `AI 리포트 생성` 버튼으로 첫 리포트를 만들면
                  이 영역에 자동으로 쌓입니다.
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex-row items-center justify-between space-y-0 pb-3">
              <CardTitle className="flex items-center gap-2 text-base">
                <FileBarChart className="h-4 w-4 text-primary" />
                경영진 요약 보고서
              </CardTitle>
              <span className="flex items-center gap-2">
                {report ? <Badge variant="secondary">{report.period_label}</Badge> : null}
                {report ? (
                  <Button size="sm" variant="outline" onClick={() => setMailOpen(true)}>
                    <Mail className="h-3.5 w-3.5" />
                    Outlook으로 보내기
                  </Button>
                ) : null}
              </span>
            </CardHeader>
            <CardContent>
              {report ? (
                <div className="markdown-body">
                  <ReactMarkdown>{report.report_markdown}</ReactMarkdown>
                </div>
              ) : (
                <div className="flex flex-col items-center gap-3 py-10 text-center">
                  <Sparkles className="h-8 w-8 text-muted-foreground/40" />
                  <p className="text-sm text-muted-foreground">
                    상단의 <span className="font-medium">AI 리포트 생성</span> 버튼을 누르면
                    <br />
                    선택한 기간의 성과 · 병목 · 리스크를 요약한 보고서가 만들어집니다.
                  </p>
                </div>
              )}
            </CardContent>
          </Card>
        </>
      )}

      {report ? (
        <ReportMailDialog
          open={mailOpen}
          onOpenChange={setMailOpen}
          report={report}
          period={report.period ?? period}
          deptId={report.dept_id ?? (deptId === "all" ? null : Number(deptId))}
        />
      ) : null}
    </div>
  );
}
