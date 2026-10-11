import { computed, ref } from 'vue'

import { createSseParser, parseJsonData } from '../utils/sse.js'
import { mergeProgressEvent } from '../utils/steps.js'
import { uid } from '../utils/id.js'
import { DEFAULT_TITLE, useConversations } from './useConversations.js'

/**
 * 可调参数（都用 VITE_* 环境变量覆盖，见 frontend/.env.example）：
 *  - VITE_QUERY_ENDPOINT                查询接口地址
 *  - VITE_API_KEY                       后端 api.api_key 的值（后端启用鉴权时必须填）
 *  - VITE_QUERY_CONNECT_TIMEOUT_MS      请求发出后多久没收到首个数据就放弃
 *  - VITE_QUERY_IDLE_TIMEOUT_MS         两个事件之间允许的最长静默
 */
const ENV = import.meta.env || {}

function positiveNumber(value, fallback) {
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback
}

const ENDPOINT = ENV.VITE_QUERY_ENDPOINT || '/api/query'
const API_KEY = ENV.VITE_API_KEY || ''
const CONNECT_TIMEOUT_MS = positiveNumber(ENV.VITE_QUERY_CONNECT_TIMEOUT_MS, 30000)
const IDLE_TIMEOUT_MS = positiveNumber(ENV.VITE_QUERY_IDLE_TIMEOUT_MS, 180000)
/** 收到终结事件后，等待连接真正关闭的宽限期 */
const FINALIZE_GRACE_MS = 1500

/** 全局单例：同一时刻只允许一次查询在跑 */
const running = ref(false)
let controller = null
let stopRequested = false

function clearTimer(timer) {
  if (timer) clearTimeout(timer)
  return null
}

function humanDuration(ms) {
  if (ms % 60000 === 0) return `${ms / 60000} 分钟`
  return `${Math.round(ms / 1000)} 秒`
}

function makeTable(rows, { truncated = false, rowLimit = null } = {}) {
  const columns = []
  for (const row of rows) {
    if (!row || typeof row !== 'object') continue
    for (const key of Object.keys(row)) {
      if (!columns.includes(key)) columns.push(key)
    }
  }
  return { id: uid('table'), columns, rows, receivedAt: Date.now(), truncated, rowLimit }
}

/** 返回事件类型，便于调用方识别终结事件 */
function applyEvent(turn, event) {
  const payload = parseJsonData(event.data)
  if (!payload) return null

  if (payload.type === 'progress') {
    if (typeof payload.step !== 'string') return 'progress'
    // 归并逻辑在 utils/steps.js（纯函数，便于单独验证次数与并发乱序的处理）
    mergeProgressEvent(turn.steps, payload.step, payload.status === 'running' ? 'running' : payload.status)
    return 'progress'
  }

  if (payload.type === 'result') {
    if (Array.isArray(payload.data)) {
      // 后端会带 truncated / row_limit：结果被服务端行数上限截断时告知用户
      turn.tables.push(
          makeTable(payload.data, {
            truncated: payload.truncated === true,
            rowLimit: Number.isFinite(payload.row_limit) ? payload.row_limit : null,
          }),
      )
    }
    return 'result'
  }

  if (payload.type === 'error') {
    turn.error = payload.message ? String(payload.message) : '执行出错'
    return 'error'
  }

  return null
}

function finishTurn(turn, status) {
  const now = Date.now()
  turn.endedAt = now
  turn.duration = now - turn.startedAt
  turn.status = status

  for (const step of turn.steps) {
    if (step.status !== 'running') continue
    step.status = status === 'stopped' ? 'interrupted' : 'error'
    step.endedAt = now
    step.duration = now - step.startedAt
  }

  turn.empty = status === 'done' && !turn.tables.length && !turn.error
}

async function readErrorDetail(response) {
  try {
    const text = (await response.text()).slice(0, 800)
    if (!text) return ''
    try {
      const data = JSON.parse(text)
      const detail = data?.detail
      if (Array.isArray(detail)) {
        return detail.map((item) => item?.msg || JSON.stringify(item)).join('；').slice(0, 300)
      }
      if (detail) return String(detail).slice(0, 300)
      if (data?.message) return String(data.message).slice(0, 300)
      return ''
    } catch {
      // 非 JSON：可能是反向代理的错误页或 HTML 堆栈
      return text.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 200)
    }
  } catch {
    return ''
  }
}

export function useChat() {
  const { activeConversation, ensureConversation, touchConversation, renameConversation } =
      useConversations()

  const activeTurn = computed(() => {
    const messages = activeConversation.value?.messages ?? []
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      if (messages[i].role === 'assistant') return messages[i]
    }
    return null
  })

  const hasMessages = computed(() => (activeConversation.value?.messages.length ?? 0) > 0)

  async function send(question) {
    const text = String(question ?? '').trim()
    if (!text || running.value) return

    const conversation = ensureConversation()
    if (!conversation) return

    conversation.messages.push(
        { id: uid('msg'), role: 'user', content: text, at: Date.now() },
        {
          id: uid('turn'),
          role: 'assistant',
          status: 'running',
          question: text,
          startedAt: Date.now(),
          endedAt: null,
          duration: null,
          steps: [],
          tables: [],
          error: null,
          empty: false,
        },
    )

    // 关键：必须从数组里取回「响应式代理」再修改。
    // 若继续修改上面那个原始对象，状态确实会变、也会落盘（刷新后看得见），
    // 但不会触发任何渲染副作用 —— 表现就是流式过程中界面完全不动。
    const turn = conversation.messages[conversation.messages.length - 1]

    if (conversation.title === DEFAULT_TITLE) {
      renameConversation(conversation.id, text.length > 28 ? `${text.slice(0, 28)}…` : text)
    }

    running.value = true
    stopRequested = false
    controller = new AbortController()

    let settled = false
    let sawTerminal = false
    let idleTimer = null
    let graceTimer = null

    /**
     * 结束一次执行。
     *
     * 关键点：不把「界面恢复可用」押在「连接会正常关闭」上。
     * 只要已经拿到终结事件（result / error）、或者判定为超时/截断，
     * 就立刻收尾，避免界面永远卡在「正在执行」而只能手动终止。
     */
    function finalize(status) {
      if (settled) return
      settled = true
      idleTimer = clearTimer(idleTimer)
      graceTimer = clearTimer(graceTimer)
      finishTurn(turn, status)
    }

    /** 重置静默看门狗；超时则主动断开并给出可读原因 */
    function armIdle(ms, reason) {
      idleTimer = clearTimer(idleTimer)
      idleTimer = setTimeout(() => {
        idleTimer = null
        turn.error = reason
        try {
          controller?.abort()
        } catch {
          /* 忽略 */
        }
        finalize('error')
      }, ms)
    }

    /** 收到终结事件后，给连接一点时间自然关闭；迟迟不关就自己收尾 */
    function armFinalizeGrace() {
      sawTerminal = true
      idleTimer = clearTimer(idleTimer)
      graceTimer = clearTimer(graceTimer)
      graceTimer = setTimeout(() => {
        graceTimer = null
        try {
          controller?.abort()
        } catch {
          /* 忽略 */
        }
        finalize(turn.error ? 'error' : 'done')
      }, FINALIZE_GRACE_MS)
    }

    const connectTimeoutReason =
        `服务端在 ${humanDuration(CONNECT_TIMEOUT_MS)}内没有返回任何数据，连接可能已被中断（可直接重试）`
    const idleTimeoutReason =
        `已有 ${humanDuration(IDLE_TIMEOUT_MS)}没收到服务端的新消息，已停止等待`

    armIdle(CONNECT_TIMEOUT_MS, connectTimeoutReason)

    try {
      const headers = { 'Content-Type': 'application/json', Accept: 'text/event-stream' }
      // 后端配置了 api.api_key 时要带上；未配置时后端不校验，这里也不会发这个头
      if (API_KEY) headers['X-API-Key'] = API_KEY

      const response = await fetch(ENDPOINT, {
        method: 'POST',
        headers,
        body: JSON.stringify({ query: text }),
        signal: controller.signal,
      })

      if (!response.ok) {
        const detail = await readErrorDetail(response)
        throw new Error(detail || `服务端返回 ${response.status} ${response.statusText || ''}`.trim())
      }
      if (!response.body) throw new Error('当前浏览器不支持流式响应')

      const reader = response.body.getReader()
      const decoder = new TextDecoder('utf-8')
      const parser = createSseParser()

      for (;;) {
        const { value, done } = await reader.read()
        if (done) break

        // 有任何字节到达就重置看门狗：首字节之后切换为较宽松的静默阈值
        armIdle(IDLE_TIMEOUT_MS, idleTimeoutReason)

        for (const event of parser.push(decoder.decode(value, { stream: true }))) {
          const type = applyEvent(turn, event)
          if (type === 'result' || type === 'error') armFinalizeGrace()
        }
      }

      for (const event of parser.flush()) {
        const type = applyEvent(turn, event)
        if (type === 'result' || type === 'error') sawTerminal = true
      }

      if (settled) {
        // 已由终结事件收尾（连接只是关得晚），无需再处理
      } else if (turn.error) {
        finalize('error')
      } else if (!sawTerminal) {
        // 一次成功的执行必然以 result 收尾、失败必然以 error 收尾；
        // 两者都没有说明响应被中途截断，不能当成成功。
        turn.error = '连接在返回结果之前中断了，未拿到完整结果（可直接重试）'
        finalize('error')
      } else {
        finalize('done')
      }
    } catch (error) {
      if (settled) {
        // 上面的超时/宽限逻辑自己 abort 产生的异常，忽略
      } else if (error?.name === 'AbortError') {
        if (stopRequested) {
          turn.error = null
          finalize('stopped')
        } else {
          if (!turn.error) turn.error = '请求已中断'
          finalize('error')
        }
      } else {
        turn.error = error?.message || '请求失败'
        finalize('error')
      }
    } finally {
      idleTimer = clearTimer(idleTimer)
      graceTimer = clearTimer(graceTimer)
      running.value = false
      controller = null
      touchConversation(conversation.id)
    }
  }

  function stop() {
    stopRequested = true
    controller?.abort()
  }

  return { running, activeTurn, hasMessages, send, stop }
}
