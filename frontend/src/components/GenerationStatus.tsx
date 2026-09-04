import { Check, Warning, X } from '@phosphor-icons/react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { useEffect, useState } from 'react'
import type { GenerationJob, GenerationStatus as Status } from '@/api/client'

const STATUS_COPY: Record<Status, string> = {
  queued: '生成任务已进入队列', generating: '正在组合场景', validating: '正在核对描述与画面', enhancing: '草稿可探索，正在完成视觉增强', partial: '最终版本未通过，已保留可探索草稿', succeeded: '世界已完成并通过相关性核对', failed: '这次没有生成成功', cancelled: '生成已取消',
}
const STAGES = [['interpreting', '理解描述'], ['resolving', '匹配能力'], ['composing_draft', '构建草稿'], ['enhancing', '视觉增强'], ['checking_fidelity', '核对画面'], ['completed', '完成']] as const

interface GenerationStatusProps { job: GenerationJob | null; error: string | null; onDismissError: () => void }

export function GenerationStatus({ job, error, onDismissError }: GenerationStatusProps) {
  const reduceMotion = useReducedMotion()
  const active = Boolean(job && ['queued', 'generating', 'validating', 'enhancing'].includes(job.status))
  const jobError = job && ['failed', 'partial'].includes(job.status) ? job.error?.message : null
  const message = error ?? jobError ?? (job ? STATUS_COPY[job.status] : null)
  const isError = Boolean(error || job?.status === 'failed' || job?.status === 'partial')
  const [clock, setClock] = useState(() => Date.now())
  useEffect(() => { if (!active) return; const timer = window.setInterval(() => setClock(Date.now()), 1000); return () => window.clearInterval(timer) }, [active])
  const elapsedSeconds = active && job ? Math.max(0, Math.floor((clock - new Date(job.createdAt).getTime()) / 1000)) : 0
  const elapsedLabel = `${String(Math.floor(elapsedSeconds / 60)).padStart(2, '0')}:${String(elapsedSeconds % 60).padStart(2, '0')}`

  return <AnimatePresence>{message ? (
    <motion.aside className={`generation-status chrome-layer${isError ? ' is-error' : ''}`} initial={reduceMotion ? false : { opacity: 0, x: -14 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -10 }} transition={{ duration: 0.32, ease: [0.16, 1, 0.3, 1] }} role={isError ? 'alert' : 'status'} aria-live="polite">
      <span className="status-icon" aria-hidden="true">{isError ? <Warning size={18} weight="fill" /> : active ? <span className="status-wave" /> : <Check size={18} />}</span>
      <span className="status-content"><strong>{message}</strong>{active ? <small>已用时 {elapsedLabel}，草稿完成后即可进入场景</small> : null}
        {job?.stages?.length ? <span className="stage-track" aria-label="生成阶段">{STAGES.map(([key, label]) => { const stage = job.stages?.find((item) => item.stage === key); return <span key={key} data-state={stage?.status ?? 'waiting'}>{label}</span> })}</span> : null}
      </span>
      {isError ? <button type="button" onClick={onDismissError} title="关闭提示"><X size={17} /><span className="sr-only">关闭提示</span></button> : null}
    </motion.aside>
  ) : null}</AnimatePresence>
}
