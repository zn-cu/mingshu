/** 复制到剪贴板与结果导出（CSV / TSV），零依赖实现 */

import { rawText, timestampName } from './format.js'

/** 复制文本；优先 Clipboard API，失败时回退到隐藏 textarea */
export async function copyText(text) {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    /* 继续走回退方案（非 HTTPS 或权限被拒） */
  }

  try {
    const area = document.createElement('textarea')
    area.value = text
    area.setAttribute('readonly', '')
    area.style.position = 'fixed'
    area.style.top = '-1000px'
    area.style.opacity = '0'
    document.body.appendChild(area)
    area.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(area)
    return ok
  } catch {
    return false
  }
}

function escapeCsv(value) {
  const text = rawText(value)
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

/** 表格 → CSV 文本（CRLF，兼容 Excel） */
export function toCsv(columns, rows) {
  const lines = [columns.map(escapeCsv).join(',')]
  for (const row of rows) {
    lines.push(columns.map((column) => escapeCsv(row?.[column])).join(','))
  }
  return lines.join('\r\n')
}

/** 表格 → TSV 文本（粘贴进 Excel 可直接分列） */
export function toTsv(columns, rows) {
  const clean = (v) => rawText(v).replace(/[\t\r\n]+/g, ' ')
  const lines = [columns.map(clean).join('\t')]
  for (const row of rows) {
    lines.push(columns.map((column) => clean(row?.[column])).join('\t'))
  }
  return lines.join('\n')
}

/** 触发浏览器下载 */
export function downloadText(filename, text, mime = 'text/plain;charset=utf-8') {
  const blob = new Blob([text], { type: mime })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

/** 导出结果表为 CSV（带 BOM，避免 Excel 打开中文乱码） */
export function exportCsv(columns, rows, prefix = 'query-result') {
  downloadText(timestampName(prefix, 'csv'), `\uFEFF${toCsv(columns, rows)}`, 'text/csv;charset=utf-8')
}
