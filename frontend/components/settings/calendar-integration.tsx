"use client";

import { useEffect, useState } from "react";
import {
  CalendarCheck2,
  CheckCircle2,
  Copy,
  ExternalLink,
  Loader2,
  ShieldQuestion,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiErrorMessage, calendarApi, calendarRedirectUri } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";
import type { CalendarApp } from "@/types";

const AZURE_STEPS = [
  "Azure Portal → Microsoft Entra ID → 앱 등록 → 새 등록",
  "이름은 자유롭게(예: AL Note 캘린더), 계정 유형은 '이 조직 디렉터리의 계정만'",
  "리디렉션 URI 는 플랫폼 '웹' 에 아래 목록을 모두 추가 (localhost + 사내 IP)",
  "API 사용 권한 → Microsoft Graph → 위임된 권한에서 Calendars.ReadWrite · Mail.Send · offline_access · User.Read 추가",
  "인증서 및 비밀 → 새 클라이언트 비밀 만들기 → 생성된 '값'을 복사(다시 볼 수 없음)",
  "개요 화면의 애플리케이션(클라이언트) ID · 디렉터리(테넌트) ID 와 함께 아래에 입력",
];

export function CalendarIntegration() {
  const [app, setApp] = useState<CalendarApp | null>(null);
  const [clientId, setClientId] = useState("");
  const [tenantId, setTenantId] = useState("");
  const [redirectUri, setRedirectUri] = useState("");
  const [secret, setSecret] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  function apply(data: CalendarApp) {
    setApp(data);
    setClientId(data.client_id);
    setTenantId(data.tenant_id);
    setRedirectUri(data.redirect_uri);
    setSecret("");
  }

  useEffect(() => {
    calendarApi
      .app()
      .then(apply)
      .catch((error) => toast.error(apiErrorMessage(error, "캘린더 설정을 불러오지 못했습니다.")))
      .finally(() => setLoading(false));
  }, []);

  async function handleSave() {
    if (!clientId.trim()) {
      toast.error("애플리케이션(클라이언트) ID 를 입력하세요.");
      return;
    }
    if (!app?.configured && !secret.trim()) {
      toast.error("클라이언트 비밀을 입력하세요.");
      return;
    }
    setSaving(true);
    try {
      apply(
        await calendarApi.saveApp({
          client_id: clientId.trim(),
          client_secret: secret.trim(),
          tenant_id: tenantId.trim() || "common",
          redirect_uri: redirectUri.trim(),
        }),
      );
      toast.success("Azure 앱 정보를 저장했습니다. 이제 각자 캘린더를 연결할 수 있습니다.");
    } catch (error) {
      toast.error(apiErrorMessage(error, "저장에 실패했습니다."));
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    setSaving(true);
    try {
      await calendarApi.deleteApp();
      apply(await calendarApi.app());
      toast.success("앱 등록 정보와 모든 구성원의 캘린더 연결을 해제했습니다.");
    } catch (error) {
      toast.error(apiErrorMessage(error, "삭제에 실패했습니다."));
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="flex h-40 items-center justify-center">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[1.15fr_1fr]">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex flex-wrap items-center justify-between gap-2 text-base">
            <span className="flex items-center gap-2">
              <CalendarCheck2 className="h-4 w-4 text-primary" />
              Microsoft 365 캘린더
              {app?.configured ? (
                <Badge variant="success">
                  <CheckCircle2 className="h-3 w-3" />
                  {app.source === "env" ? ".env 설정됨" : "연동 준비됨"}
                </Badge>
              ) : (
                <Badge variant="warning">미설정</Badge>
              )}
            </span>
            {app?.configured && app.source === "db" ? (
              <Button
                variant="ghost"
                size="sm"
                className="text-destructive hover:text-destructive"
                disabled={saving}
                onClick={handleDelete}
              >
                <Trash2 className="h-3.5 w-3.5" />
                등록 삭제
              </Button>
            ) : null}
          </CardTitle>
          <p className="text-xs text-muted-foreground">
            조직에 앱을 한 번만 등록하면, 구성원은 AI 회의실에서 각자 자기 계정을 연결합니다.
            서버는 사용자별 토큰만 보관하며 캘린더는 읽기 전용으로만 접근합니다.
          </p>
        </CardHeader>

        <CardContent className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="ms-client-id">애플리케이션(클라이언트) ID</Label>
            <Input
              id="ms-client-id"
              value={clientId}
              onChange={(e) => setClientId(e.target.value)}
              placeholder="00000000-0000-0000-0000-000000000000"
              className="font-mono text-xs"
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="ms-tenant-id">디렉터리(테넌트) ID</Label>
            <Input
              id="ms-tenant-id"
              value={tenantId}
              onChange={(e) => setTenantId(e.target.value)}
              placeholder="테넌트 ID 또는 common"
              className="font-mono text-xs"
            />
            <p className="text-[11px] text-muted-foreground">
              사내 계정만 쓰면 테넌트 ID 를 넣는 편이 안전합니다. 외부 조직·개인 계정도 허용하려면
              <code className="mx-1 font-mono">common</code>.
            </p>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="ms-secret">클라이언트 비밀</Label>
            <Input
              id="ms-secret"
              type="password"
              value={secret}
              onChange={(e) => setSecret(e.target.value)}
              placeholder={
                app?.client_secret_masked
                  ? `저장됨 (${app.client_secret_masked}) — 바꿀 때만 입력`
                  : "Azure 에서 발급한 비밀 '값'"
              }
              className="font-mono text-xs"
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="ms-redirect">기본 리디렉션 URI (참고용)</Label>
            <div className="flex flex-wrap gap-2">
              <Input
                id="ms-redirect"
                value={redirectUri}
                onChange={(e) => setRedirectUri(e.target.value)}
                placeholder={`https://<서버IP>:3001/api/calendar/callback`}
                className="min-w-0 flex-1 font-mono text-xs"
              />
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => {
                  const current = calendarRedirectUri();
                  setRedirectUri(current);
                  toast.success("현재 접속 주소로 채웠습니다.");
                }}
              >
                현재 주소
              </Button>
              <Button
                variant="outline"
                size="icon"
                title="복사"
                onClick={() => {
                  void navigator.clipboard.writeText(redirectUri);
                  toast.success("리디렉션 URI 를 복사했습니다.");
                }}
              >
                <Copy className="h-3.5 w-3.5" />
              </Button>
            </div>
            <p className="text-[11px] text-muted-foreground">
              Azure에는 <b>다른 PC 주소창에 실제로 보이는 주소</b>를 넣어야 합니다. 서버에 LAN IP가
              두 개면 둘 다 등록하세요. <code>http://</code> 로 열면 실패하고,{" "}
              <code>https://10.10.120.50:3001</code> 과{" "}
              <code>https://10.10.102.182:3001</code> 은 서로 다른 URI입니다.
            </p>
            {app?.suggested_redirect_uris?.length ? (
              <div className="space-y-1 rounded-lg border bg-muted/30 p-3">
                <p className="text-[11px] font-medium">Azure에 등록할 URI 목록</p>
                <ul className="space-y-1">
                  {app.suggested_redirect_uris.map((uri) => (
                    <li key={uri} className="flex items-center justify-between gap-2">
                      <code className="break-all font-mono text-[10px]">{uri}</code>
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 shrink-0"
                        title="복사"
                        onClick={() => {
                          void navigator.clipboard.writeText(uri);
                          toast.success("복사했습니다.");
                        }}
                      >
                        <Copy className="h-3 w-3" />
                      </Button>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>

          <div className="flex items-center justify-between gap-2 pt-1">
            <p className="text-[11px] text-muted-foreground">
              {app?.updated_at
                ? `최근 수정 ${formatDateTime(app.updated_at)}${
                    app.updated_by ? ` · ${app.updated_by}` : ""
                  }`
                : "아직 저장된 값이 없습니다."}
            </p>
            <Button size="sm" onClick={handleSave} disabled={saving}>
              {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
              저장
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <ShieldQuestion className="h-4 w-4 text-primary" />
            Azure 앱 등록 방법
          </CardTitle>
          <p className="text-xs text-muted-foreground">
            앱 등록 권한이 없다면 아래 내용을 그대로 IT 담당자에게 전달하세요.
          </p>
        </CardHeader>
        <CardContent className="space-y-3">
          <ol className="space-y-2 text-xs text-muted-foreground">
            {AZURE_STEPS.map((line, index) => (
              <li key={line} className="flex gap-2">
                <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[10px] font-medium text-primary">
                  {index + 1}
                </span>
                <span>{line}</span>
              </li>
            ))}
          </ol>

          <div className="rounded-lg border bg-muted/30 p-3 text-xs">
            <p className="mb-1 font-medium">요청할 위임 권한</p>
            <div className="flex flex-wrap gap-1">
              {(app?.scopes ?? []).map((scope) => (
                <code key={scope} className="rounded bg-background px-1.5 py-0.5 font-mono text-[11px]">
                  {scope}
                </code>
              ))}
            </div>
            <p className="mt-2 text-[11px] text-muted-foreground">
              Calendars.ReadWrite 는 일정 조회·생성, Mail.Send 는 연결된 계정으로 메일 발송에
              필요합니다. 테넌트 정책상 사용자 동의를 막아 두었다면 관리자가 Azure → API 사용
              권한에서 &lsquo;관리자 동의 허용&rsquo; 을 한 번 눌러야 합니다. 이미 읽기만 연결한
              구성원은 회의실에서 「권한 추가」로 다시 로그인해야 새 권한이 적용됩니다.
            </p>
          </div>

          <Button asChild variant="outline" size="sm" className="w-full">
            <a
              href="https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade"
              target="_blank"
              rel="noreferrer"
            >
              Azure 앱 등록 화면 열기
              <ExternalLink className="h-3.5 w-3.5" />
            </a>
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
