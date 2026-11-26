export interface Connection {
  id: string
  workspace: string
  connectedAt: number
}
export interface Integrations {
  slack: { enabled: boolean; connections: Connection[] }
  notion: { enabled: boolean; connections: Connection[]; databaseUrl: string | null }
}

async function ok(res: Response): Promise<Response> {
  if (!res.ok) throw new Error(`Request failed (${res.status})`)
  return res
}

export async function listIntegrations(): Promise<Integrations> {
  return (await ok(await fetch('/api/integrations'))).json()
}

export async function disconnectIntegration(id: string): Promise<void> {
  await ok(await fetch(`/api/integrations/${encodeURIComponent(id)}`, { method: 'DELETE' }))
}
