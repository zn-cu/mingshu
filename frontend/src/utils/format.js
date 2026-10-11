/** 时间、数字与单元格的展示格式化 */

function pad(n) {
  return String(n).padStart(2, '0')
}

/** 毫秒 → 人类可读耗时 */
export function formatDuration(ms) {
  if (ms == null || !Number.isFinite(ms) || ms < 0) return ''
  if (ms < 1000) return `${Math.round(ms)} 毫秒`
  if (ms < 10000) return `${(ms / 1000).toFixed(1)} 秒`
  if (ms < 60000) return `${Math.round(ms / 1000)} 秒`
  const total = Math.round(ms / 1000)
  return `${Math.floor(total / 60)} 分 ${pad(total % 60)} 秒`
}

/** 时间戳 → HH:mm */
export function formatClock(ts) {
  const d = new Date(ts)
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** 时间戳 → 今天 / 昨天 / MM-DD */
export function formatDay(ts) {
  const d = new Date(ts)
  const today = new Date()
  const startOfToday = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime()
  const dayMs = 86400000

  if (ts >= startOfToday) return '今天'
  if (ts >= startOfToday - dayMs) return '昨天'
  if (d.getFullYear() === today.getFullYear()) return `${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

export function isNumeric(value) {
  if (typeof value === 'number') return Number.isFinite(value)
  if (typeof value === 'string' && value.trim() !== '') {
    return Number.isFinite(Number(value))
  }
  return false
}

/** 数字加千分位；整数不带小数，小数最多保留 4 位 */
export function formatNumber(value) {
  const n = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(n)) return String(value)
  if (Number.isInteger(n) && Math.abs(n) < 1e15) return n.toLocaleString('zh-CN')
  if (Math.abs(n) >= 1e15 || (Math.abs(n) < 1e-4 && n !== 0)) return n.toExponential(4)
  return n.toLocaleString('zh-CN', { maximumFractionDigits: 4 })
}

/**
 * 单元格渲染描述。
 * kind: null | number | boolean | text —— 数字右对齐，null 弱化显示。
 */
export function describeCell(value) {
  if (value === null) return { kind: 'null', text: 'NULL' }
  if (value === undefined) return { kind: 'null', text: 'NULL' }
  if (typeof value === 'boolean') return { kind: 'boolean', text: value ? 'true' : 'false' }
  if (value === '') return { kind: 'text', text: '' }

  if (typeof value === 'number') {
    return { kind: 'number', text: formatNumber(value) }
  }

  if (typeof value === 'object') {
    let text
    try {
      text = JSON.stringify(value)
    } catch {
      text = String(value)
    }
    return { kind: 'text', text }
  }

  const text = String(value)
  return { kind: isNumeric(text) ? 'number' : 'text', text: isNumeric(text) ? formatNumber(text) : text }
}

/** 单元格原始值 → 纯文本（用于复制/导出） */
export function rawText(value) {
  if (value === null || value === undefined) return ''
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value)
    } catch {
      return String(value)
    }
  }
  return String(value)
}

/** 表格列宽估算：按表头与首行内容的字符数给一个初始宽度 */
export function estimateColumnWidth(column, rows) {
  const header = String(column).length
  let max = header
  const sample = Math.min(rows.length, 40)
  for (let i = 0; i < sample; i += 1) {
    const len = String(rawText(rows[i]?.[column])).length
    if (len > max) max = len
  }
  return Math.min(Math.max(max, 6), 40) * 8 + 24
}

/** 带时间戳的导出文件名 */
export function timestampName(prefix, ext) {
  const d = new Date()
  const stamp = `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`
  return `${prefix}-${stamp}.${ext}`
}
