import type { QueueWorkbench } from "./workbench";

const defaultApiBaseUrl = "http://127.0.0.1:8010";

export async function fetchQueueWorkbench(
  signal?: AbortSignal,
): Promise<QueueWorkbench> {
  const baseUrl = apiBaseUrl();
  const response = await fetch(`${baseUrl}/queue/workbench`, { signal });
  if (!response.ok) {
    throw new Error(`Queue workbench request failed with ${response.status}`);
  }
  return (await response.json()) as QueueWorkbench;
}

function apiBaseUrl(): string {
  return (import.meta.env.VITE_KAIROTA_API_BASE_URL || defaultApiBaseUrl).replace(
    /\/$/,
    "",
  );
}
