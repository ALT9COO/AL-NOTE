"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Activity,
  CircleDollarSign,
  Cpu,
  Gauge,
  Pause,
  Play,
  RefreshCw,
  Trash2,
} from "lucide-react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { toast } from "sonner";

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
import { adminApi, apiErrorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { UsageSummary } from "@/types";

const POLL_MS = 8000;

const STATUS_BADGE: Record<string, { variant: "success" | "danger" | "muted"; label: string }> = {
  success: { variant: "success", label: "성공" },
  error: { variant: "danger", label: "실패" },
  mock: { variant: "muted", label: "데모" },
};

const PROVIDER_COLOR: Record<string, string> = {
  openai: "#10b981",
  anthropic: "#f97316",
  google: "#3b82f6",
  mock: "#94a3b8",
};

function formatCost(value: number) {
  if (!value) return "$0.00";
  if (value < 0.01) return `$${value.toFixed(4)}`;
  return `$${value.toFixed(2)}`;
}

function formatTokens(value: number) {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(2)}M`;
  if (value >= 1000) return `${(value / 1000).toFixed(1)}K`;
  return String(value);
}

function timeOf(iso: string) {
  const d = new Date(iso);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(
    2,
    "0",
  )}:${String(d.getSeconds()).padStart(2, "0")}`;
}

export function UsageMonitor() {
  const [data, setData] = useState<UsageSummary | null>(null);
  const [days, setDays] = useState("7");
  const [live, setLive] = useState(true);
  const [loading, setLoading] = useState(true);
  const [pulse, setPulse] = useState(false);
  const previousCalls = useRef<number | null>(null);

  const load = useCallback(async () => {
    try {
      const result = await adminApi.usage(Number(days), 20);
      setData((prev) => {
        if (previousCalls.current !== null && result.totals.calls > previousCalls.current) {
          setPulse(true);
          setTimeout(() => setPulse(false), 1200);
        }
        previousCalls.current = result.totals.calls;
        return result ?? prev;
      });
    } catch (error) {
      toast.error(apiErrorMessage(error, "사용량을 불러오지 못했습니다."));
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!live) return;
    const timer = setInterval(load, POLL_MS);
    return () => clearInterval(timer);
  }, [live, load]);

  if (loading || !data) {
    return (
      <div className="flex h-48 items-center justify-center text-sm text-muted-foreground">
        사용량을 불러오는 중...
      </div>
    );
  }

  const providers = data.by_provider.filter((row) => row.calls > 0 || row.is_active);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span
            className={cn(
              "flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium",
              live ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600",
            )}
          >
            <span
              className={cn(
                "h-1.5 w-1.5 rounded-full",
                live ? "animate-pulse bg-emerald-500" : "bg-slate-400",
              )}
            />
            {live ? `실시간 (${POLL_MS / 1000}초 주기)` : "일시정지"}
          </span>
          <span className={cn("text-[11px] text-muted-foreground", pulse && "text-emerald-600")}>
            최근 갱신 {timeOf(data.generated_at)}
          </span>
        </div>

        <div className="flex items-center gap-1.5">
          <Select value={days} onValueChange={setDays}>
            <SelectTrigger className="h-8 w-[110px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="1">오늘</SelectItem>
              <SelectItem value="7">최근 7일</SelectItem>
              <SelectItem value="30">최근 30일</SelectItem>
            </SelectContent>
          </Select>
          <Button variant="outline" size="sm" onClick={() => setLive((v) => !v)}>
            {live ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
            {live ? "일시정지" : "재개"}
          </Button>
          <Button variant="outline" size="sm" onClick={load}>
            <RefreshCw className="h-3.5 w-3.5" />
            새로고침
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="text-destructive hover:text-destructive"
            onClick={async () => {
              try {
                await adminApi.clearUsage();
                previousCalls.current = null;
                await load();
                toast.success("사용량 로그를 초기화했습니다.");
              } catch (error) {
                toast.error(apiErrorMessage(error, "초기화에 실패했습니다."));
              }
            }}
          >
            <Trash2 className="h-3.5 w-3.5" />
            로그 초기화
          </Button>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="호출 수"
          value={data.totals.calls}
          hint={`오늘 ${data.today.calls}건 · 실패 ${data.totals.error}건`}
          icon={Activity}
          tone="blue"
        />
        <StatCard
          label="총 토큰"
          value={formatTokens(data.totals.total_tokens)}
          hint={`입력 ${formatTokens(data.totals.prompt_tokens)} · 출력 ${formatTokens(
            data.totals.completion_tokens,
          )}`}
          icon={Cpu}
          tone="emerald"
        />
        <StatCard
          label="추정 비용"
          value={formatCost(data.totals.cost_usd)}
          hint={`오늘 ${formatCost(data.today.cost_usd)}`}
          icon={CircleDollarSign}
          tone="amber"
        />
        <StatCard
          label="평균 응답"
          value={`${data.totals.avg_latency_ms}ms`}
          hint={`데모 호출 ${data.totals.mock}건 제외 시 실호출 ${data.totals.success}건`}
          icon={Gauge}
          tone="violet"
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">일자별 호출 · 토큰</CardTitle>
          </CardHeader>
          <CardContent className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data.daily} margin={{ top: 4, right: 8, left: -18, bottom: 0 }}>
                <defs>
                  <linearGradient id="usageCalls" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.35} />
                    <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                <XAxis
                  dataKey="date"
                  tickFormatter={(value: string) => value.slice(5)}
                  fontSize={11}
                  tickLine={false}
                  axisLine={false}
                />
                <YAxis fontSize={11} tickLine={false} axisLine={false} allowDecimals={false} />
                <Tooltip formatter={(value) => [`${value}건`, "호출"]} />
                <Area
                  type="monotone"
                  dataKey="calls"
                  stroke="#3b82f6"
                  fill="url(#usageCalls)"
                  strokeWidth={2}
                />
              </AreaChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">기능별 호출</CardTitle>
          </CardHeader>
          <CardContent className="h-56">
            {data.by_feature.length ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={data.by_feature}
                  layout="vertical"
                  margin={{ top: 4, right: 16, left: 8, bottom: 0 }}
                >
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#e2e8f0" />
                  <XAxis type="number" fontSize={11} tickLine={false} axisLine={false} allowDecimals={false} />
                  <YAxis
                    type="category"
                    dataKey="feature"
                    width={96}
                    fontSize={11}
                    interval={0}
                    tickFormatter={(value: string) => value.replace(" ", "")}
                    tickLine={false}
                    axisLine={false}
                  />
                  <Tooltip formatter={(value) => [`${value}건`, "호출"]} />
                  <Bar dataKey="calls" fill="#6366f1" radius={[0, 4, 4, 0]} barSize={16} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex h-full items-center justify-center text-xs text-muted-foreground">
                아직 호출 기록이 없습니다.
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">프로바이더별 사용량</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {providers.map((row) => (
            <div key={row.provider} className="rounded-lg border p-3">
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-1.5 text-xs font-medium">
                  <span
                    className="h-2 w-2 rounded-full"
                    style={{ background: PROVIDER_COLOR[row.provider] ?? "#94a3b8" }}
                  />
                  {row.label}
                </span>
                {row.is_active ? <Badge>활성</Badge> : null}
              </div>
              <p className="mt-2 text-lg font-semibold">{row.calls}건</p>
              <p className="text-[11px] text-muted-foreground">
                토큰 {formatTokens(row.total_tokens)} · {formatCost(row.cost_usd)}
              </p>
              <p className="text-[11px] text-muted-foreground">
                평균 {row.avg_latency_ms}ms · 실패 {row.error_calls}건
              </p>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">최근 호출 로그</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="max-h-72 overflow-auto">
            <table className="w-full min-w-[720px] text-xs">
              <thead className="sticky top-0 bg-muted/60">
                <tr className="text-left text-[11px] uppercase tracking-wide text-muted-foreground">
                  <th className="px-4 py-2 font-medium">시각</th>
                  <th className="px-4 py-2 font-medium">기능</th>
                  <th className="px-4 py-2 font-medium">프로바이더 · 모델</th>
                  <th className="px-4 py-2 font-medium">토큰</th>
                  <th className="px-4 py-2 font-medium">비용</th>
                  <th className="px-4 py-2 font-medium">응답</th>
                  <th className="px-4 py-2 font-medium">상태</th>
                </tr>
              </thead>
              <tbody>
                {data.recent.map((log) => {
                  const badge = STATUS_BADGE[log.status] ?? STATUS_BADGE.mock;
                  return (
                    <tr key={log.usage_id} className="border-b last:border-0">
                      <td className="whitespace-nowrap px-4 py-2 font-mono text-[11px] text-muted-foreground">
                        {timeOf(log.created_at)}
                      </td>
                      <td className="px-4 py-2">{log.feature}</td>
                      <td className="px-4 py-2 text-muted-foreground">
                        {log.provider} · {log.model}
                      </td>
                      <td className="px-4 py-2">{formatTokens(log.total_tokens)}</td>
                      <td className="px-4 py-2">{formatCost(log.cost_usd)}</td>
                      <td className="px-4 py-2 text-muted-foreground">{log.latency_ms}ms</td>
                      <td className="px-4 py-2">
                        <Badge variant={badge.variant} title={log.error_message || undefined}>
                          {badge.label}
                        </Badge>
                      </td>
                    </tr>
                  );
                })}
                {!data.recent.length ? (
                  <tr>
                    <td colSpan={7} className="px-4 py-10 text-center text-muted-foreground">
                      호출 기록이 없습니다. AI 회의실이나 리포트를 실행하면 여기에 실시간으로 쌓입니다.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
