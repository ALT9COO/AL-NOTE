const DB_NAME = "alnote-audio";
const STORE = "recordings";
const KEY = "latest";

export type CachedRecording = {
  blob: Blob;
  mimeType: string;
  createdAt: number;
  seconds: number;
  eventTitle?: string | null;
};

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) db.createObjectStore(STORE);
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

export async function saveCachedRecording(record: CachedRecording) {
  try {
    const db = await openDb();
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE, "readwrite");
      tx.objectStore(STORE).put(record, KEY);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
    db.close();
  } catch {
    /* private mode / quota */
  }
}

export async function loadCachedRecording(): Promise<CachedRecording | null> {
  try {
    const db = await openDb();
    const record = await new Promise<CachedRecording | null>((resolve, reject) => {
      const tx = db.transaction(STORE, "readonly");
      const req = tx.objectStore(STORE).get(KEY);
      req.onsuccess = () => resolve((req.result as CachedRecording | undefined) ?? null);
      req.onerror = () => reject(req.error);
    });
    db.close();
    if (!record?.blob || record.blob.size <= 0) return null;
    return record;
  } catch {
    return null;
  }
}

export async function clearCachedRecording() {
  try {
    const db = await openDb();
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE, "readwrite");
      tx.objectStore(STORE).delete(KEY);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
    db.close();
  } catch {
    /* ignore */
  }
}

export function recordingFilename(mimeType?: string) {
  if (mimeType?.includes("mp4") || mimeType?.includes("aac")) return "recording.m4a";
  return "recording.webm";
}
