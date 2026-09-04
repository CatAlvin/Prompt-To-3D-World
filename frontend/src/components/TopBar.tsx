import {
  ArrowCounterClockwise,
  ClockCounterClockwise,
  MagicWand,
  Cube,
  Moon,
  Sun,
} from '@phosphor-icons/react'

interface TopBarProps {
  connected: boolean | null
  theme: 'light' | 'dark'
  onToggleTheme: () => void
  onOpenHistory: () => void
  onOpenInspector: () => void
  onResetCamera: () => void
}

export function TopBar({
  connected,
  theme,
  onToggleTheme,
  onOpenHistory,
  onOpenInspector,
  onResetCamera,
}: TopBarProps) {
  return (
    <header className="top-bar chrome-layer" aria-label="应用工具栏">
      <div className="brand-lockup" aria-label="Prompt to World">
        <span className="brand-mark" aria-hidden="true">
          <Cube size={20} weight="duotone" />
        </span>
        <span>
          <strong>PROMPT</strong>
          <span>TO WORLD</span>
        </span>
      </div>

      <div className="service-state" data-connected={connected === true}>
        {connected === null ? '正在连接生成服务' : connected ? '生成服务已连接' : '生成服务离线'}
      </div>

      <nav className="top-actions" aria-label="场景工具">
        <button className="icon-button" type="button" onClick={onResetCamera} title="重置视角">
          <ArrowCounterClockwise size={19} />
          <span className="sr-only">重置视角</span>
        </button>
        <button className="icon-button" type="button" onClick={onOpenInspector} title="场景工作台">
          <MagicWand size={19} />
          <span className="sr-only">场景工作台</span>
        </button>
        <button
          className="toolbar-button"
          type="button"
          onClick={onOpenHistory}
          aria-label="历史"
          title="历史"
        >
          <ClockCounterClockwise size={18} />
          <span>历史</span>
        </button>
        <button className="icon-button" type="button" onClick={onToggleTheme} title="切换界面主题">
          {theme === 'dark' ? <Sun size={19} /> : <Moon size={19} />}
          <span className="sr-only">切换界面主题</span>
        </button>
      </nav>
    </header>
  )
}
