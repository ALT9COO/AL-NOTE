"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Info, Loader2, LogIn, ShieldCheck, Sparkles, Waypoints } from "lucide-react";
import { toast } from "sonner";

import { BrandLogo } from "@/components/brand/logo";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiErrorMessage, REMEMBER_KEY, USER_ID_KEY } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

const HIGHLIGHTS = [
  { icon: Waypoints, title: "드래그 한 번으로 진행 관리", desc: "칸반에서 옮기면 상태가 바로 반영" },
  { icon: Sparkles, title: "회의 녹음 → 업무 업데이트", desc: "음성 전사 + AI 구조화 파싱" },
  { icon: ShieldCheck, title: "역할 기반 접근 제어", desc: "부서 트리 기준 조회·수정 권한 분리" },
];

export default function LoginPage() {
  const router = useRouter();
  const { user, loading, login } = useAuth();
  const [userId, setUserId] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!loading && user) router.replace("/dashboard");
  }, [loading, user, router]);

  useEffect(() => {
    const savedId = window.localStorage.getItem(USER_ID_KEY);
    if (savedId) setUserId(savedId);
    setRemember(window.localStorage.getItem(REMEMBER_KEY) !== "0");
  }, []);

  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("reason") === "expired") {
      toast.error("로그인이 만료되었습니다. 다시 로그인해 주세요.");
    }
  }, []);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    try {
      const logged = await login(userId.trim(), password, remember);
      toast.success(`${logged.user_name}님 환영합니다.`);
      router.replace("/dashboard");
    } catch (error) {
      toast.error(apiErrorMessage(error, "로그인에 실패했습니다."));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="grid min-h-screen lg:grid-cols-2">
      <section className="relative hidden overflow-hidden bg-slate-950 p-12 text-white lg:flex lg:flex-col lg:justify-between">
        <div className="pointer-events-none absolute -left-32 -top-32 h-96 w-96 rounded-full bg-blue-600/30 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-40 -right-24 h-96 w-96 rounded-full bg-cyan-400/20 blur-3xl" />

        <div className="relative">
          <div className="inline-flex rounded-2xl bg-white px-4 py-3 shadow-sm">
            <BrandLogo className="h-24 w-auto" />
          </div>
        </div>

        <div className="relative space-y-8">
          <div className="space-y-3">
            <h1 className="text-4xl font-bold leading-tight tracking-tight">
              회의 한 번으로
              <br />
              업무 현황까지 자동으로.
            </h1>
            <p className="max-w-md text-sm leading-relaxed text-slate-400">
              녹음 파일을 올리면 AI가 회의록을 요약하고, 담당자별 진행률과 이슈까지 정리해
              칸반 보드에 반영합니다.
            </p>
          </div>

          <ul className="space-y-4">
            {HIGHLIGHTS.map(({ icon: Icon, title, desc }) => (
              <li key={title} className="flex items-start gap-3">
                <span className="mt-0.5 rounded-lg bg-white/10 p-2">
                  <Icon className="h-4 w-4 text-blue-300" />
                </span>
                <div>
                  <p className="text-sm font-medium">{title}</p>
                  <p className="text-xs text-slate-400">{desc}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>

        <p className="relative text-xs text-slate-500">© {new Date().getFullYear()} AL-Note. Internal use only.</p>
      </section>

      <section className="flex items-center justify-center bg-background p-6">
        <div className="w-full max-w-sm space-y-6 animate-fade-in-up">
          <div className="space-y-1.5 text-center lg:text-left">
            <div className="mb-4 flex items-center justify-center lg:hidden">
              <BrandLogo className="h-16 w-auto" />
            </div>
            <h2 className="text-2xl font-semibold tracking-tight">로그인</h2>
            <p className="text-sm text-muted-foreground">사내 계정으로 대시보드에 접속하세요.</p>
          </div>

          {typeof window !== "undefined" && window.location.protocol === "https:" && (
            <div className="flex items-start gap-2 rounded-lg border border-blue-200 bg-blue-50 px-3 py-2.5 text-xs text-blue-800">
              <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-blue-500" />
              <span>
                사내 자체 서명 인증서를 사용합니다. 브라우저에서{" "}
                <strong>「보안 경고」</strong>가 표시되면{" "}
                <strong>고급 → 계속(안전하지 않음)</strong>을 눌러 접속하세요.
              </span>
            </div>
          )}
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="user_id">아이디</Label>
              <Input
                id="user_id"
                value={userId}
                onChange={(e) => setUserId(e.target.value)}
                placeholder="아이디"
                autoComplete="username"
                required
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="password">비밀번호</Label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                autoComplete="current-password"
                required
              />
            </div>
            <label className="flex cursor-pointer items-center gap-2 text-sm text-muted-foreground">
              <Checkbox
                checked={remember}
                onCheckedChange={(value) => setRemember(value === true)}
              />
              자동 로그인 (1년 동안 유지)
            </label>
            <Button type="submit" className="w-full" disabled={submitting}>
              {submitting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <LogIn className="h-4 w-4" />
              )}
              로그인
            </Button>
          </form>
        </div>
      </section>
    </main>
  );
}
