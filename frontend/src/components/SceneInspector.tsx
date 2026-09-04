import { ArrowCounterClockwise, Check, Code, Copy, MagicWand, X } from '@phosphor-icons/react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { useState } from 'react'
import type { SceneCommandType, SceneDetail } from '@/api/client'
import type { SceneDocument } from '@/types/scene'
import { isSceneV3 } from '@/types/scene'

interface SceneInspectorProps {
  open: boolean
  scene: SceneDocument
  copied: boolean
  busy: boolean
  versions: SceneDetail[]
  currentVersionId: string | null
  selectedNodeId: string | null
  onCopy: () => void
  onClose: () => void
  onCommand: (type: SceneCommandType, parameters: Record<string, unknown>) => void
  onRestore: (versionId: string) => void
}

export function SceneInspector({ open, scene, copied, busy, versions, currentVersionId, selectedNodeId, onCopy, onClose, onCommand, onRestore }: SceneInspectorProps) {
  const reduceMotion = useReducedMotion()
  const [tab, setTab] = useState<'refine' | 'versions' | 'json'>('refine')
  const [density, setDensity] = useState(0.68)
  const [semantic, setSemantic] = useState('')
  const supportsCommands = isSceneV3(scene) && Boolean(currentVersionId)
  const selectedNode = selectedNodeId ? scene.nodes.find((node) => node.id === selectedNodeId) : null
  const selectedProvenance = selectedNode && 'provenance' in selectedNode ? selectedNode.provenance : null

  return <AnimatePresence>{open ? <>
    <motion.button className="drawer-scrim" type="button" aria-label="关闭场景检查器" onClick={onClose} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />
    <motion.aside className="side-drawer inspector-drawer" aria-label="场景检查器" initial={reduceMotion ? false : { x: '100%' }} animate={{ x: 0 }} exit={{ x: '100%' }} transition={{ duration: 0.42, ease: [0.16, 1, 0.3, 1] }}>
      <header><div><h2>场景工作台</h2><p>所有调整都会创建一个新的不可变版本。</p></div><button className="icon-button" type="button" onClick={onClose} title="关闭"><X size={19} /></button></header>
      <div className="inspector-tabs" role="tablist">
        <button type="button" role="tab" aria-selected={tab === 'refine'} onClick={() => setTab('refine')}><MagicWand size={16} />调整</button>
        <button type="button" role="tab" aria-selected={tab === 'versions'} onClick={() => setTab('versions')}><ArrowCounterClockwise size={16} />版本</button>
        <button type="button" role="tab" aria-selected={tab === 'json'} onClick={() => setTab('json')}><Code size={16} />数据</button>
      </div>

      {tab === 'refine' ? <div className="refine-content drawer-content">
        {!supportsCommands ? <div className="inspector-notice">旧版场景可以继续探索。创建 V3 场景后可使用可追溯的局部调整。</div> : <>
          {selectedNode && selectedProvenance ? <section className="provenance-card">
            <div><h3>为什么会出现</h3><span>{selectedNode.semantics.category}</span></div>
            <p>{selectedProvenance.reason}</p>
            <dl>
              <div><dt>来源</dt><dd>{selectedProvenance.origin === 'prompt' ? '你的描述' : '场景结构'}</dd></div>
              <div><dt>表现能力</dt><dd>{selectedProvenance.capabilityId}</dd></div>
              <div><dt>匹配度</dt><dd>{Math.round(selectedProvenance.confidence * 100)}%</dd></div>
            </dl>
            {selectedProvenance.userRemovable && selectedProvenance.entityId ? <button className="command-danger" disabled={busy} type="button" onClick={() => onCommand('remove_entity', { entityId: selectedProvenance.entityId })}>移除此内容</button> : null}
          </section> : null}
          <section><h3>探索方式</h3><p>切换相机与空间规则，不改变已经识别的实体。</p>
            <select disabled={busy} value={scene.pipeline.sceneMode} onChange={(event) => onCommand('change_scene_mode', { sceneMode: event.target.value })}>
              <option value="walkable">步行探索</option>
              <option value="interior">室内空间</option>
              <option value="orbital">轨道观察</option>
              <option value="flythrough">飞越浏览</option>
              <option value="diorama">微缩展示</option>
              <option value="panorama">全景氛围</option>
            </select>
          </section>
          <section><h3>环境</h3><p>修改天气与光照，不改变空间布局。</p><div className="command-grid">
            <button disabled={busy} type="button" onClick={() => onCommand('set_environment', { weather: 'rain', exposure: 1.04, fogDensity: 0.018 })}>雨夜</button>
            <button disabled={busy} type="button" onClick={() => onCommand('set_environment', { weather: 'mist', exposure: 0.92, fogDensity: 0.046 })}>浓雾</button>
            <button disabled={busy} type="button" onClick={() => onCommand('set_environment', { weather: 'clear', exposure: 1.18, fogDensity: 0.004 })}>清朗</button>
          </div></section>
          <section><h3>保留布局换风格</h3><select disabled={busy} defaultValue={scene.pipeline.styleKit} onChange={(event) => onCommand('set_style_kit', { styleKit: event.target.value })}>
            <option value="cyberpunk_tokyo_v1">东京霓雨</option><option value="cozy_lowpoly_v1">暖木低模</option><option value="misty_nature_v1">雾林石径</option><option value="lunar_research_v1">轨道晨光</option>
          </select></section>
          <section><h3>细节密度</h3><div className="command-range"><input type="range" min="0.2" max="1" step="0.05" value={density} onChange={(event) => setDensity(Number(event.target.value))} /><span>{Math.round(density * 100)}</span></div><button className="command-primary" disabled={busy} type="button" onClick={() => onCommand('set_density', { density })}>应用密度</button></section>
          <section><h3>移除语义对象</h3><div className="semantic-command"><input value={semantic} onChange={(event) => setSemantic(event.target.value)} placeholder="例如 sign、rock、lantern" /><button disabled={busy || !semantic.trim()} type="button" onClick={() => onCommand('remove_by_semantics', { semantic: semantic.trim() })}>移除</button></div></section>
        </>}
      </div> : null}

      {tab === 'versions' ? <div className="version-list drawer-content">{versions.length ? versions.map((item) => <article key={item.version.versionId} data-current={item.version.versionId === currentVersionId}>
        <div><strong>版本 {item.version.versionNumber}</strong><span>{item.version.versionKind === 'draft' ? '草稿' : '完成'}</span></div><p>{item.version.changeSummary ?? '场景版本'}</p><small>{new Date(item.version.createdAt).toLocaleString('zh-CN')}</small>{item.version.versionId !== currentVersionId ? <button disabled={busy} type="button" onClick={() => onRestore(item.version.versionId)}>恢复为新版本</button> : <em>当前版本</em>}
      </article>) : <div className="inspector-notice">打开一个已保存场景后会显示版本时间线。</div>}</div> : null}

      {tab === 'json' ? <><div className="inspector-actions"><span>Schema {scene.schemaVersion}</span><button type="button" onClick={onCopy}>{copied ? <Check size={16} /> : <Copy size={16} />}{copied ? '已复制' : '复制 JSON'}</button></div><pre className="json-viewer"><code>{JSON.stringify(scene, null, 2)}</code></pre></> : null}
    </motion.aside>
  </> : null}</AnimatePresence>
}
