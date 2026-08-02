export type DecimalValue = { value: string | null; scale: number; unit?: string; currency?: string }
export type Comparability = 'searchable' | 'restricted' | 'benchmark_candidate'
export type Project = { id: string; name: string; region: string; pricing_date: string; specialty: string; pricing_mode: string; result_stage: string; project_type?: string; profile?: Record<string, string>; price_context?: Record<string, string>; comparability?: Comparability; area: DecimalValue; latest_version_id?: string; latest_version_no?: number; latest_status?: string; item_count: number; issue_count: number }
export type LibraryKey = 'catalog' | 'resource' | 'quota'
export type WorkspaceRecord = { id: string; library?: LibraryKey; data_type: string; name: string; code?: string; specification?: string; description?: string; unit?: string; quantity: DecimalValue; unit_price: DecimalValue; total: DecimalValue; project_id: string; project_name: string; project_version_id: string; region: string; pricing_date: string; specialty: string; pricing_mode: string; result_stage: string; comparability: Comparability; data_status: 'raw' | 'parsed' | 'reviewed' | 'published' | 'deprecated'; price_context: Record<string, string>; warnings: string[]; source?: { file_name: string; sheet_name: string; start_row: number; field_cells?: Record<string, string> }; attributes: Record<string, unknown> }
export type WorkspaceSearchResult = { items: WorkspaceRecord[]; total: number }
export type LibrarySummary = { key: LibraryKey; name: string; database: string; status: string; record_count: number; project_count: number; updated_at?: string }
export type ProjectDetail = { project: Project & { profile: Record<string, string>; comparability: Comparability }; versions: Array<{ id: string; version_no: number; status: string; label: string; item_count: number }>; data_counts: Record<string, number>; metrics: Array<{ id: string; code: string; name: string; value: DecimalValue; formula: string; status: string; numerator_source: Record<string, unknown>; denominator_source: Record<string, unknown> }>; source_files: Array<{ file_id: string; file_name: string }> }
export type QualityReport = { project_version_id: string; publishable: boolean; summary: { errors: number; warnings: number; total: number }; issues: Array<{ severity: string; code: string; message: string; source?: { file_name: string; sheet_name: string; start_row: number } }> }
export type UnitConversion = { id: string; source_unit: string; target_unit: string; factor: string; basis: string; enabled: boolean }
export type MetricTemplate = { id: string; code: string; name: string; unit: string; formula: string; description?: string; enabled: boolean }
export type Benchmark = { metric_code: string; sample_count: number; mean: DecimalValue; p25: DecimalValue; p50: DecimalValue; p75: DecimalValue; samples: Array<{ project_name: string; region: string; pricing_date: string; value: string; unit: string }> }
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
  if (path.startsWith('/workspace/search')) return { items: [], total: 0 }
  if (path === '/libraries') return []
  if (path.startsWith('/libraries/')) return { items: [], total: 0 }
  if (path.startsWith('/quality/projects')) return { publishable: true, summary: { errors: 0, warnings: 0, total: 0 }, issues: [] }
  if (path.startsWith('/metric-templates') || path.startsWith('/unit-conversions')) return []
  if (path.startsWith('/benchmarks/metrics')) return { metric_code: '', sample_count: 0, mean: { value: null }, p25: { value: null }, p50: { value: null }, p75: { value: null }, samples: [] }
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
