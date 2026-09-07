"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { toast } from "sonner";

import { apiErrorMessage, finishTranscription, meetingApi, transcribeArchiveFromError } from "@/lib/api";
import {
  clearCachedRecording,
  loadCachedRecording,
  recordingFilename,
  saveCachedRecording,
} from "@/lib/audio-cache";
import { writeLocalDraft } from "@/lib/meeting-draft";
import type { CalendarEvent } from "@/types";

export type RecordingStatus = "idle" | "recording" | "uploading" | "ready" | "failed";

interface RecordingContextValue {
  status: RecordingStatus;
  seconds: number;
  event: CalendarEvent | null;
  transcript: string | null;
  draftId: number | null;
  backupBytes: number;
  startRecording: (event?: CalendarEvent | null) => Promise<void>;
  stopRecording: () => void;
  retryTranscription: () => Promise<void>;
  downloadBackup: () => void;
  discardBackup: () => Promise<void>;
  acknowledgeTranscript: () => string | null;
  hideDock: () => void;
  dockHidden: boolean;
}

const RecordingContext = createContext<RecordingContextValue | undefined>(undefined);

export function formatRecordingTime(total: number) {
  return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}

export function isRecordingSecureContext() {
  return typeof window === "undefined" || window.isSecureContext;
}

function micErrorMessage(error: unknown) {
  const name = error instanceof DOMException || error instanceof Error ? error.name : "";
  const message = error instanceof Error ? error.message : "";
  if (name === "SecurityError" || message === "insecure-context" || (typeof window !== "undefined" && !window.isSecureContext)) {
    return "휴대폰에서는 HTTPS(보안 연결)가 아니면 마이크를 켤 수 없습니다. PC에서 녹음하거나, 오디오 파일을 올려 주세요.";
  }
  if (name === "NotAllowedError" || name === "PermissionDeniedError") {
    return "브라우저 마이크 권한이 차단되어 있습니다. Chrome 사이트 설정에서 마이크를 허용한 뒤 다시 시도하세요.";
  }
  if (name === "NotFoundError" || name === "DevicesNotFoundError") {
    return "사용할 수 있는 마이크를 찾지 못했습니다.";
  }
  if (name === "NotSupportedError" || message === "no-media-devices") {
    return "이 브라우저에서는 바로 녹음을 지원하지 않습니다. 오디오 파일을 올려 주세요.";
  }
  return "마이크를 열 수 없습니다. 휴대폰에서는 파일 업로드를 권장합니다.";
}

function snapshotBlob(chunks: BlobPart[], mimeType: string) {
  if (!chunks.length) return null;
  return new Blob(chunks, { type: mimeType || "audio/webm" });
}

export function RecordingProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<RecordingStatus>("idle");
  const [seconds, setSeconds] = useState(0);
  const [event, setEvent] = useState<CalendarEvent | null>(null);
  const [transcript, setTranscript] = useState<string | null>(null);
  const [draftId, setDraftId] = useState<number | null>(null);
  const [dockHidden, setDockHidden] = useState(false);
  const [backupBytes, setBackupBytes] = useState(0);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const eventRef = useRef<CalendarEvent | null>(null);
  const blobRef = useRef<Blob | null>(null);
  const mimeRef = useRef("audio/webm");
  const secondsRef = useRef(0);
  const persistTick = useRef(0);

  const clearTimer = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const releaseMic = useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    recorderRef.current = null;
  }, []);

  const persistBackup = useCallback(async (blob: Blob, elapsed: number) => {
    blobRef.current = blob;
    setBackupBytes(blob.size);
    await saveCachedRecording({
      blob,
      mimeType: blob.type || mimeRef.current,
      createdAt: Date.now(),
      seconds: elapsed,
      eventTitle: eventRef.current?.title ?? null,
    });
  }, []);

  const transcribeBlob = useCallback(
    async (blob: Blob, filename: string) => {
      blobRef.current = blob;
      setBackupBytes(blob.size);
      setStatus("uploading");
      try {
        const uploaded = await meetingApi.transcribe(blob, filename);
        const linkedEvent = eventRef.current;
        setDraftId(uploaded.draft_id ?? null);
        if (uploaded.draft_id && linkedEvent) {
          try {
            await meetingApi.updateDraft(uploaded.draft_id, {
              event: linkedEvent,
              step: 1,
            });
          } catch {
            /* 초안 일정 연결은 실패해도 전사는 유지 */
          }
        }
        if (uploaded.stt_status === "transcribing") {
          toast.info("음성을 올렸습니다. 전사를 진행 중입니다…");
        }
        const result = await finishTranscription(uploaded);
        if (result.stt_status === "error") {
          await clearCachedRecording();
          blobRef.current = null;
          setBackupBytes(0);
          setTranscript("");
          setStatus("ready");
          setDockHidden(false);
          toast.warning(
            `${result.stt_error || "전사에 실패했습니다."} 음성은 회의실에 보관되어 있습니다.`,
          );
          return;
        }
        setTranscript(result.transcript);
        writeLocalDraft({
          draftId: result.draft_id ?? null,
          step: 2,
          transcript: result.transcript,
          parsed: null,
          event: linkedEvent,
        });
        if (result.draft_id && linkedEvent) {
          try {
            await meetingApi.updateDraft(result.draft_id, {
              event: linkedEvent,
              step: 2,
              transcript: result.transcript,
            });
          } catch {
            /* 초안 일정 연결은 실패해도 전사는 유지 */
          }
        }
        await clearCachedRecording();
        blobRef.current = null;
        setBackupBytes(0);
        setStatus("ready");
        setDockHidden(false);
        toast.success(
          result.mock
            ? "데모 전사본이 준비되었습니다. 회의실에서 확인하세요."
            : "전사가 완료되었습니다. 음성은 회의록과 함께 보관됩니다.",
        );
      } catch (error) {
        const archived = transcribeArchiveFromError(error);
        if (archived) {
          await clearCachedRecording();
          blobRef.current = null;
          setBackupBytes(0);
          setDraftId(archived.draft_id);
          setTranscript("");
          setStatus("ready");
          setDockHidden(false);
          toast.warning(`${archived.message} 회의실에서 다시 듣거나 회의록으로 보관할 수 있습니다.`);
          return;
        }
        setStatus("failed");
        setDockHidden(false);
        toast.error(
          `${apiErrorMessage(error, "전사에 실패했습니다.")} 음성은 이 브라우저에 보관되어 있으니 다시 전사하거나 파일로 저장하세요.`,
        );
      }
    },
    [],
  );

  const startRecording = useCallback(
    async (nextEvent?: CalendarEvent | null) => {
      if (recorderRef.current && recorderRef.current.state === "recording") return;
      try {
        if (typeof window !== "undefined" && !window.isSecureContext) {
          throw Object.assign(new Error("insecure-context"), { name: "SecurityError" });
        }
        if (!navigator.mediaDevices?.getUserMedia) {
          throw Object.assign(new Error("no-media-devices"), { name: "NotSupportedError" });
        }
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: { echoCancellation: true, noiseSuppression: true },
        });
        const mimeType = [
          "audio/webm;codecs=opus",
          "audio/webm",
          "audio/mp4",
          "audio/aac",
        ].find((type) => typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported(type));
        const recorder = mimeType
          ? new MediaRecorder(stream, { mimeType })
          : new MediaRecorder(stream);

        chunksRef.current = [];
        persistTick.current = 0;
        streamRef.current = stream;
        recorderRef.current = recorder;
        mimeRef.current = recorder.mimeType || "audio/webm";
        blobRef.current = null;
        setBackupBytes(0);
        await clearCachedRecording();

        recorder.ondataavailable = (evt) => {
          if (evt.data.size > 0) chunksRef.current.push(evt.data);
          persistTick.current += 1;
          if (persistTick.current % 5 === 0) {
            const snapshot = snapshotBlob(chunksRef.current, mimeRef.current);
            if (snapshot) void persistBackup(snapshot, secondsRef.current);
          }
        };
        recorder.onstop = () => {
          const blob = snapshotBlob(chunksRef.current, mimeRef.current);
          releaseMic();
          clearTimer();
          if (!blob || blob.size <= 0) {
            setStatus("idle");
            toast.error("녹음 데이터가 비어 있습니다.");
            return;
          }
          void persistBackup(blob, secondsRef.current).then(() =>
            transcribeBlob(blob, recordingFilename(blob.type)),
          );
        };

        recorder.start(1000);
        eventRef.current = nextEvent ?? null;
        setEvent(nextEvent ?? null);
        setTranscript(null);
        setSeconds(0);
        secondsRef.current = 0;
        setStatus("recording");
        setDockHidden(false);
        timerRef.current = setInterval(() => {
          setSeconds((value) => {
            secondsRef.current = value + 1;
            return value + 1;
          });
        }, 1000);
      } catch (error) {
        releaseMic();
        toast.error(micErrorMessage(error));
      }
    },
    [clearTimer, persistBackup, releaseMic, transcribeBlob],
  );

  const stopRecording = useCallback(() => {
    const recorder = recorderRef.current;
    if (!recorder || recorder.state === "inactive") return;
    recorder.stop();
    clearTimer();
  }, [clearTimer]);

  const retryTranscription = useCallback(async () => {
    const blob = blobRef.current;
    if (!blob) {
      toast.error("다시 전사할 음성 백업이 없습니다.");
      return;
    }
    await transcribeBlob(blob, recordingFilename(blob.type));
  }, [transcribeBlob]);

  const downloadBackup = useCallback(() => {
    const blob = blobRef.current;
    if (!blob) {
      toast.error("저장할 음성 백업이 없습니다.");
      return;
    }
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = recordingFilename(blob.type);
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }, []);

  const discardBackup = useCallback(async () => {
    blobRef.current = null;
    setBackupBytes(0);
    await clearCachedRecording();
    if (status === "failed") setStatus("idle");
  }, [status]);

  const acknowledgeTranscript = useCallback(() => {
    const text = transcript;
    setTranscript(null);
    setStatus("idle");
    setDockHidden(false);
    return text;
  }, [transcript]);

  const hideDock = useCallback(() => {
    setDockHidden(true);
  }, []);

  useEffect(() => {
    if (status !== "recording") return;
    const onUnload = (evt: BeforeUnloadEvent) => {
      evt.preventDefault();
      evt.returnValue = "";
    };
    window.addEventListener("beforeunload", onUnload);
    return () => window.removeEventListener("beforeunload", onUnload);
  }, [status]);

  useEffect(() => {
    let cancelled = false;
    void loadCachedRecording().then((cached) => {
      if (cancelled || !cached) return;
      if (recorderRef.current) return;
      blobRef.current = cached.blob;
      mimeRef.current = cached.mimeType;
      setBackupBytes(cached.blob.size);
      setSeconds(cached.seconds);
      secondsRef.current = cached.seconds;
      setStatus((current) => (current === "idle" ? "failed" : current));
      toast.message("이전에 끊긴 녹음이 이 브라우저에 남아 있습니다. 다시 전사하거나 파일로 저장하세요.");
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    return () => {
      clearTimer();
      if (recorderRef.current && recorderRef.current.state === "recording") {
        recorderRef.current.onstop = null;
        recorderRef.current.stop();
      }
      releaseMic();
    };
  }, [clearTimer, releaseMic]);

  const value = useMemo(
    () => ({
      status,
      seconds,
      event,
      transcript,
      draftId,
      backupBytes,
      startRecording,
      stopRecording,
      retryTranscription,
      downloadBackup,
      discardBackup,
      acknowledgeTranscript,
      hideDock,
      dockHidden,
    }),
    [
      status,
      seconds,
      event,
      transcript,
      draftId,
      backupBytes,
      startRecording,
      stopRecording,
      retryTranscription,
      downloadBackup,
      discardBackup,
      acknowledgeTranscript,
      hideDock,
      dockHidden,
    ],
  );

  return <RecordingContext.Provider value={value}>{children}</RecordingContext.Provider>;
}

export function useRecording() {
  const context = useContext(RecordingContext);
  if (!context) throw new Error("useRecording 은 RecordingProvider 내부에서만 사용할 수 있습니다.");
  return context;
}
