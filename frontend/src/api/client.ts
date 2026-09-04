import type { SceneDocument } from '@/types/scene'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api/v3'
const SESSION_STORAGE_KEY = 'prompt-to-world-session'

export type GenerationStatus =
  | 'queued'
  | 'generating'
  | 'validating'
  | 'enhancing'
  | 'partial'
  | 'succeeded'
  | 'failed'
  | 'cancelled'

export interface SceneSummary {
  sceneId: string
  title: string
  currentVersionId: string
  prompt: string
  schemaVersion: string
  nodeCount: number
  versionKind?: 'draft' | 'final' | null
  styleKit?: string | null
  quality?: string | null
  changeSummary?: string | null
  thumbnail?: { background: string; accent: string }
  createdAt: string
  updatedAt: string
}

export interface SceneDetail extends SceneSummary {
  intentPreview?: IntentPreview | null
  coverage?: FidelityReport | null
  unsupportedEntities?: UnsupportedEntity[]
  resolutionTrace?: ResolutionTrace[]
  version: {
    versionId: string
    versionNumber: number
    schemaVersion: string
    sceneJson: SceneDocument
    prompt: string
    seed: number
    provider: string
    model: string
    parentVersionId?: string | null
    versionKind?: 'draft' | 'final'
    changeSummary?: string | null
    planJson?: Record<string, unknown> | null
    compilerVersion?: string | null
    styleKit?: string | null
    quality?: string | null
    createdAt: string
  }
}

export interface GenerationJob {
  jobId: string
  status: GenerationStatus
  prompt: string
  provider: string
  model: string
  error: { code: string; message: string } | null
  durationMs: number | null
  usage: {
    promptTokens: number | null
    completionTokens: number | null
  }
  retryCount: number
  sceneId: string | null
  sceneVersionId: string | null
  apiVersion?: string
  currentStage?: string | null
  requestFingerprint?: string | null
  draftVersionId?: string | null
  finalVersionId?: string | null
  stages?: GenerationStage[]
  createdAt: string
  updatedAt: string
  completedAt: string | null
  scene?: SceneDetail | null
  draft?: SceneDetail | null
  request?: {
    prompt: string
    preferences: GenerationPreferences
    intentPreview?: IntentPreview
  } | null
  intentPreview?: IntentPreview | null
  coverage?: FidelityReport | null
  unsupportedEntities?: UnsupportedEntity[]
}

export interface GenerationStage {
  stage: string
  status: 'running' | 'completed' | 'failed' | 'skipped'
  attempt: number
  durationMs: number | null
  checkpointVersionId: string | null
  errorCode: string | null
  metadataJson?: Record<string, unknown> | null
  startedAt: string
  completedAt: string | null
}

export interface IntentEntityPreview {
  id: string
  concept: string
  label: string
  role: 'hero' | 'supporting' | 'background' | 'structural'
  support: 'pending' | 'exact' | 'abstract' | 'unsupported'
  message?: string | null
}

export interface IntentPreview {
  title: string
  sceneMode: 'walkable' | 'interior' | 'orbital' | 'flythrough' | 'diorama' | 'panorama'
  entities: IntentEntityPreview[]
  relations: Array<{ sourceId: string; type: string; targetId: string; strength: number }>
  time: string
  weather: string
  styleKit: GenerationPreferences['styleKit']
}

export interface FidelityReport {
  status: 'pending' | 'passed' | 'failed'
  requiredCoverage: number
  relationSatisfaction: number
  forbiddenViolations: number
  unrelatedRatio: number
  heroVisible: boolean
  coveredEntityIds: string[]
  missingEntityIds: string[]
}

export interface UnsupportedEntity {
  entityId: string
  concept: string
  support: 'abstract' | 'unsupported'
  message: string | null
}

export interface ResolutionTrace {
  entityId: string
  concept: string
  category: string
  capabilityId: string
  capabilityVersion: string
  recipe: string
  support: 'exact' | 'abstract' | 'unsupported'
  confidence: number
  label: string
  message: string | null
}

export interface GenerationPreferences {
  styleKit: 'auto' | 'cyberpunk_tokyo_v1' | 'cozy_lowpoly_v1' | 'misty_nature_v1' | 'lunar_research_v1'
  time: 'auto' | 'day' | 'sunrise' | 'sunset' | 'night' | 'indoor'
  weather: 'auto' | 'clear' | 'rain' | 'mist' | 'dust'
  density: number
  quality: 'draft' | 'balanced' | 'quality'
  scale: 'compact' | 'medium' | 'wide'
  seed: number | null
}

export interface GenerationEvent {
  type: 'job.status' | 'intent.ready' | 'stage.started' | 'stage.completed' | 'draft.ready' | 'final.ready' | 'job.failed'
  data: unknown
}

export type SceneCommandType =
  | 'set_environment'
  | 'set_style_kit'
  | 'set_density'
  | 'remove_by_semantics'
  | 'remove_entity'
  | 'replace_entity'
  | 'add_entity'
  | 'change_relation'
  | 'change_scene_mode'

export interface StyleKit {
  id: GenerationPreferences['styleKit']
  name: string
  description: string
  palette: Record<string, string>
}

export class ApiError extends Error {
  code: string
  status: number

  constructor(message: string, code = 'API_ERROR', status = 500) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
  }
}

export function sessionId(): string {
  const existing = window.localStorage.getItem(SESSION_STORAGE_KEY)
  if (existing) return existing
  const created = `world_session_${crypto.randomUUID().replaceAll('-', '')}`
  window.localStorage.setItem(SESSION_STORAGE_KEY, created)
  return created
}

async function requestJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), 20_000)
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      ...init,
      signal: init.signal ?? controller.signal,
      headers: {
        'Content-Type': 'application/json',
        'X-Session-ID': sessionId(),
        ...init.headers,
      },
    })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) {
      const detail = payload?.detail ?? payload?.error ?? payload
      throw new ApiError(
        detail?.message ?? '服务暂时不可用，请稍后再试。',
        detail?.code ?? 'API_ERROR',
        response.status,
      )
    }
    return payload as T
  } catch (error) {
    if (error instanceof ApiError) throw error
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiError('请求超时，请检查后端服务。', 'REQUEST_TIMEOUT', 408)
    }
    throw new ApiError('无法连接生成服务，请确认后端已经启动。', 'NETWORK_ERROR', 503)
  } finally {
    window.clearTimeout(timeout)
  }
}

export function createGeneration(prompt: string, preferences: GenerationPreferences): Promise<GenerationJob> {
  return requestJson('/generations', {
    method: 'POST',
    headers: { 'Idempotency-Key': crypto.randomUUID() },
    body: JSON.stringify({ prompt, preferences }),
  })
}

export function getGeneration(jobId: string): Promise<GenerationJob> {
  return requestJson(`/generations/${encodeURIComponent(jobId)}`)
}

export function cancelGeneration(jobId: string): Promise<{ cancelled: boolean }> {
  return requestJson(`/generations/${encodeURIComponent(jobId)}/cancel`, { method: 'POST' })
}

export async function listScenes(): Promise<SceneSummary[]> {
  const payload = await requestJson<{ items: SceneSummary[] }>('/scenes?limit=30')
  return payload.items
}

export function getScene(sceneId: string): Promise<SceneDetail> {
  return requestJson(`/scenes/${encodeURIComponent(sceneId)}`)
}

export async function listSceneVersions(sceneId: string): Promise<SceneDetail[]> {
  const payload = await requestJson<{ items: SceneDetail[] }>(`/scenes/${encodeURIComponent(sceneId)}/versions`)
  return payload.items
}

export function restoreSceneVersion(sceneId: string, versionId: string): Promise<SceneDetail> {
  return requestJson(`/scenes/${encodeURIComponent(sceneId)}/versions/${encodeURIComponent(versionId)}/restore`, { method: 'POST' })
}

export function applySceneCommand(
  sceneId: string,
  sourceVersionId: string,
  type: SceneCommandType,
  parameters: Record<string, unknown>,
): Promise<SceneDetail> {
  return requestJson(`/scenes/${encodeURIComponent(sceneId)}/commands`, {
    method: 'POST',
    headers: { 'Idempotency-Key': crypto.randomUUID() },
    body: JSON.stringify({ sourceVersionId, type, parameters }),
  })
}

export async function listStyleKits(): Promise<StyleKit[]> {
  const payload = await requestJson<{ items: StyleKit[] }>('/style-kits')
  return payload.items
}

export async function streamGenerationEvents(
  jobId: string,
  onEvent: (event: GenerationEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  const response = await fetch(`${API_BASE}/generations/${encodeURIComponent(jobId)}/events`, {
    headers: { 'X-Session-ID': sessionId() },
    signal,
  })
  if (!response.ok || !response.body) throw new ApiError('渐进事件连接失败，将使用轮询继续。', 'SSE_UNAVAILABLE', response.status)
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (!signal.aborted) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const packets = buffer.split('\n\n')
    buffer = packets.pop() ?? ''
    for (const packet of packets) {
      let type: GenerationEvent['type'] | null = null
      let data = ''
      for (const line of packet.split('\n')) {
        if (line.startsWith('event: ')) type = line.slice(7) as GenerationEvent['type']
        if (line.startsWith('data: ')) data += line.slice(6)
      }
      if (type && data) onEvent({ type, data: JSON.parse(data) })
    }
  }
}
