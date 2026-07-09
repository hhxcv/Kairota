import type { QueueWorkbench, Repository, RuntimeHealth } from "./workbench";

const defaultApiBaseUrl = "http://127.0.0.1:8010";

export async function fetchQueueWorkbench(
  signal?: AbortSignal,
): Promise<QueueWorkbench> {
  const baseUrl = getApiBaseUrl();
  const response = await fetch(`${baseUrl}/queue/workbench`, { signal });
  if (!response.ok) {
    throw new Error(`Queue workbench request failed with ${response.status}`);
  }
  return (await response.json()) as QueueWorkbench;
}

export async function fetchRuntimeHealth(
  signal?: AbortSignal,
): Promise<RuntimeHealth> {
  const baseUrl = getApiBaseUrl();
  const response = await fetch(`${baseUrl}/healthz`, { signal });
  if (!response.ok) {
    throw new Error(`Health request failed with ${response.status}`);
  }
  return (await response.json()) as RuntimeHealth;
}

export async function fetchRepositories(
  signal?: AbortSignal,
): Promise<Repository[]> {
  const baseUrl = getApiBaseUrl();
  const response = await fetch(`${baseUrl}/repositories`, { signal });
  if (!response.ok) {
    throw new Error(`Repositories request failed with ${response.status}`);
  }
  return (await response.json()) as Repository[];
}

export function getApiBaseUrl(): string {
  return (import.meta.env.VITE_KAIROTA_API_BASE_URL || defaultApiBaseUrl).replace(
    /\/$/,
    "",
  );
}
