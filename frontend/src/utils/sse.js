/**
 * Server-Sent Events 解析。
 *
 * 后端（app/services/query_service.py）按 SSE 规范输出：
 *   data: {"type":"progress","step":"召回字段信息","status":"running"}\n\n
 *
 * 这里实现一个增量解析器，而不是简单地 split('\n\n')：
 *  - 兼容 \r\n 与 \n
 *  - 支持一个事件内多行 data（按规范用 \n 拼接）
 *  - 忽略以 ':' 开头的注释行（心跳）
 *  - 正确处理跨 chunk 被截断的事件
 */

const SEPARATOR = /\r?\n\r?\n/

/** 解析单个事件块（两个空行之间的内容） */
export function parseEventBlock(raw) {
  if (!raw) return null

  // 容忍 BOM：浏览器 TextDecoder 会自动去掉，但抓包/回放的数据里可能残留，
  // 否则首个字段名会变成 "\uFEFFdata" 而被当成未知字段丢弃。
  const text = raw.charCodeAt(0) === 0xfeff ? raw.slice(1) : raw

  const dataLines = []
  let event = 'message'
  let id

  for (const line of text.split(/\r?\n/)) {
    if (!line || line.startsWith(':')) continue

    const colon = line.indexOf(':')
    const field = colon === -1 ? line : line.slice(0, colon)
    let value = colon === -1 ? '' : line.slice(colon + 1)
    if (value.startsWith(' ')) value = value.slice(1)

    if (field === 'data') dataLines.push(value)
    else if (field === 'event') event = value
    else if (field === 'id') id = value
  }

  if (!dataLines.length) return null
  return { event, id, data: dataLines.join('\n') }
}

/** 创建一个增量解析器；push() 返回本次新增的完整事件数组 */
export function createSseParser() {
  let buffer = ''

  return {
    push(text) {
      buffer += text
      const events = []

      for (;;) {
        const match = SEPARATOR.exec(buffer)
        if (!match) break

        const raw = buffer.slice(0, match.index)
        buffer = buffer.slice(match.index + match[0].length)

        const event = parseEventBlock(raw)
        if (event) events.push(event)
      }

      return events
    },

    /** 流结束时冲刷残留内容（末事件可能没有以空行收尾） */
    flush() {
      const raw = buffer
      buffer = ''
      const event = parseEventBlock(raw)
      return event ? [event] : []
    },
  }
}

/** 安全地把事件 data 解析为 JSON 对象 */
export function parseJsonData(data) {
  if (typeof data !== 'string') return data
  const text = data.trim()
  if (!text || text === '[DONE]') return null
  try {
    const parsed = JSON.parse(text)
    return parsed && typeof parsed === 'object' ? parsed : null
  } catch {
    return null
  }
}
