export interface AccessToken {
  id: string
  name: string
  createdAt: number
  lastUsedAt: number | null
}

async function ok(res: Response): Promise<Response> {
  if (!res.ok) throw new Error(`Request failed (${res.status})`)
  return res
}

export async function listTokens(): Promise<AccessToken[]> {
  return (await ok(await fetch('/api/tokens'))).json()
}

export async function createToken(name: string): Promise<{ id: string; name: string; token: string }> {
  const res = await fetch('/api/tokens', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
  return (await ok(res)).json()
}

export async function revokeToken(id: string): Promise<void> {
  await ok(await fetch(`/api/tokens/${encodeURIComponent(id)}`, { method: 'DELETE' }))
}
