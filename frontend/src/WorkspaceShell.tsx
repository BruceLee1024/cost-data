import { FormEvent, ReactNode, useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { BarChart3, Bell, Box, ChevronDown, CircleCheck, Database, Download, FolderKanban, GitCompareArrows, Home, Layers3, Menu, Moon, Search, Settings, ShieldCheck, SlidersHorizontal, Sun, TriangleAlert, Wrench, X } from 'lucide-react'
import type { View } from './App'
import { isStaticDemo, request } from './api'

const navigation = [
  ['overview', '工作台', Home], ['projects', '项目管理', FolderKanban],
  ['explorer', '数据查询', Search], ['analysis', '造价分析', BarChart3],
  ['catalog', '清单库', Layers3], ['quota', '定额库', Database],
  ['resource', '材料库', Box],
] as const
const tools = [['matching', '清单匹配', GitCompareArrows], ['quality', '数据质量中心', ShieldCheck], ['rules', '标准化规则', SlidersHorizontal]] as const

export function WorkspaceShell({ view, go, search, ready, children }: { view: View; go: (view: View) => void; search: (value: string) => void; ready: boolean; children: ReactNode }) {
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem('cost-data-sidebar-collapsed') === 'true')
  const [width, setWidth] = useState(() => { const saved = Number(localStorage.getItem('cost-data-sidebar-width-v2')); return saved >= 200 && saved <= 320 ? saved : 228 })
  const [resizing, setResizing] = useState(false)
  const [toolsOpen, setToolsOpen] = useState(false)
  const [notifications, setNotifications] = useState(false)
  const [dark, setDark] = useState(() => localStorage.getItem('cost-data-theme') === 'dark')
  const [query, setQuery] = useState('')
  const searchRef = useRef<HTMLInputElement>(null)
  const stats = useQuery({ queryKey: ['dashboard'], queryFn: () => request<Record<string, number>>('/dashboard'), enabled: ready })
  useEffect(() => { localStorage.setItem('cost-data-sidebar-collapsed', String(collapsed)) }, [collapsed])
  useEffect(() => { localStorage.setItem('cost-data-theme', dark ? 'dark' : 'light'); document.documentElement.dataset.theme = dark ? 'dark' : 'light' }, [dark])
  useEffect(() => {
    const keydown = (event: KeyboardEvent) => { if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); searchRef.current?.focus() } if (event.key === 'Escape') setNotifications(false) }
    window.addEventListener('keydown', keydown); return () => window.removeEventListener('keydown', keydown)
  }, [])
  useEffect(() => {
    if (!resizing) return
    const move = (event: PointerEvent) => setWidth(Math.min(320, Math.max(200, event.clientX)))
    const stop = () => setResizing(false)
    const oldCursor = document.body.style.cursor, oldSelect = document.body.style.userSelect
    document.body.style.cursor = 'col-resize'; document.body.style.userSelect = 'none'
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', stop)
    return () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', stop); document.body.style.cursor = oldCursor; document.body.style.userSelect = oldSelect }
  }, [resizing])
  useEffect(() => { if (!resizing) localStorage.setItem('cost-data-sidebar-width-v2', String(width)) }, [width, resizing])
  const submit = (event: FormEvent) => { event.preventDefault(); search(query.trim()) }
  return <div className={`shell workspace-shell ${collapsed ? 'sidebar-collapsed' : ''}`} style={{ gridTemplateColumns: collapsed ? '72px minmax(0,1fr)' : `${width}px minmax(0,1fr)` }}>
    <aside className="workspace-sidebar">
      <button className="brand" onClick={() => go('overview')} aria-label="返回工作台"><img src={`${import.meta.env.BASE_URL}images/brand.webp`} alt="" /><div><strong>工程造价数据库</strong><small>我的工程数据工作台</small></div></button>
      <nav aria-label="主导航">
        {navigation.map(([id, label, Icon]) => <button key={id} className={view === id ? 'active' : ''} aria-current={view === id ? 'page' : undefined} aria-label={label} title={collapsed ? label : undefined} onClick={() => go(id)}><Icon /><span>{label}</span></button>)}
        <button className={tools.some(([id]) => id === view) ? 'active' : ''} aria-label="我的工具" aria-expanded={toolsOpen} onClick={() => setToolsOpen(!toolsOpen)}><Wrench /><span>我的工具</span><ChevronDown className={`nav-chevron ${toolsOpen ? 'open' : ''}`} /></button>
        {toolsOpen && <div className="workspace-subnav">{tools.map(([id, label, Icon]) => <button key={id} className={view === id ? 'active' : ''} title={collapsed ? label : undefined} onClick={() => go(id)}><Icon /><span>{label}</span></button>)}</div>}
        <button aria-label="数据导入" className={view === 'imports' ? 'active' : ''} onClick={() => go('imports')}><Download /><span>数据导入</span></button>
        <button aria-label="设置" className={view === 'settings' ? 'active' : ''} onClick={() => go('settings')}><Settings /><span>设置</span></button>
      </nav>
      <button className="workspace-profile" onClick={() => go('settings')} title="设置与本地服务状态"><img src={`${import.meta.env.BASE_URL}images/bruce.webp`} alt="Bruce 的头像" /><span><strong>Bruce</strong><small>{isStaticDemo ? '静态预览' : '个人版'}</small></span><ChevronDown /></button>
      <div className="sidebar-resize-handle" role="separator" aria-label="调整导航栏宽度" onPointerDown={() => setResizing(true)} onDoubleClick={() => setWidth(228)} />
    </aside>
    <main>
      <header className="workspace-topbar">
        <button className="workspace-collapse" title={collapsed ? '展开导航栏' : '收起导航栏'} aria-label={collapsed ? '展开导航栏' : '收起导航栏'} onClick={() => setCollapsed(!collapsed)}><Menu /></button>
        <form className="workspace-search" onSubmit={submit}><Search /><input ref={searchRef} aria-label="全局搜索" placeholder="搜索项目、清单、材料、定额..." value={query} onChange={event => setQuery(event.target.value)} /><kbd>⌘ K</kbd></form>
        <div className="workspace-topbar-actions"><div className="notification-wrap"><button className="workspace-icon-button notification-button" aria-label="通知" aria-expanded={notifications} onClick={() => setNotifications(!notifications)}><Bell />{(stats.data?.open_issues || !ready) ? <i /> : null}</button>{notifications && <div className="workspace-notifications"><div><strong>通知中心</strong><button className="workspace-icon-button" aria-label="关闭通知" onClick={() => setNotifications(false)}><X /></button></div><p>{ready ? <CircleCheck /> : <TriangleAlert />}{isStaticDemo ? '当前为静态预览' : ready ? '本地服务运行正常' : '正在连接本地服务'}</p><button onClick={() => { go('quality'); setNotifications(false) }}><ShieldCheck /><span>{stats.data?.open_issues ? `${stats.data.open_issues} 个数据问题待复核` : '暂无待处理的数据异常'}<small>前往数据质量中心</small></span></button></div>}</div><span className="topbar-divider" /><button className="workspace-icon-button" aria-label={dark ? '切换浅色主题' : '切换深色主题'} onClick={() => setDark(!dark)}>{dark ? <Moon /> : <Sun />}</button></div>
      </header>
      {children}
    </main>
  </div>
}
