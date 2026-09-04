import { CheckCircle, Eye, Info, WarningCircle } from '@phosphor-icons/react'
import type { FidelityReport, IntentPreview, UnsupportedEntity } from '@/api/client'

const MODE_LABELS: Record<IntentPreview['sceneMode'], string> = {
  walkable: '步行探索',
  interior: '室内空间',
  orbital: '轨道观察',
  flythrough: '飞越浏览',
  diorama: '微缩展示',
  panorama: '全景氛围',
}

interface IntentSummaryProps {
  intent: IntentPreview | null
  coverage: FidelityReport | null
  unsupported: UnsupportedEntity[]
  active: boolean
}

export function IntentSummary({ intent, coverage, unsupported, active }: IntentSummaryProps) {
  if (!intent) return null
  const exactCount = intent.entities.filter((entity) => entity.support === 'exact').length
  const abstractCount = intent.entities.filter((entity) => entity.support === 'abstract').length
  const coveragePercent = coverage ? Math.round(coverage.requiredCoverage * 100) : null
  const requiredCount = coverage ? coverage.coveredEntityIds.length + coverage.missingEntityIds.length : null

  return (
    <aside className="intent-summary chrome-layer" aria-live="polite">
      <header>
        <span className="intent-kicker"><Eye size={15} />我理解为</span>
        <span className="intent-mode">{MODE_LABELS[intent.sceneMode]}</span>
      </header>
      <strong>{intent.title}</strong>
      <div className="intent-chips" aria-label="识别到的关键内容">
        {intent.entities.slice(0, 6).map((entity) => (
          <span key={entity.id} data-support={entity.support}>
            {entity.label}
          </span>
        ))}
        {intent.entities.length > 6 ? <span>+{intent.entities.length - 6}</span> : null}
      </div>
      <div className="intent-health">
        {coverage?.status === 'passed' ? (
          <span data-tone="success"><CheckCircle size={16} weight="fill" />已表现 {coverage.coveredEntityIds.length}/{requiredCount} 个关键内容</span>
        ) : active ? (
          <span><Info size={16} />正在核对描述与画面</span>
        ) : coverage && coveragePercent !== null ? (
          <span data-tone="warning"><WarningCircle size={16} weight="fill" />内容 {coveragePercent}% · 关系 {Math.round(coverage.relationSatisfaction * 100)}% · 禁止项 {coverage.forbiddenViolations}</span>
        ) : (
          <span><Info size={16} />已识别 {intent.entities.length} 个场景要素</span>
        )}
      </div>
      {unsupported.length ? (
        <details>
          <summary>{abstractCount || unsupported.length} 项将使用抽象表现</summary>
          <div>
            {unsupported.map((item) => <p key={item.entityId}>{item.message ?? item.concept}</p>)}
          </div>
        </details>
      ) : exactCount ? (
        <small>{exactCount} 项可由当前引擎直接表现</small>
      ) : null}
    </aside>
  )
}
