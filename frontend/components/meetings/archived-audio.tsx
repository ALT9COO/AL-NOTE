"use client";

import { useEffect, useRef, useState } from "react";
import { Download, Loader2, Volume2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { apiErrorMessage, meetingApi } from "@/lib/api";

function formatBytes(size?: number | null) {
  if (!size || size <= 0) return "";
  if (size < 1024) return `${size}B`;
  if (size < 1024 * 1024) return `${Math.round(size / 1024)}KB`;
  return `${(size / (1024 * 1024)).toFixed(1)}MB`;
}

export function ArchivedAudio({
  kind,
  id,
  name,
  size,
}: {
  kind: "meeting" | "draft";
  id: number;
  name?: string | null;
  size?: number | null;
}) {
  const [url, setUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    let objectUrl = "";
    let cancelled = false;
    setLoading(true);
    setFailed(false);
    meetingApi
      .audioBlob(kind, id)
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      })
      .catch((error) => {
        if (!cancelled) {
          setFailed(true);
          toast.error(apiErrorMessage(error, "음성을 불러오지 못했습니다."));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [kind, id]);

  function download() {
    if (!url) return;
    const link = document.createElement("a");
    link.href = url;
    link.download = name || "recording.webm";
    document.body.appendChild(link);
    link.click();
    link.remove();
  }

  return (
    <div className="space-y-2 rounded-lg border bg-muted/30 p-3">
      <div className="flex items-center justify-between gap-2">
        <p className="flex items-center gap-1.5 text-xs font-medium">
          <Volume2 className="h-3.5 w-3.5 text-primary" />
          음성 기록
          {name ? <span className="font-normal text-muted-foreground">· {name}</span> : null}
          {size ? <span className="font-normal text-muted-foreground">· {formatBytes(size)}</span> : null}
        </p>
        {url ? (
          <Button size="sm" variant="outline" className="h-7 px-2 text-[11px]" onClick={download}>
            <Download className="h-3 w-3" />
            저장
          </Button>
        ) : null}
      </div>
      {loading ? (
        <div className="flex h-10 items-center justify-center text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
        </div>
      ) : url && !failed ? (
        <audio
          ref={audioRef}
          controls
          preload="metadata"
          src={url}
          className="w-full"
          onError={() => setFailed(true)}
        />
      ) : (
        <p className="text-[11px] text-muted-foreground">음성 파일을 재생할 수 없습니다.</p>
      )}
    </div>
  );
}
