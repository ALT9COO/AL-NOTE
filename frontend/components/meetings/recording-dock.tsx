"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Download, Loader2, Mic, RefreshCw, Square, X } from "lucide-react";

import { formatRecordingTime, useRecording } from "@/lib/recording-context";
import { cn } from "@/lib/utils";

export function RecordingDock() {
  const {
    status,
    seconds,
    event,
    stopRecording,
    hideDock,
    dockHidden,
    retryTranscription,
    downloadBackup,
    discardBackup,
  } = useRecording();
  const pathname = usePathname();
  const router = useRouter();

  if (status === "idle") return null;
  if (status === "ready" && dockHidden) return null;
  if (status === "failed" && dockHidden) return null;

  const onMeetings = pathname.startsWith("/meetings");

  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-5 z-50 flex justify-center px-4 lg:pl-64">
      <div
        className={cn(
          "pointer-events-auto flex max-w-[min(100%,520px)] items-center gap-3 rounded-full border px-3 py-2 shadow-2xl",
          status === "ready"
            ? "border-emerald-200 bg-emerald-600 text-white"
            : status === "failed"
              ? "border-amber-200 bg-slate-900 text-white"
              : "border-red-200 bg-slate-900 text-white",
        )}
      >
        <button
          type="button"
          onClick={() => {
            if (!onMeetings) router.push("/meetings");
          }}
          className={cn(
            "flex h-10 w-10 shrink-0 items-center justify-center rounded-full",
            status === "recording" && "animate-pulse bg-red-500",
            status === "uploading" && "bg-white/15",
            status === "ready" && "bg-white/20",
            status === "failed" && "bg-amber-500",
          )}
          title={onMeetings ? "녹음 중" : "회의실로 이동"}
        >
          {status === "uploading" ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Mic className="h-4 w-4" />
          )}
        </button>

        <div className="min-w-0 flex-1">
          <p className="truncate text-xs font-semibold">
            {status === "recording"
              ? "회의 녹음 중"
              : status === "uploading"
                ? "음성 전사 중…"
                : status === "failed"
                  ? "전사 실패 · 음성은 보관됨"
                  : "전사 완료"}
          </p>
          <p className="truncate font-mono text-[11px] text-white/75">
            {status === "ready"
              ? event?.title || "회의실에서 확인하세요"
              : `${formatRecordingTime(seconds)}${event?.title ? ` · ${event.title}` : ""}`}
          </p>
        </div>

        {status === "recording" ? (
          <button
            type="button"
            onClick={stopRecording}
            className="flex h-9 items-center gap-1.5 rounded-full bg-red-500 px-3 text-xs font-medium hover:bg-red-400"
          >
            <Square className="h-3 w-3 fill-current" />
            종료
          </button>
        ) : null}

        {status === "failed" ? (
          <>
            <button
              type="button"
              onClick={() => void retryTranscription()}
              className="flex h-9 items-center gap-1 rounded-full bg-amber-500 px-3 text-xs font-semibold text-slate-900 hover:bg-amber-400"
            >
              <RefreshCw className="h-3 w-3" />
              다시 전사
            </button>
            <button
              type="button"
              onClick={downloadBackup}
              className="flex h-8 w-8 items-center justify-center rounded-full hover:bg-white/15"
              title="음성 파일 저장"
            >
              <Download className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={() => void discardBackup()}
              className="flex h-8 w-8 items-center justify-center rounded-full hover:bg-white/15"
              title="무시하고 닫기"
            >
              <X className="h-4 w-4" />
            </button>
          </>
        ) : null}

        {status === "ready" ? (
          <>
            {!onMeetings ? (
              <Link
                href="/meetings"
                className="rounded-full bg-white px-3 py-1.5 text-xs font-semibold text-emerald-700 hover:bg-emerald-50"
              >
                회의실
              </Link>
            ) : null}
            <button
              type="button"
              onClick={hideDock}
              className="flex h-8 w-8 items-center justify-center rounded-full hover:bg-white/15"
              title="팝업만 닫기 (전사는 헤더에서 다시 열 수 있습니다)"
            >
              <X className="h-4 w-4" />
            </button>
          </>
        ) : null}
      </div>
    </div>
  );
}

export function RecordingHeaderChip() {
  const { status, seconds } = useRecording();
  if (status === "idle") return null;

  return (
    <Link
      href="/meetings"
      className={cn(
        "flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium",
        status === "ready"
          ? "bg-emerald-50 text-emerald-700"
          : status === "failed"
            ? "bg-amber-50 text-amber-800"
            : "bg-red-50 text-red-600",
      )}
      title="AI 회의실로 이동"
    >
      <span
        className={cn(
          "h-2 w-2 rounded-full",
          status === "recording" && "animate-pulse bg-red-500",
          status === "uploading" && "bg-amber-500",
          status === "ready" && "bg-emerald-500",
          status === "failed" && "bg-amber-600",
        )}
      />
      {status === "recording"
        ? `녹음 ${formatRecordingTime(seconds)}`
        : status === "uploading"
          ? "전사 중"
          : status === "failed"
            ? "음성 보관됨"
            : "전사 완료"}
    </Link>
  );
}
