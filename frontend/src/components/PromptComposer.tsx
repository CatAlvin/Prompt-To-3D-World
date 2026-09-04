import { ArrowRight, CaretDown, SlidersHorizontal, Sparkle, Stop } from '@phosphor-icons/react'
import { motion, useReducedMotion } from 'motion/react'
import { useState, type FormEvent } from 'react'
import type { GenerationPreferences } from '@/api/client'

const EXAMPLES = [
  '雨夜的赛博朋克日本小巷，两侧是拉面店和霓虹招牌。',
  'A quiet lunar research station above a blue crater at sunrise.',
  '漂浮在云海中的古老庭院，有石桥、竹林和暖色灯笼。',
]

interface PromptComposerProps {
  value: string
  isGenerating: boolean
  preferences: GenerationPreferences
  onChange: (value: string) => void
  onPreferencesChange: (preferences: GenerationPreferences) => void
  onSubmit: () => void
  onCancel: () => void
}

export function PromptComposer({ value, isGenerating, preferences, onChange, onPreferencesChange, onSubmit, onCancel }: PromptComposerProps) {
  const reduceMotion = useReducedMotion()
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (!isGenerating && value.trim().length >= 3) onSubmit()
  }

  return (
    <motion.section className="prompt-composer chrome-layer" initial={reduceMotion ? false : { opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.55, ease: [0.16, 1, 0.3, 1] }} aria-label="场景生成器">
      <form onSubmit={submit}>
        <div className="composer-heading">
          <div><span className="composer-kicker">描述一个地方</span><h1>一句话，走进新世界。</h1></div>
          <span className="prompt-count" aria-label={`已输入 ${value.length} 个字符`}>{value.length}/2000</span>
        </div>

        <label htmlFor="scene-prompt">场景描述</label>
        <textarea id="scene-prompt" value={value} maxLength={2000} rows={3} disabled={isGenerating} onChange={(event) => onChange(event.target.value)} placeholder="例如：夜晚的赛博朋克日本小巷，拉面店沿街亮着霓虹灯。" aria-describedby="prompt-help" />
        <p id="prompt-help" className="helper-text">先生成可探索草稿，再在后台完成材质、资产与灯光增强。</p>

        <div className="generation-presets" aria-label="生成偏好">
          <label><span>视觉风格</span><select value={preferences.styleKit} disabled={isGenerating} onChange={(event) => onPreferencesChange({ ...preferences, styleKit: event.target.value as GenerationPreferences['styleKit'] })}>
            <option value="auto">自动匹配</option><option value="cyberpunk_tokyo_v1">东京霓雨</option><option value="cozy_lowpoly_v1">暖木低模</option><option value="misty_nature_v1">雾林石径</option><option value="lunar_research_v1">轨道晨光</option>
          </select></label>
          <label><span>完成质量</span><select value={preferences.quality} disabled={isGenerating} onChange={(event) => onPreferencesChange({ ...preferences, quality: event.target.value as GenerationPreferences['quality'] })}>
            <option value="draft">快速草稿</option><option value="balanced">平衡</option><option value="quality">高质量</option>
          </select></label>
        </div>

        <button className="advanced-toggle" type="button" aria-expanded={advancedOpen} onClick={() => setAdvancedOpen((value) => !value)}>
          <SlidersHorizontal size={16} /><span>更多控制</span><CaretDown className={advancedOpen ? 'is-open' : ''} size={15} />
        </button>

        {advancedOpen ? (
          <div className="advanced-controls">
            <label><span>时间</span><select value={preferences.time} onChange={(event) => onPreferencesChange({ ...preferences, time: event.target.value as GenerationPreferences['time'] })}>
              <option value="auto">自动</option><option value="day">白天</option><option value="sunrise">日出</option><option value="sunset">日落</option><option value="night">夜晚</option><option value="indoor">室内</option>
            </select></label>
            <label><span>天气</span><select value={preferences.weather} onChange={(event) => onPreferencesChange({ ...preferences, weather: event.target.value as GenerationPreferences['weather'] })}>
              <option value="auto">自动</option><option value="clear">晴朗</option><option value="rain">雨</option><option value="mist">雾</option><option value="dust">尘沙</option>
            </select></label>
            <label className="density-control"><span>细节密度 <b>{Math.round(preferences.density * 100)}</b></span><input type="range" min="0.2" max="1" step="0.05" value={preferences.density} onChange={(event) => onPreferencesChange({ ...preferences, density: Number(event.target.value) })} /></label>
          </div>
        ) : null}

        <div className="example-prompts" aria-label="示例描述">
          {EXAMPLES.map((example, index) => <button key={example} type="button" onClick={() => onChange(example)} disabled={isGenerating} title={example}>{index === 0 ? '霓雨小巷' : index === 1 ? '月面站点' : '云中古庭'}</button>)}
        </div>

        {isGenerating ? (
          <button className="generate-button cancel" type="button" onClick={onCancel}><Stop size={18} weight="fill" /><span>停止增强并保留草稿</span></button>
        ) : (
          <button className="generate-button" type="submit" disabled={value.trim().length < 3}><Sparkle size={19} weight="fill" /><span>生成世界</span><ArrowRight className="button-arrow" size={19} /></button>
        )}
      </form>
    </motion.section>
  )
}
