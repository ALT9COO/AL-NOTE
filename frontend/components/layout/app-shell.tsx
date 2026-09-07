"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  AlertTriangle,
  BookOpen,
  ChartNoAxesCombined,
  KanbanSquare,
  Loader2,
  LogOut,
  KeyRound,
  Mic,
  Moon,
  Settings,
  Sparkles,
  Sun,
} from "lucide-react";
import { useTheme } from "next-themes";

import { BrandLogo } from "@/components/brand/logo";

import { NotificationBell } from "@/components/layout/notification-bell";
import { RecordingDock, RecordingHeaderChip } from "@/components/meetings/recording-dock";
import { PasswordDialog } from "@/components/layout/password-dialog";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { systemApi } from "@/lib/api";
import { ROLE_LABELS, useAuth } from "@/lib/auth-context";
import { RecordingProvider, useRecording } from "@/lib/recording-context";
import { cn, initials } from "@/lib/utils";
import type { AiStatus } from "@/types";

const NAV = [
  { href: "/dashboard", label: "칸반 보드", icon: KanbanSquare, desc: "업무 진행 현황" },
  { href: "/meetings", label: "AI 회의실", icon: Mic, desc: "녹음 · 요약 · 반영" },
  { href: "/analytics", label: "AI 리포트", icon: ChartNoAxesCombined, desc: "기간별 경영 분석" },
  { href: "/guide", label: "사용자 가이드", icon: BookOpen, desc: "기능 사용 방법" },
  {
    href: "/settings",
    label: "설정",
    icon: Settings,
    desc: "계정 · 복원 · 권한",
  },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { user, loading, logout } = useAuth();
  const [ai, setAi] = useState<AiStatus | null>(null);

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  useEffect(() => {
    if (!user) return;
    systemApi
      .health()
      .then((res) => setAi(res.ai))
      .catch(() => setAi(null));
  }, [user]);

  if (loading || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const navItems = NAV.filter((item) => !item.adminOnly || user.role_level === "ADMIN");

  return (
    <RecordingProvider>
      <AppShellFrame user={user} ai={ai} navItems={navItems} onLogout={logout}>
        {children}
      </AppShellFrame>
    </RecordingProvider>
  );
}

function AppShellFrame({
  user,
  ai,
  navItems,
  onLogout,
  children,
}: {
  user: NonNullable<ReturnType<typeof useAuth>["user"]>;
  ai: AiStatus | null;
  navItems: { href: string; label: string; icon: typeof Mic; desc: string; adminOnly?: boolean }[];
  onLogout: () => void;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const { status: recordingStatus } = useRecording();
  const [passwordOpen, setPasswordOpen] = useState(false);
  const [bannerDismissed, setBannerDismissed] = useState(false);
  const { theme, setTheme } = useTheme();

  const showDefaultPwBanner =
    !bannerDismissed && user.is_using_default_password === true;

  return (
    <div className="flex min-h-screen bg-background">
      <aside className="fixed inset-y-0 left-0 hidden w-64 flex-col border-r bg-card lg:flex">
        <div className="flex h-16 items-center gap-2 border-b px-4">
          <BrandLogo variant="mark" className="h-9 w-auto" />
          <span className="text-sm font-semibold tracking-tight">AL-Note</span>
        </div>

        <div className="p-3">
          <div className="rounded-xl bg-gradient-to-br from-blue-600 to-cyan-500 p-3 text-white shadow-sm">
            <div className="flex items-center gap-2.5">
              <Avatar className="h-9 w-9 border-white/40">
                <AvatarFallback className="bg-white/20 text-white">
                  {initials(user.user_name)}
                </AvatarFallback>
              </Avatar>
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold">{user.user_name}</p>
                <p className="truncate text-[11px] text-white/80">
                  {user.dept_name ?? "-"} · {user.user_id}
                </p>
              </div>
            </div>
            <span className="mt-2 inline-block rounded-full bg-white/20 px-2 py-0.5 text-[10px] font-medium">
              {ROLE_LABELS[user.role_level]}
              {user.job_title ? ` · ${user.job_title}` : ""}
            </span>
          </div>
        </div>

        <nav className="flex-1 space-y-1 px-3">
          {navItems.map((item) => {
            const active = pathname.startsWith(item.href);
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors",
                  active
                    ? "bg-primary text-primary-foreground shadow-sm"
                    : "text-muted-foreground hover:bg-accent hover:text-foreground",
                )}
              >
                <Icon className="h-4 w-4 shrink-0" />
                <span className="flex-1">
                  <span className="block font-medium leading-tight">{item.label}</span>
                  <span
                    className={cn(
                      "block text-[11px] leading-tight",
                      active ? "text-primary-foreground/70" : "text-muted-foreground/70",
                    )}
                  >
                    {item.desc}
                  </span>
                </span>
                {item.href === "/meetings" && recordingStatus !== "idle" ? (
                  <span
                    className={cn(
                      "h-2 w-2 rounded-full",
                      recordingStatus === "ready"
                        ? "bg-emerald-400"
                        : recordingStatus === "failed"
                          ? "bg-amber-400"
                          : "animate-pulse bg-red-400",
                    )}
                  />
                ) : null}
              </Link>
            );
          })}
        </nav>

        <div className="space-y-3 p-3">
          <Separator />
          <div className="rounded-lg border bg-muted/40 p-3">
            <div className="flex items-center gap-1.5 text-xs font-medium">
              <Sparkles className="h-3.5 w-3.5 text-primary" />
              AI 엔진 상태
            </div>
            {ai ? (
              <div className="mt-2 space-y-1.5">
                <Badge variant={ai.llm_ready ? "success" : "warning"} className="max-w-full">
                  <span className="truncate">
                    {ai.llm_ready
                      ? `${ai.provider_label}: ${ai.text_model}`
                      : "LLM: 데모 모드"}
                  </span>
                </Badge>
                <Badge variant={ai.stt_ready ? "success" : "warning"}>
                  {ai.stt_ready ? `STT: ${ai.stt_model}` : "STT: 데모 전사"}
                </Badge>
              </div>
            ) : (
              <p className="mt-2 text-[11px] text-muted-foreground">백엔드 연결 확인 중…</p>
            )}
          </div>
          <Button variant="outline" className="w-full" onClick={onLogout}>
            <LogOut className="h-4 w-4" />
            로그아웃
          </Button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col lg:pl-64">
        <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b bg-background/80 px-4 backdrop-blur lg:px-8">
          <div className="flex items-center gap-2 lg:hidden">
            <BrandLogo variant="mark" className="h-8 w-auto" />
            <span className="font-semibold">AL-Note</span>
          </div>
          <nav className="flex flex-1 items-center gap-1 overflow-x-auto lg:hidden">
            {navItems.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "whitespace-nowrap rounded-md px-2.5 py-1.5 text-xs font-medium",
                  pathname.startsWith(item.href)
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:bg-accent",
                )}
              >
                {item.label}
              </Link>
            ))}
          </nav>
          <div className="hidden flex-1 lg:block" />
          <div className="flex items-center gap-2">
            <RecordingHeaderChip />
            <Badge variant="muted">{user.dept_name ?? "-"}</Badge>
            <NotificationBell />
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
              title={theme === "dark" ? "라이트 모드로 전환" : "다크 모드로 전환"}
            >
              {theme === "dark" ? (
                <Sun className="h-4 w-4" />
              ) : (
                <Moon className="h-4 w-4" />
              )}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="hidden h-8 px-2 text-xs lg:inline-flex"
              onClick={() => setPasswordOpen(true)}
            >
              <KeyRound className="h-3.5 w-3.5" />
              비밀번호 변경
            </Button>
            <Avatar className="h-8 w-8">
              <AvatarFallback>{initials(user.user_name)}</AvatarFallback>
            </Avatar>
            <Button
              variant="ghost"
              size="icon"
              className="lg:hidden"
              onClick={() => setPasswordOpen(true)}
              title="비밀번호 변경"
            >
              <KeyRound className="h-4 w-4" />
            </Button>
            <Button variant="ghost" size="icon" className="lg:hidden" onClick={onLogout}>
              <LogOut className="h-4 w-4" />
            </Button>
          </div>
        </header>

        {showDefaultPwBanner ? (
          <div className="flex items-center justify-between gap-3 border-b border-amber-300 bg-amber-50 px-4 py-2.5 text-amber-900 dark:border-amber-700 dark:bg-amber-950/60 dark:text-amber-200">
            <div className="flex items-center gap-2 text-xs font-medium">
              <AlertTriangle className="h-4 w-4 shrink-0 text-amber-600" />
              초기 비밀번호를 사용 중입니다. 보안을 위해 비밀번호를 즉시 변경해 주세요.
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <Button
                size="sm"
                variant="outline"
                className="h-7 border-amber-400 bg-white text-xs text-amber-900 hover:bg-amber-100"
                onClick={() => setPasswordOpen(true)}
              >
                <KeyRound className="h-3.5 w-3.5" />
                지금 변경
              </Button>
              <button
                type="button"
                className="text-[11px] text-amber-700 underline underline-offset-2 hover:text-amber-900"
                onClick={() => setBannerDismissed(true)}
              >
                나중에
              </button>
            </div>
          </div>
        ) : null}
        <main className="flex-1 px-4 py-6 lg:px-8">{children}</main>
      </div>
      <RecordingDock />
      <PasswordDialog open={passwordOpen} onOpenChange={setPasswordOpen} />
    </div>
  );
}
