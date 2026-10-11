/**
 * 后端 progress 事件的步骤元数据。
 *
 * 步骤名与 app/agent/nodes/*.py 中的 `step = "..."` 一一对应，
 * 一共 12 个。前端把它们归入 5 个阶段，用于渲染执行时间线。
 * 触发自动校正时，校正SQL / 校验SQL 会按事件顺序重复出现，这是预期行为。
 */

import { uid } from './id.js'

export const PHASES = [
  { key: 'understand', label: '理解问题', hint: '把自然语言拆成检索线索' },
  { key: 'recall', label: '检索元知识', hint: '向量检索字段、取值与指标' },
  { key: 'fuse', label: '融合与过滤', hint: '合并召回结果并筛掉无关信息' },
  { key: 'generate', label: '生成 SQL', hint: '基于表/指标/日期上下文写 SQL' },
  { key: 'execute', label: '校验与执行', hint: '校验通过后在数仓执行' },
]

const STEP_TABLE = {
  抽取关键词: { phase: 'understand', icon: 'key', hint: '从问题中提炼关键词' },
  召回字段信息: { phase: 'recall', icon: 'columns', hint: 'Qdrant 向量召回相关字段' },
  召回字段取值: { phase: 'recall', icon: 'search', hint: 'ES 检索字段的真实取值' },
  召回指标信息: { phase: 'recall', icon: 'metric', hint: 'Qdrant 向量召回业务指标' },
  合并召回信息: { phase: 'fuse', icon: 'layers', hint: '合并多路召回结果' },
  过滤表信息: { phase: 'fuse', icon: 'filter', hint: '大模型筛选相关表' },
  过滤指标信息: { phase: 'fuse', icon: 'filter', hint: '大模型筛选相关指标' },
  添加额外上下文: { phase: 'fuse', icon: 'calendar', hint: '补充日期与数据库方言信息' },
  生成SQL: { phase: 'generate', icon: 'sparkles', hint: '大模型生成 SQL' },
  校验SQL: { phase: 'execute', icon: 'shield', hint: 'EXPLAIN 校验 SQL 合法性' },
  校正SQL: { phase: 'generate', icon: 'wrench', hint: '校验失败后重新校正 SQL' },
  运行SQL: { phase: 'execute', icon: 'play', hint: '在数仓执行并返回结果' },
}

const FALLBACK = { phase: 'other', icon: 'dot', hint: '' }

export function stepMeta(name) {
  return STEP_TABLE[name] || FALLBACK
}

export function phaseLabel(key) {
  return PHASES.find((p) => p.key === key)?.label || '其他'
}

export const STATUS_TEXT = {
  running: '进行中',
  success: '已完成',
  error: '失败',
  interrupted: '已中断',
  pending: '等待中',
}

/**
 * 把步骤列表按阶段分组，保持事件到达顺序。
 * 返回 [{ phase, label, hint, steps: [...] }]
 */
export function groupByPhase(steps) {
  const groups = []
  const index = new Map()

  for (const step of steps) {
    const phase = stepMeta(step.name).phase
    let group = index.get(phase)
    if (!group) {
      group = {
        phase,
        label: phaseLabel(phase),
        hint: PHASES.find((p) => p.key === phase)?.hint || '',
        steps: [],
      }
      index.set(phase, group)
      groups.push(group)
    }
    group.steps.push(step)
  }

  return groups
}

/** 汇总一次执行的步骤状态，用于头部摘要 */
export function summarizeSteps(steps) {
  const total = steps.length
  let done = 0
  let failed = 0
  let running = 0

  for (const step of steps) {
    if (step.status === 'success') done += 1
    else if (step.status === 'error') failed += 1
    else if (step.status === 'running') running += 1
  }

  return { total, done, failed, running, interrupted: total - done - failed - running }
}

function countAttempts(steps, name) {
  return steps.reduce((total, step) => (step.name === name ? total + 1 : total), 0)
}

/** 找同名且仍在执行的步骤 —— 它的 success/error 事件还没到 */
function findOpenStep(steps, name) {
  for (let i = steps.length - 1; i >= 0; i -= 1) {
    const step = steps[i]
    if (step.name === name && step.status === 'running') return step
  }
  return null
}

/**
 * 归并一条 progress 事件到步骤列表（就地修改）。
 *
 * 两个关键点：
 * 1. extract_keywords 之后的三路召回是**并发**的，事件会交错到达，
 *    所以必须按步骤名匹配，不能假设「最后一个步骤就是当前步骤」；
 * 2. 同一步骤可能被执行多次（校验失败 → 校正 → 再校验），这时要**新建一条**
 *    并记下 attempt，时间线才能显示「第 2 次」。
 *
 * @param {Array} steps  步骤列表（会被就地修改）
 * @param {string} name  步骤名
 * @param {string} status running / success / error / ...
 */
export function mergeProgressEvent(steps, name, status) {
  const now = Date.now()
  const open = findOpenStep(steps, name)

  if (status === 'running') {
    if (open) return
    steps.push({
      id: uid('step'),
      name,
      status: 'running',
      startedAt: now,
      endedAt: null,
      duration: null,
      attempt: countAttempts(steps, name) + 1,
    })
    return
  }

  if (open) {
    open.status = status
    open.endedAt = now
    open.duration = now - open.startedAt
    return
  }

  // 没收到配对的 running（事件丢失或乱序）：补一条已结束的步骤
  steps.push({
    id: uid('step'),
    name,
    status,
    startedAt: now,
    endedAt: now,
    duration: 0,
    attempt: countAttempts(steps, name) + 1,
    detached: true,
  })
}
