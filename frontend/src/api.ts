type ApiErrorBody = {
  detail?: string | Array<{ msg?: string }>;
};

export async function apiRequest<T>(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(input, init);
  const body = await response.json().catch(() => null) as ApiErrorBody | T | null;

  if (!response.ok) {
    let message = `Erro ${response.status}`;
    if (body && typeof body === 'object' && 'detail' in body) {
      if (typeof body.detail === 'string') message = body.detail;
      else if (Array.isArray(body.detail)) {
        message = body.detail.map(item => item.msg).filter(Boolean).join(', ');
      }
    }
    throw new Error(message);
  }

  return body as T;
}
