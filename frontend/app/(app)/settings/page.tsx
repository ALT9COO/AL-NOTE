"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Building2,
  CalendarCheck2,
  KeyRound,
  Loader2,
  PlugZap,
  ShieldCheck,
  Trash2,
  Users,
} from "lucide-react";
import { toast } from "sonner";

import { AccountSettings } from "@/components/settings/account-settings";
import { ApiIntegrations } from "@/components/settings/api-integrations";
import { CalendarIntegration } from "@/components/settings/calendar-integration";
import { DeletedTasks } from "@/components/settings/deleted-tasks";
import { DepartmentManager } from "@/components/settings/department-manager";
import { RoleGuide } from "@/components/settings/role-guide";
import { UsageMonitor } from "@/components/settings/usage-monitor";
import { UserManager } from "@/components/settings/user-manager";
import { StatCard } from "@/components/common/stat-card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { adminApi, apiErrorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import type { AdminDepartment, AdminUser, IntegrationList } from "@/types";

const ADMIN_TABS = ["users", "departments", "roles", "api", "calendar"] as const;
const ALL_TABS = ["account", "trash", ...ADMIN_TABS] as const;

export default function SettingsPage() {
  const { user } = useAuth();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [departments, setDepartments] = useState<AdminDepartment[]>([]);
  const [integrations, setIntegrations] = useState<IntegrationList | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState("account");

  const isAdmin = user?.role_level === "ADMIN";

  const load = useCallback(async () => {
    if (!isAdmin) return;
    try {
      const [userList, deptList, integrationList] = await Promise.all([
        adminApi.users(),
        adminApi.departments(),
        adminApi.integrations(),
      ]);
      setUsers(userList);
      setDepartments(deptList);
      setIntegrations(integrationList);
    } catch (error) {
      toast.error(apiErrorMessage(error, "설정 데이터를 불러오지 못했습니다."));
    }
  }, [isAdmin]);

  useEffect(() => {
    if (!isAdmin) {
      setLoading(false);
      return;
    }
    void load().finally(() => setLoading(false));
  }, [load, isAdmin]);

  useEffect(() => {
    const requested = new URLSearchParams(window.location.search).get("tab");
    if (requested && (ALL_TABS as readonly string[]).includes(requested)) {
      if (!isAdmin && ADMIN_TABS.includes(requested as (typeof ADMIN_TABS)[number])) {
        setTab("account");
        return;
      }
      setTab(requested);
    }
  }, [isAdmin]);

  if (loading && isAdmin) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">설정</h1>
        <p className="text-sm text-muted-foreground">
          {isAdmin
            ? "계정, 삭제된 업무, 사용자 · 조직 · 권한을 관리합니다. 변경 사항은 즉시 적용됩니다."
            : "비밀번호를 변경하고, 삭제한 업무 카드를 1년 이내에 복원할 수 있습니다."}
        </p>
      </header>

      {isAdmin ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard label="전체 사용자" value={users.length} icon={Users} tone="blue" />
          <StatCard label="등록 부서" value={departments.length} icon={Building2} tone="emerald" />
          <StatCard
            label="관리자 계정"
            value={users.filter((u) => u.role_level === "ADMIN").length}
            hint={`조직장 ${users.filter((u) => u.role_level === "LEADER").length}명 · 구성원 ${
              users.filter((u) => u.role_level === "MEMBER").length
            }명`}
            icon={ShieldCheck}
            tone="amber"
          />
          <StatCard
            label="AI 엔진"
            value={
              integrations?.llm_ready
                ? integrations.providers.find((p) => p.provider === integrations.active_provider)
                    ?.label ?? "연결됨"
                : "데모 모드"
            }
            hint={integrations?.llm_ready ? integrations.active_model : "API 연동 탭에서 키 등록"}
            icon={PlugZap}
            tone="violet"
          />
        </div>
      ) : null}

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="h-auto flex-wrap justify-start">
          <TabsTrigger value="account">
            <KeyRound className="h-3.5 w-3.5" />
            계정
          </TabsTrigger>
          <TabsTrigger value="trash">
            <Trash2 className="h-3.5 w-3.5" />
            삭제된 업무
          </TabsTrigger>
          {isAdmin ? (
            <>
              <TabsTrigger value="users">
                <Users className="h-3.5 w-3.5" />
                사용자 관리
              </TabsTrigger>
              <TabsTrigger value="departments">
                <Building2 className="h-3.5 w-3.5" />
                조직 관리
              </TabsTrigger>
              <TabsTrigger value="roles">
                <ShieldCheck className="h-3.5 w-3.5" />
                권한 설정
              </TabsTrigger>
              <TabsTrigger value="api">
                <PlugZap className="h-3.5 w-3.5" />
                API 연동
              </TabsTrigger>
              <TabsTrigger value="calendar">
                <CalendarCheck2 className="h-3.5 w-3.5" />
                캘린더 연동
              </TabsTrigger>
            </>
          ) : null}
        </TabsList>

        <TabsContent value="account">
          <AccountSettings />
        </TabsContent>
        <TabsContent value="trash">
          <DeletedTasks />
        </TabsContent>
        {isAdmin ? (
          <>
            <TabsContent value="users">
              <UserManager users={users} departments={departments} onChanged={load} />
            </TabsContent>
            <TabsContent value="departments">
              <DepartmentManager departments={departments} onChanged={load} />
            </TabsContent>
            <TabsContent value="roles">
              <RoleGuide users={users} onChanged={load} />
            </TabsContent>
            <TabsContent value="api">
              <div className="space-y-6">
                {integrations ? <ApiIntegrations data={integrations} onChanged={load} /> : null}
                <div>
                  <h2 className="mb-2 text-sm font-semibold">실시간 사용량</h2>
                  <UsageMonitor />
                </div>
              </div>
            </TabsContent>
            <TabsContent value="calendar">
              <CalendarIntegration />
            </TabsContent>
          </>
        ) : null}
      </Tabs>
    </div>
  );
}
