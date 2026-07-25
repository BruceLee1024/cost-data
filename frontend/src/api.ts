export type DecimalValue = { value: string | null; scale: number; unit?: string; currency?: string }
export type Project = { id: string; name: string; region: string; pricing_date: string; specialty: string; pricing_mode: string; result_stage: string; project_type?: string; area: DecimalValue; latest_version_id?: string; latest_version_no?: number; latest_status?: string; item_count: number; issue_count: number }
export type ImportJob = { id: string; project_id: string; project_version_id: string; status: string; progress: number; total_files: number; processed_files: number; open_issue_count: number; error_summary?: string; created_at: string }
export type ImportIssue = { id: string; import_job_id: string; severity: string; code: string; message: string; sheet_name?: string; cell_range?: string; suggested_action?: string; status: string }
export type CostItem = { id: string; project_name: string; code?: string; name: string; description?: string; specification?: string; unit?: string; quantity: DecimalValue; unit_price: DecimalValue; total: DecimalValue; region: string; pricing_date: string; specialty: string; pricing_mode: string; source: { file_name: string; sheet_name: string; start_row: number }; components: Array<{ id: string; category: string; name: string; amount: DecimalValue }> }
export type SearchResult = { items: CostItem[]; total: number; next_cursor?: string }
export type Rule = { id: string; rule_type: string; source_value: string; target_value: string; enabled: boolean; source: string }
export type Backup = { id: string; path: string; kind: string; created_at: string; database_sha256: string; file_count: number; status: string }

let token = typeof sessionStorage === 'undefined' ? '' : sessionStorage.getItem('cost-data-token') || ''

export async function request<T = unknown>(path: string, init: RequestInit = {}): Promise<T> {
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
