import { Component, Suspense, lazy, type ErrorInfo, type PropsWithChildren, useCallback, useEffect, useMemo, useState } from 'react'
import { CornersOut, Warning } from '@phosphor-icons/react'
import sampleSceneData from '@shared/examples/cyberpunk-alley.json'
import {
  ApiError,
  applySceneCommand,
  cancelGeneration,
  createGeneration,
  getGeneration,
  getScene,
  listScenes,
  listSceneVersions,
  restoreSceneVersion,
  streamGenerationEvents,
  type GenerationJob,
  type GenerationPreferences,
  type FidelityReport,
  type IntentPreview,
  type SceneCommandType,
  type SceneDetail,
  type SceneSummary,
  type UnsupportedEntity,
} from '@/api/client'
import { GenerationStatus } from '@/components/GenerationStatus'
import { HistoryDrawer } from '@/components/HistoryDrawer'
import { IntentSummary } from '@/components/IntentSummary'
import { PromptComposer } from '@/components/PromptComposer'
import { SceneInspector } from '@/components/SceneInspector'
import { TopBar } from '@/components/TopBar'
import type { SceneDocument } from '@/types/scene'
import { isSceneV2, isSceneV3 } from '@/types/scene'
import { getSceneStats } from '@/utils/scene'

const DEFAULT_PROMPT = 'A small cyberpunk Japanese alley at night with ramen shops and neon signs.'
const WorldCanvas = lazy(() => import('@/components/scene/WorldCanvas').then((module) => ({ default: module.WorldCanvas })))
const DEFAULT_PREFERENCES: GenerationPreferences = {
  styleKit: 'auto', time: 'auto', weather: 'auto', density: 0.68, quality: 'balanced', scale: 'compact', seed: null,
}

interface RuntimeBoundaryState { failed: boolean }
class RuntimeBoundary extends Component<PropsWithChildren, RuntimeBoundaryState> {
  state: RuntimeBoundaryState = { failed: false }
  static getDerivedStateFromError(): RuntimeBoundaryState { return { failed: true } }
  componentDidCatch(error: Error, info: ErrorInfo) { console.error('Scene runtime failed', error, info.componentStack) }
  render() { return this.state.failed ? <div className="runtime-fallback" role="alert"><Warning size={28} weight="fill" /><strong>场景运行时遇到错误</strong><span>请刷新页面，或从历史记录重新打开一个场景。</span></div> : this.props.children }
}

function wait(milliseconds: number): Promise<void> { return new Promise((resolve) => window.setTimeout(resolve, milliseconds)) }
function messageFrom(error: unknown): string { return error instanceof ApiError ? error.message : error instanceof Error ? error.message : '发生未知错误，请稍后再试。' }

export default function App() {
  const [scene, setScene] = useState<SceneDocument>(sampleSceneData as SceneDocument)
  const [prompt, setPrompt] = useState(DEFAULT_PROMPT)
  const [preferences, setPreferences] = useState<GenerationPreferences>(DEFAULT_PREFERENCES)
  const [history, setHistory] = useState<SceneSummary[]>([])
  const [versions, setVersions] = useState<SceneDetail[]>([])
  const [historyOpen, setHistoryOpen] = useState(false)
  const [inspectorOpen, setInspectorOpen] = useState(false)
  const [loadingSceneId, setLoadingSceneId] = useState<string | null>(null)
  const [activeSceneId, setActiveSceneId] = useState<string | null>(null)
  const [activeVersionId, setActiveVersionId] = useState<string | null>(null)
  const [activeJobId, setActiveJobId] = useState<string | null>(null)
  const [job, setJob] = useState<GenerationJob | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [connected, setConnected] = useState<boolean | null>(null)
  const [locked, setLocked] = useState(false)
  const [resetRequest, setResetRequest] = useState(0)
  const [runtimeError, setRuntimeError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [commandBusy, setCommandBusy] = useState(false)
  const [intentPreview, setIntentPreview] = useState<IntentPreview | null>(null)
  const [coverage, setCoverage] = useState<FidelityReport | null>(null)
  const [unsupportedEntities, setUnsupportedEntities] = useState<UnsupportedEntity[]>([])
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    const saved = window.localStorage.getItem('prompt-to-world-theme')
    if (saved === 'light' || saved === 'dark') return saved
    return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
  })

  const stats = useMemo(() => getSceneStats(scene), [scene])
  const isGenerating = activeJobId !== null
  const versionKind = isSceneV2(scene) || isSceneV3(scene) ? scene.pipeline.versionKind : 'final'
  const styleName = isSceneV2(scene) || isSceneV3(scene) ? ({ cyberpunk_tokyo_v1: '东京霓雨', cozy_lowpoly_v1: '暖木低模', misty_nature_v1: '雾林石径', lunar_research_v1: '轨道晨光' }[scene.pipeline.styleKit]) : 'V1 场景'
  const orbitMode = scene.camera.mode !== 'firstPerson'

  useEffect(() => { document.documentElement.dataset.theme = theme; window.localStorage.setItem('prompt-to-world-theme', theme) }, [theme])

  const refreshHistory = useCallback(async () => {
    try { setHistory(await listScenes()); setConnected(true) } catch { setConnected(false) }
  }, [])
  useEffect(() => { void refreshHistory() }, [refreshHistory])

  const acceptSceneDetail = useCallback((detail: SceneDetail) => {
    setScene(detail.version.sceneJson)
    setPrompt(detail.prompt)
    setActiveSceneId(detail.sceneId)
    setActiveVersionId(detail.version.versionId)
    setRuntimeError(null)
    setIntentPreview(detail.intentPreview ?? null)
    setCoverage(detail.coverage ?? null)
    setUnsupportedEntities(detail.unsupportedEntities ?? [])
    setSelectedNodeId(null)
  }, [])

  useEffect(() => {
    if (!activeJobId) return
    const controller = new AbortController()
    void streamGenerationEvents(activeJobId, (event) => {
      if (event.type === 'intent.ready' && event.data) setIntentPreview(event.data as IntentPreview)
      if ((event.type === 'draft.ready' || event.type === 'final.ready') && event.data) acceptSceneDetail(event.data as SceneDetail)
    }, controller.signal).catch(() => undefined)
    return () => controller.abort()
  }, [activeJobId, acceptSceneDetail])

  useEffect(() => {
    if (!activeJobId) return
    let disposed = false
    const poll = async () => {
      while (!disposed) {
        try {
          const next = await getGeneration(activeJobId)
          if (disposed) return
          setJob(next)
          setConnected(true)
          const progressive = next.status === 'succeeded' ? next.scene : next.draft ?? next.scene
          if (progressive && progressive.version.versionId !== activeVersionId) acceptSceneDetail(progressive)
          if (next.intentPreview) setIntentPreview(next.intentPreview)
          if (next.coverage) setCoverage(next.coverage)
          if (next.unsupportedEntities) setUnsupportedEntities(next.unsupportedEntities)
          if (['succeeded', 'partial', 'failed', 'cancelled'].includes(next.status)) {
            setActiveJobId(null)
            if (next.status === 'failed') setError(next.error?.message ?? '场景生成失败。')
            await refreshHistory()
            if (next.sceneId) setVersions(await listSceneVersions(next.sceneId))
            if (next.status === 'succeeded') window.setTimeout(() => setJob((current) => current?.jobId === next.jobId ? null : current), 3600)
            return
          }
        } catch (pollError) {
          if (!disposed) { setConnected(false); setError(messageFrom(pollError)); setActiveJobId(null) }
          return
        }
        await wait(650)
      }
    }
    void poll()
    return () => { disposed = true }
  }, [activeJobId, activeVersionId, acceptSceneDetail, refreshHistory])

  const startGeneration = async () => {
    setError(null); setInspectorOpen(false); setHistoryOpen(false); setVersions([])
    try {
      const created = await createGeneration(prompt.trim(), preferences)
      setJob(created); setActiveJobId(created.jobId); setConnected(true)
      setIntentPreview(created.intentPreview ?? created.request?.intentPreview ?? null)
      setCoverage(null); setUnsupportedEntities([]); setSelectedNodeId(null)
    } catch (submitError) { setConnected(false); setError(messageFrom(submitError)) }
  }

  const cancelActiveGeneration = async () => {
    if (!activeJobId) return
    try { await cancelGeneration(activeJobId) } catch (cancelError) { setError(messageFrom(cancelError)); setActiveJobId(null) }
  }

  const openScene = async (sceneId: string) => {
    setLoadingSceneId(sceneId); setError(null)
    try {
      const detail = await getScene(sceneId)
      acceptSceneDetail(detail)
      setVersions(await listSceneVersions(sceneId))
      setHistoryOpen(false); setConnected(true); setResetRequest((value) => value + 1)
    } catch (loadError) { setError(messageFrom(loadError)) } finally { setLoadingSceneId(null) }
  }

  const openInspector = async () => {
    setHistoryOpen(false); setInspectorOpen(true)
    if (activeSceneId) {
      try { setVersions(await listSceneVersions(activeSceneId)) } catch { setVersions([]) }
    }
  }

  const runCommand = async (type: SceneCommandType, parameters: Record<string, unknown>) => {
    if (!activeSceneId || !activeVersionId) return
    setCommandBusy(true); setError(null)
    try {
      const detail = await applySceneCommand(activeSceneId, activeVersionId, type, parameters)
      acceptSceneDetail(detail)
      setVersions(await listSceneVersions(activeSceneId))
      await refreshHistory()
      setResetRequest((value) => value + 1)
    } catch (commandError) { setError(messageFrom(commandError)) } finally { setCommandBusy(false) }
  }

  const restoreVersion = async (versionId: string) => {
    if (!activeSceneId) return
    setCommandBusy(true); setError(null)
    try {
      const detail = await restoreSceneVersion(activeSceneId, versionId)
      acceptSceneDetail(detail)
      setVersions(await listSceneVersions(activeSceneId))
      await refreshHistory()
      setResetRequest((value) => value + 1)
    } catch (restoreError) { setError(messageFrom(restoreError)) } finally { setCommandBusy(false) }
  }

  const copyScene = async () => { await navigator.clipboard.writeText(JSON.stringify(scene, null, 2)); setCopied(true); window.setTimeout(() => setCopied(false), 1800) }

  return <main className={`app-shell${locked ? ' is-exploring' : ''}`}>
    <div className="world-layer" aria-label={`当前 3D 场景：${scene.title}`}><RuntimeBoundary key={scene.id}><Suspense fallback={<div className="canvas-fallback">正在载入 3D 运行时...</div>}><WorldCanvas scene={scene} resetRequest={resetRequest} onLockedChange={setLocked} onRuntimeError={setRuntimeError} onNodeSelect={(nodeId) => { if (!locked) { setSelectedNodeId(nodeId); setHistoryOpen(false); setInspectorOpen(true) } }} /></Suspense></RuntimeBoundary></div>
    <TopBar connected={connected} theme={theme} onToggleTheme={() => setTheme((value) => value === 'dark' ? 'light' : 'dark')} onOpenHistory={() => { setInspectorOpen(false); setHistoryOpen(true) }} onOpenInspector={() => void openInspector()} onResetCamera={() => setResetRequest((value) => value + 1)} />
    <GenerationStatus job={job} error={error} onDismissError={() => setError(null)} />
    <IntentSummary intent={intentPreview} coverage={coverage} unsupported={unsupportedEntities} active={isGenerating} />
    <PromptComposer value={prompt} isGenerating={isGenerating} preferences={preferences} onChange={setPrompt} onPreferencesChange={setPreferences} onSubmit={startGeneration} onCancel={cancelActiveGeneration} />

    <aside className="scene-readout chrome-layer" aria-label="当前场景信息">
      <span className="scene-version" data-kind={versionKind}>{versionKind === 'draft' ? '可探索草稿' : '完成版本'}</span>
      <span className="scene-title">{scene.title}</span>
      <span className="scene-metrics">{styleName} / {stats.nodes} 节点 / {stats.lights} 灯光 / {stats.signs} 招牌</span>
      <button id="enter-world" className="enter-world-button" type="button" onClick={() => { if (orbitMode) setResetRequest((value) => value + 1) }}><CornersOut size={18} /><span>{orbitMode ? '重置视角' : '进入场景'}</span></button>
    </aside>

    {runtimeError ? <div className="runtime-warning chrome-layer" role="alert"><Warning size={18} weight="fill" /><span>{runtimeError}</span></div> : null}
    <div className="explore-hud" aria-hidden={!locked}><span>{scene.title}</span><div><kbd>W</kbd><kbd>A</kbd><kbd>S</kbd><kbd>D</kbd><small>移动</small><kbd>Shift</kbd><small>加速</small><kbd>Esc</kbd><small>退出</small></div></div>
    <HistoryDrawer open={historyOpen} scenes={history} loadingSceneId={loadingSceneId} onClose={() => setHistoryOpen(false)} onSelect={openScene} />
    <SceneInspector open={inspectorOpen} scene={scene} copied={copied} busy={commandBusy} versions={versions} currentVersionId={activeVersionId} selectedNodeId={selectedNodeId} onCopy={copyScene} onClose={() => setInspectorOpen(false)} onCommand={runCommand} onRestore={restoreVersion} />
  </main>
}
