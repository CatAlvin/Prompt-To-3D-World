import { ArrowRight, ClockCounterClockwise, X } from '@phosphor-icons/react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import type { SceneSummary } from '@/api/client'

interface HistoryDrawerProps {
  open: boolean
  scenes: SceneSummary[]
  loadingSceneId: string | null
  onClose: () => void
  onSelect: (sceneId: string) => void
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat('zh-CN', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

export function HistoryDrawer({
  open,
  scenes,
  loadingSceneId,
  onClose,
  onSelect,
}: HistoryDrawerProps) {
  const reduceMotion = useReducedMotion()
  return (
    <AnimatePresence>
      {open ? (
        <>
          <motion.button
            className="drawer-scrim"
            type="button"
            aria-label="关闭历史记录"
            onClick={onClose}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          />
          <motion.aside
            className="side-drawer"
            aria-label="生成历史"
            initial={reduceMotion ? false : { x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ duration: 0.42, ease: [0.16, 1, 0.3, 1] }}
          >
            <header>
              <span className="drawer-title-icon" aria-hidden="true">
                <ClockCounterClockwise size={21} />
              </span>
              <div>
                <h2>生成历史</h2>
                <p>场景版本会保持不变，可以随时重新进入。</p>
              </div>
              <button className="icon-button" type="button" onClick={onClose} title="关闭">
                <X size={19} />
              </button>
            </header>

            <div className="drawer-content">
              {scenes.length === 0 ? (
                <div className="empty-history">
                  <ClockCounterClockwise size={30} weight="thin" />
                  <h3>还没有生成记录</h3>
                  <p>完成第一个世界后，它会保存在这里。</p>
                </div>
              ) : (
                <div className="history-list">
                  {scenes.map((scene) => (
                    <button
                      type="button"
                      key={scene.sceneId}
                      onClick={() => onSelect(scene.sceneId)}
                      disabled={loadingSceneId === scene.sceneId}
                    >
                      <span
                        className="history-thumbnail"
                        aria-hidden="true"
                        style={{
                          background: `linear-gradient(145deg, ${scene.thumbnail?.background ?? '#11121a'}, ${scene.thumbnail?.accent ?? '#c92f63'})`,
                        }}
                      />
                      <span className="history-date">{formatDate(scene.createdAt)}</span>
                      <strong>{scene.title}</strong>
                      <span className="history-prompt">{scene.prompt}</span>
                      <span className="history-meta">
                        <b>{scene.versionKind === 'draft' ? '草稿' : '完成'}</b>
                        {scene.nodeCount} 节点
                        <ArrowRight size={16} />
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </motion.aside>
        </>
      ) : null}
    </AnimatePresence>
  )
}
