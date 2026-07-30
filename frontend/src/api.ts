export type DecimalValue = { value: string | null; scale: number; unit?: string; currency?: string }
export type Project = { id: string; name: string; region: string; pricing_date: string; specialty: string; pricing_mode: string; result_stage: string; project_type?: string; area: DecimalValue; latest_version_id?: string; latest_version_no?: number; latest_status?: string; item_count: number; issue_count: number }
export type ImportJob = { id: string; project_id: string; project_version_id: string; status: string; progress: number; total_files: number; processed_files: number; open_issue_count: number; error_summary?: string; created_at: string }
export type ImportIssue = { id: string; import_job_id: string; severity: string; code: string; message: string; sheet_name?: string; cell_range?: string; suggested_action?: string; status: string }
export type ImportParsePreview = { tables: Array<{ source_file_id: string; sheet_name: string; report_type: string; header_rows: number[]; columns: Record<string, { column: number; header_path: string[] }>; raw_columns?: Record<string, string[]>; requires_confirmation: boolean }> }
export type CostItem = { id: string; project_name: string; item_type: string; code?: string; name: string; description?: string; specification?: string; unit?: string; quantity: DecimalValue; unit_price: DecimalValue; total: DecimalValue; region: string; pricing_date: string; specialty: string; pricing_mode: string; import_attributes: Record<string, string>; source: { file_name: string; sheet_name: string; start_row: number; field_cells?: Record<string, string> }; components: Array<{ id: string; category: string; name: string; amount: DecimalValue }> }
export type SearchResult = { items: CostItem[]; total: number; next_cursor?: string }
export type Rule = { id: string; rule_type: string; source_value: string; target_value: string; enabled: boolean; source: string }
export type Backup = { id: string; path: string; kind: string; created_at: string; database_sha256: string; file_count: number; status: string }

let token = typeof sessionStorage === 'undefined' ? '' : sessionStorage.getItem('cost-data-token') || ''
export const isStaticDemo = import.meta.env.VITE_STATIC_DEMO === 'true'

function staticDemoResponse(path: string): unknown {
  if (path === '/health') return { status: 'ok', version: '0.1.0', session_token: '' }
  if (path === '/dashboard') return { projects: 0, published_versions: 0, cost_items: 0, open_issues: 0 }
  if (path === '/settings/ai') return { base_url: 'https://api.deepseek.com', model: 'deepseek-chat', has_api_key: false }
  if (path.startsWith('/cost-items/search')) return { items: [], total: 0 }
  if (path.startsWith('/match-sessions')) return { results: [{ candidates: [] }] }
  if (path.endsWith('/parse-preview')) return { tables: [] }
  if (path === '/projects' || path === '/imports' || path === '/normalization-rules' || path === '/backups' || path.endsWith('/issues')) return []
  return {}
}

export async function request<T = unknown>(path: string, init: RequestInit = {}): Promise<T> {
  if (isStaticDemo) return staticDemoResponse(path) as T
  const headers = new Headers(init.headers)
  if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  if (token) headers.set('X-Cost-Data-Token', token)
  const response = await fetch(`/api/v1${path}`, { ...init, headers })
  const body = response.headers.get('content-type')?.includes('json') ? await response.json() : null
  if (!response.ok) throw new Error(body?.error?.message || body?.detail || `请求失败 (${response.status})`)
  return body as T
}

export async function bootstrap() {
  const health = await request<{ session_token: string }>('/health')
  token = health.session_token
  if (typeof sessionStorage !== 'undefined') sessionStorage.setItem('cost-data-token', token)
  return health
}

export function formatAmount(value?: DecimalValue) {
  if (!value?.value) return '—'
  return new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 4 }).format(Number(value.value))
}
