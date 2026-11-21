export class HttpError extends Error {
  constructor(readonly status: number) { super(`HTTP ${status}`) }
}
export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  if (!response.ok) throw new HttpError(response.status)
  return response.json() as Promise<T>
}
export function json(method: string, body: unknown, headers?: Record<string,string>): RequestInit {
  return { method, headers: { 'Content-Type': 'application/json', ...headers }, body: JSON.stringify(body) }
}
