"use client";

import Link from "next/link";
import { ArrowDownRight, ArrowRight, ArrowUpRight, GitCompareArrows } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { AnalyticsSummary, WeekCompareRow } from "@/types";

function Change({ value, unit }: { value: number; unit: string }) {
  if (value === 0) return <span className="text-[11px] text-muted-foreground">0</span>;
  const up = value > 0;
  const Icon = up ? ArrowUpRight : ArrowDownRight;
  return (
    <span className={cn("inline-flex items-center text-[11px] font-medium", up ? "text-emerald-600" : "text-red-600")}>
      <Icon className="h-3 w-3" />
      {up ? "+" : ""}
      {value}
      {unit}
    </span>
  );
}

function Delta({ value }: { value?: number | null }) {
  if (value == null) return <span className="text-[11px] text-muted-foreground">-</span>;
  return <Change value={value} unit="%p" />;
}

function StatPair({
  label,
  last,
  current,
  suffix = "",
  unit,
}: {
  label: string;
  last: number;
  current: number;
  suffix?: string;
  unit: string;
}) {
  return (
    <div className="rounded-lg border bg-background px-3 py-2">
      <p className="text-[11px] text-muted-foreground">{label}</p>
      <p className="mt-1 flex items-center gap-1.5 text-sm font-semibold">
        <span className="text-muted-foreground">{last}{suffix}</span>
        <ArrowRight className="h-3 w-3 text-muted-foreground" />
        <span>{current}{suffix}</span>
        <Change value={current - last} unit={unit} />
      </p>
    </div>
  );
}

function CompareRow({ row }: { row: WeekCompareRow }) {
  return (
    <tr className="border-t align-top">
      <td className="px-3 py-2">
        <Link
          href={`/dashboard?task=${encodeURIComponent(row.task_id)}`}
          className="text-sm font-medium text-primary hover:underline"
        >
          [{row.task_name}]
        </Link>
        <p className="text-[11px] text-muted-foreground">
          {row.task_id} · {row.assignee_name}
        </p>
      </td>
      <td className="px-3 py-2 text-xs text-muted-foreground">{row.last_week}</td>
      <td className="px-3 py-2 text-xs text-muted-foreground">{row.this_week}</td>
      <td className="px-3 py-2 text-right">
        <Delta value={row.delta} />
      </td>
    </tr>
  );
}

export function WeekCompareCard({ summary }: { summary: AnalyticsSummary }) {
  const wow = summary.week_over_week;
  if (!wow) return null;

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <GitCompareArrows className="h-4 w-4 text-primary" />
          전주 대비 이번주
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
          <Badge variant="secondary">전주 {wow.last_start} ~ {wow.last_end}</Badge>
          <ArrowRight className="h-3 w-3" />
          <Badge>이번주 {summary.start_date} ~ {summary.end_date}</Badge>
        </div>
        <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
          <StatPair label="집계 업무" last={wow.last_total} current={summary.total} suffix="건" unit="건" />
          <StatPair label="완료" last={wow.last_completed} current={summary.completed} suffix="건" unit="건" />
          <StatPair label="완료율" last={wow.last_completion_rate} current={summary.completion_rate} suffix="%" unit="%p" />
          <StatPair label="평균 진행률" last={wow.last_avg_progress} current={summary.avg_progress} suffix="%" unit="%p" />
        </div>
        {wow.rows.length ? (
          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full min-w-[640px] text-left">
              <thead className="bg-muted/50 text-[11px] uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="px-3 py-2 font-medium">업무</th>
                  <th className="px-3 py-2 font-medium">전주 진행상황</th>
                  <th className="px-3 py-2 font-medium">이번주 진행 예정</th>
                  <th className="px-3 py-2 text-right font-medium">증감</th>
                </tr>
              </thead>
              <tbody>
                {wow.rows.map((row) => (
                  <CompareRow key={row.task_id} row={row} />
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="rounded-lg border border-dashed px-3 py-6 text-center text-sm text-muted-foreground">
            전주·이번주에 비교할 업무가 없습니다.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
