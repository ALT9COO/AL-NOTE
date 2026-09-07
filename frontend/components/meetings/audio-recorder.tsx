"use client";

import { useState } from "react";
import { Loader2, Mic, Square, Upload, Wand2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { apiErrorMessage, finishTranscription, meetingApi, transcribeArchiveFromError } from "@/lib/api";
import { formatRecordingTime, isRecordingSecureContext, useRecording } from "@/lib/recording-context";
import { cn } from "@/lib/utils";
import type { CalendarEvent } from "@/types";

interface AudioRecorderProps {
  event?: CalendarEvent | null;
  onTranscript: (transcript: string, draftId?: number | null) => void;
}

export function AudioRecorder({ event, onTranscript }: AudioRecorderProps) {
  const {
    status,
    seconds,
    startRecording,
    stopRecording,
    retryTranscription,
    downloadBackup,
    discardBackup,
    backupBytes,
  } = useRecording();
  const [manualText, setManualText] = useState("");
  const [uploadingFile, setUploadingFile] = useState(false);

  const recording = status === "recording";
  const uploading = status === "uploading" || uploadingFile;
  const busy = recording || uploading;
  const insecure = !isRecordingSecureContext();

  async function sendFile(blob: Blob, filename: string) {
    setUploadingFile(true);
    try {
      const uploaded = await meetingApi.transcribe(blob, filename);
      if (uploaded.draft_id && event) {
        try {
          await meetingApi.updateDraft(uploaded.draft_id, {
            event,
            step: 1,
          });
        } catch {
          /* ignore */
        }
      }
      if (uploaded.stt_status === "transcribing") {
        toast.info("음성을 올렸습니다. 전사를 진행 중입니다…");
      }
      const result = await finishTranscription(uploaded);
      if (result.stt_status === "error") {
        onTranscript("", result.draft_id);
        toast.warning(
          `${result.stt_error || "전사에 실패했습니다."} 아래에서 다시 듣거나 회의록으로 보관할 수 있습니다.`,
        );
        return;
      }
      if (result.draft_id && event) {
        try {
          await meetingApi.updateDraft(result.draft_id, {
            event,
            step: 2,
            transcript: result.transcript,
          });
        } catch {
          /* ignore */
        }
      }
      onTranscript(result.transcript, result.draft_id);
      toast.success(result.mock ? "데모 전사본을 불러왔습니다." : "전사가 완료되었습니다. 음성은 회의록과 함께 보관됩니다.");
    } catch (error) {
      const archived = transcribeArchiveFromError(error);
      if (archived) {
        onTranscript("", archived.draft_id);
        toast.warning(`${archived.message} 아래에서 다시 듣거나 회의록으로 보관할 수 있습니다.`);
        return;
      }
      toast.error(apiErrorMessage(error, "전사에 실패했습니다."));
    } finally {
      setUploadingFile(false);
    }
  }

  function handleFile(evt: React.ChangeEvent<HTMLInputElement>) {
    const file = evt.target.files?.[0];
    if (!file) return;
    if (file.size > 200 * 1024 * 1024) {
      toast.error("파일 크기는 200MB 이하여야 합니다.");
      evt.target.value = "";
      return;
    }
    void sendFile(file, file.name);
    evt.target.value = "";
  }

  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <Card className="lg:col-span-1">
        <CardContent className="flex h-full flex-col items-center justify-center gap-3 p-6">
          <button
            type="button"
            onClick={() => (recording ? stopRecording() : void startRecording(event))}
            disabled={uploading}
            className={cn(
              "flex h-20 w-20 items-center justify-center rounded-full text-white shadow-lg transition-all disabled:opacity-50",
              recording
                ? "animate-pulse bg-red-500 ring-8 ring-red-100"
                : "bg-gradient-to-br from-blue-600 to-cyan-500 hover:scale-105",
            )}
          >
            {recording ? <Square className="h-7 w-7" /> : <Mic className="h-8 w-8" />}
          </button>
          <div className="text-center">
            <p className="text-sm font-medium">
              {recording
                ? "녹음 중… 다른 페이지로 이동해도 유지됩니다"
                : uploading
                  ? "전사 처리 중…"
                  : status === "failed"
                    ? "음성 백업이 있습니다"
                    : "브라우저에서 바로 녹음"}
            </p>
            <p className="font-mono text-xs text-muted-foreground">
              {formatRecordingTime(seconds)}
            </p>
            {status === "failed" ? (
              <div className="mt-3 flex w-full max-w-[240px] flex-col gap-2">
                <p className="text-[11px] leading-4 text-amber-800">
                  네트워크가 끊겨도 음성은 이 브라우저에 남아 있습니다
                  {backupBytes ? ` (${Math.max(1, Math.round(backupBytes / 1024))}KB)` : ""}.
                </p>
                <Button size="sm" onClick={() => void retryTranscription()}>
                  다시 전사
                </Button>
                <Button size="sm" variant="outline" onClick={downloadBackup}>
                  음성 파일 저장
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => void startRecording(event)}
                >
                  무시하고 새로 녹음
                </Button>
                <button
                  type="button"
                  className="text-[11px] text-muted-foreground underline-offset-2 hover:underline"
                  onClick={() => void discardBackup()}
                >
                  백업만 버리고 닫기
                </button>
              </div>
            ) : null}
            {insecure ? (
              <p className="mt-2 max-w-[220px] text-[11px] leading-4 text-amber-700">
                휴대폰 HTTP 접속에서는 마이크가 막힙니다. 아래 파일 업로드를 사용하세요.
              </p>
            ) : null}
          </div>
        </CardContent>
      </Card>

      <Card className="lg:col-span-2">
        <CardContent className="space-y-4 p-5">
          <div className="space-y-2">
            <p className="text-sm font-medium">오디오 파일 업로드</p>
            <label
              className={cn(
                "flex cursor-pointer items-center justify-center gap-2 rounded-lg border border-dashed px-4 py-6 text-sm text-muted-foreground transition-colors hover:border-primary/50 hover:bg-primary/5",
                busy && "pointer-events-none opacity-60",
              )}
            >
              {uploadingFile ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Upload className="h-4 w-4" />
              )}
              mp3 · wav · m4a · webm (최대 200MB)
              <input
                type="file"
                accept="audio/*,.mp3,.wav,.m4a,.webm"
                className="hidden"
                onChange={handleFile}
                disabled={busy}
              />
            </label>
            <p className="text-[11px] text-muted-foreground">
              1시간 이상 회의는 브라우저 녹음보다 파일 업로드를 권장합니다.
            </p>
          </div>

          <div className="space-y-2">
            <p className="text-sm font-medium">또는 회의 내용을 직접 붙여넣기</p>
            <Textarea
              rows={4}
              value={manualText}
              onChange={(e) => setManualText(e.target.value)}
              placeholder={"박팀장: 로그인 API 진행 상황 공유 바랍니다.\n이사원: 90% 완료했고 이번 주 마무리 예정입니다."}
            />
            <Button
              variant="secondary"
              className="w-full"
              disabled={!manualText.trim() || busy}
              onClick={() => {
                onTranscript(manualText.trim());
                toast.success("전사본으로 사용합니다.");
              }}
            >
              <Wand2 className="h-4 w-4" />이 텍스트 사용
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
