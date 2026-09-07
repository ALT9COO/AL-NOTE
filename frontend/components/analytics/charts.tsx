"use client";

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { STATUS_CHART_COLORS } from "@/lib/utils";
import type { AnalyticsSummary } from "@/types";

const AXIS = { fontSize: 11, fill: "#64748b" } as const;

const TOOLTIP_STYLE = {
  borderRadius: 10,
  border: "1px solid #e2e8f0",
  fontSize: 12,
  boxShadow: "0 8px 24px rgba(15, 23, 42, 0.08)",
} as const;

export function StatusPieChart({ data }: { data: AnalyticsSummary["status_counts"] }) {
  const chartData = data.filter((item) => item.count > 0);
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">상태별 분포</CardTitle>
      </CardHeader>
      <CardContent className="h-[260px]">
        {chartData.length === 0 ? (
          <EmptyChart />
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={chartData}
                dataKey="count"
                nameKey="status"
                innerRadius={55}
                outerRadius={85}
                paddingAngle={3}
              >
                {chartData.map((entry) => (
                  <Cell key={entry.status} fill={STATUS_CHART_COLORS[entry.status]} />
                ))}
              </Pie>
              <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(value) => [`${value}건`, "업무"]} />
              <Legend iconType="circle" wrapperStyle={{ fontSize: 12 }} />
            </PieChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  );
}

export function AssigneeBarChart({ data }: { data: AnalyticsSummary["by_assignee"] }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">담당자별 업무량 · 평균 진행률</CardTitle>
      </CardHeader>
      <CardContent className="h-[260px]">
        {data.length === 0 ? (
          <EmptyChart />
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 10, right: 8, left: -18, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
              <XAxis dataKey="assignee" tick={AXIS} tickLine={false} axisLine={false} />
              <YAxis tick={AXIS} tickLine={false} axisLine={false} allowDecimals={false} />
              <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: "#f8fafc" }} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="total" name="담당 업무" fill="#3b82f6" radius={[6, 6, 0, 0]} maxBarSize={36} />
              <Bar dataKey="done" name="완료" fill="#22c55e" radius={[6, 6, 0, 0]} maxBarSize={36} />
              <Bar dataKey="delayed" name="지연" fill="#ef4444" radius={[6, 6, 0, 0]} maxBarSize={36} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  );
}

export function TrendAreaChart({ data }: { data: AnalyticsSummary["trend"] }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">기간 내 완료 추이</CardTitle>
      </CardHeader>
      <CardContent className="h-[260px]">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 10, right: 8, left: -18, bottom: 0 }}>
            <defs>
              <linearGradient id="completedFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#22c55e" stopOpacity={0.35} />
                <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="createdFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
            <XAxis dataKey="label" tick={AXIS} tickLine={false} axisLine={false} />
            <YAxis tick={AXIS} tickLine={false} axisLine={false} allowDecimals={false} />
            <Tooltip contentStyle={TOOLTIP_STYLE} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Area
              type="monotone"
              dataKey="completed"
              name="완료"
              stroke="#22c55e"
              strokeWidth={2}
              fill="url(#completedFill)"
            />
            <Area
              type="monotone"
              dataKey="created"
              name="신규 등록"
              stroke="#3b82f6"
              strokeWidth={2}
              fill="url(#createdFill)"
            />
          </AreaChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}

export function DeptBarChart({ data }: { data: AnalyticsSummary["by_dept"] }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">부서별 평균 진행률</CardTitle>
      </CardHeader>
      <CardContent className="h-[260px]">
        {data.length === 0 ? (
          <EmptyChart />
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={data}
              layout="vertical"
              margin={{ top: 10, right: 16, left: 8, bottom: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" horizontal={false} />
              <XAxis type="number" domain={[0, 100]} tick={AXIS} tickLine={false} axisLine={false} />
              <YAxis
                type="category"
                dataKey="dept_name"
                tick={AXIS}
                tickLine={false}
                axisLine={false}
                width={90}
              />
              <Tooltip
                contentStyle={TOOLTIP_STYLE}
                cursor={{ fill: "#f8fafc" }}
                formatter={(value) => [`${value}%`, "평균 진행률"]}
              />
              <Bar dataKey="avg_progress" fill="#6366f1" radius={[0, 6, 6, 0]} maxBarSize={28} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  );
}

function EmptyChart() {
  return (
    <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
      표시할 데이터가 없습니다.
    </div>
  );
}
