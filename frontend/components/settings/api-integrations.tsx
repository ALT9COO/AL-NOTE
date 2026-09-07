"use client";

import { useEffect, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  ExternalLink,
  Eye,
  EyeOff,
  Loader2,
  Mic,
  PlugZap,
  Save,
  Sparkles,
  Trash2,
  Zap,
} from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { adminApi, apiErrorMessage } from "@/lib/api";
import { cn, formatDateTime } from "@/lib/utils";
import type { AiProvider, Integration, IntegrationList } from "@/types";

const PROVIDER_ACCENT: Record<AiProvider, string> = {
  openai: "from-emerald-500 to-teal-500",
  anthropic: "from-orange-500 to-amber-500",
  google: "from-blue-500 to-indigo-500",
};

interface ApiIntegrationsProps {
  data: IntegrationList;
  onChanged: () => Promise<void>;
}

export function ApiIntegrations({ data, onChanged }: ApiIntegrationsProps) {
  return (
    <div className="space-y-4">
      <Card
        className={cn(
          "border",
          data.llm_ready ? "border-emerald-200 bg-emerald-50/50" : "border-amber-200 bg-amber-50/50",
        )}
      >
        <CardContent className="flex flex-wrap items-center justify-between gap-3 py-4">
          <div className="flex items-center gap-3">
            {data.llm_ready ? (
              <CheckCircle2 className="h-5 w-5 text-emerald-600" />
            ) : (
              <AlertCircle className="h-5 w-5 text-amber-500" />
            )}
            <div>
              <p className="text-sm font-semibold">
                {data.llm_ready
                  ? `${
                      data.providers.find((p) => p.provider === data.active_provider)?.label ?? ""
                    } · ${data.active_model} 사용 중`
                  : "연결된 AI 프로바이더가 없습니다 (데모 모드)"}
              </p>
              <p className="text-xs text-muted-foreground">
                회의 요약과 경영 리포트는 활성 프로바이더로, 음성 전사는 OpenAI Whisper 또는 Gemini 오디오로 처리됩니다.
              </p>
            </div>
          </div>
          <div className="flex gap-1.5">
            <Badge variant={data.llm_ready ? "success" : "warning"}>
              <Sparkles className="h-3 w-3" />
              LLM {data.llm_ready ? "연결됨" : "데모"}
            </Badge>
            <Badge variant={data.stt_ready ? "success" : "warning"}>
              <Mic className="h-3 w-3" />
              STT {data.stt_ready ? "연결됨" : "데모"}
            </Badge>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-3">
        {data.providers.map((provider) => (
          <ProviderCard key={provider.provider} provider={provider} onChanged={onChanged} />
        ))}
      </div>
    </div>
  );
}

function ProviderCard({
  provider,
  onChanged,
}: {
  provider: Integration;
  onChanged: () => Promise<void>;
}) {
  const [key, setKey] = useState("");
  const [model, setModel] = useState(provider.text_model);
  const [reveal, setReveal] = useState(false);
  const [busy, setBusy] = useState<"save" | "test" | "activate" | "clear" | null>(null);

  useEffect(() => {
    setModel(provider.text_model);
  }, [provider.text_model]);

  async function run(action: typeof busy, fn: () => Promise<void>) {
    setBusy(action);
    try {
      await fn();
      await onChanged();
    } catch (error) {
      toast.error(apiErrorMessage(error, "요청에 실패했습니다."));
    } finally {
      setBusy(null);
    }
  }

  const dirty = key.trim().length > 0 || model !== provider.text_model;

  return (
    <Card className={cn("flex flex-col", provider.is_active && "ring-2 ring-primary/40")}>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center justify-between text-base">
          <span className="flex items-center gap-2">
            <span
              className={cn(
                "flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br text-white",
                PROVIDER_ACCENT[provider.provider],
              )}
            >
              <PlugZap className="h-4 w-4" />
            </span>
            {provider.label}
          </span>
          {provider.is_active ? <Badge>활성</Badge> : null}
        </CardTitle>
        <p className="text-xs text-muted-foreground">{provider.description}</p>
      </CardHeader>

      <CardContent className="flex flex-1 flex-col gap-3">
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <Label htmlFor={`key-${provider.provider}`}>API 키</Label>
            {provider.has_key ? (
              <span className="font-mono text-[10px] text-muted-foreground">
                {provider.masked_key}
              </span>
            ) : (
              <span className="text-[10px] text-muted-foreground">미등록</span>
            )}
          </div>
          <div className="relative">
            <Input
              id={`key-${provider.provider}`}
              type={reveal ? "text" : "password"}
              value={key}
              onChange={(e) => setKey(e.target.value)}
              placeholder={provider.has_key ? "새 키 입력 시 교체" : provider.key_hint}
              className="pr-9 font-mono text-xs"
              autoComplete="off"
            />
            <button
              type="button"
              onClick={() => setReveal((v) => !v)}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              aria-label="키 표시 전환"
            >
              {reveal ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
            </button>
          </div>
          <a
            href={provider.console_url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-[10px] text-primary hover:underline"
          >
            키 발급 콘솔 열기
            <ExternalLink className="h-2.5 w-2.5" />
          </a>
        </div>

        <div className="space-y-1.5">
          <Label>사용 모델</Label>
          <Select value={model} onValueChange={setModel}>
            <SelectTrigger className="h-8">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {provider.models.map((name) => (
                <SelectItem key={name} value={name}>
                  {name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="flex flex-wrap gap-1.5 text-[10px] text-muted-foreground">
          <Badge variant={provider.supports_stt ? "secondary" : "muted"}>
            <Mic className="h-3 w-3" />
            {provider.supports_stt ? "음성 전사 지원" : "텍스트 전용"}
          </Badge>
          {provider.last_tested_at ? (
            <Badge variant={provider.last_test_ok ? "success" : "danger"}>
              {provider.last_test_ok ? "연결 정상" : "연결 실패"}
            </Badge>
          ) : null}
        </div>

        {provider.last_test_message ? (
          <p
            className={cn(
              "rounded-md px-2 py-1.5 text-[10px]",
              provider.last_test_ok
                ? "bg-emerald-50 text-emerald-700"
                : "bg-rose-50 text-rose-700",
            )}
          >
            {provider.last_test_message}
            {provider.last_tested_at ? (
              <span className="block opacity-70">{formatDateTime(provider.last_tested_at)}</span>
            ) : null}
          </p>
        ) : null}

        <div className="mt-auto space-y-1.5 pt-1">
          <div className="flex gap-1.5">
            <Button
              size="sm"
              className="flex-1"
              disabled={!dirty || busy !== null}
              onClick={() =>
                run("save", async () => {
                  await adminApi.saveIntegration(provider.provider, {
                    ...(key.trim() ? { api_key: key.trim() } : {}),
                    ...(model !== provider.text_model ? { text_model: model } : {}),
                  });
                  setKey("");
                  toast.success(`${provider.label} 설정을 저장했습니다.`);
                })
              }
            >
              {busy === "save" ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Save className="h-3.5 w-3.5" />
              )}
              저장
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={!provider.has_key || busy !== null}
              onClick={() =>
                run("test", async () => {
                  const result = await adminApi.testIntegration(provider.provider, model);
                  if (result.ok) toast.success(`${result.message} (${result.latency_ms}ms)`);
                  else toast.error(result.message);
                })
              }
            >
              {busy === "test" ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Zap className="h-3.5 w-3.5" />
              )}
              연결 테스트
            </Button>
          </div>

          <div className="flex gap-1.5">
            <Button
              size="sm"
              variant={provider.is_active ? "secondary" : "outline"}
              className="flex-1"
              disabled={!provider.has_key || provider.is_active || busy !== null}
              onClick={() =>
                run("activate", async () => {
                  await adminApi.saveIntegration(provider.provider, { activate: true });
                  toast.success(`${provider.label} 를 기본 AI 엔진으로 지정했습니다.`);
                })
              }
            >
              {busy === "activate" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
              {provider.is_active ? "사용 중" : "이 엔진 사용"}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="text-destructive hover:text-destructive"
              disabled={!provider.has_key || busy !== null}
              title="저장된 키 삭제"
              onClick={() =>
                run("clear", async () => {
                  await adminApi.saveIntegration(provider.provider, { api_key: "" });
                  toast.success(`${provider.label} 키를 삭제했습니다.`);
                })
              }
            >
              {busy === "clear" ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Trash2 className="h-3.5 w-3.5" />
              )}
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
