<script setup>
import { computed, ref } from 'vue'

import AppIcon from './AppIcon.vue'
import ResultTable from './ResultTable.vue'
import StepTimeline from './StepTimeline.vue'
import { formatClock, formatDuration } from '../utils/format.js'
import { copyText } from '../utils/export.js'

const props = defineProps({
  message: { type: Object, required: true },
})

const emit = defineEmits(['retry'])

const copied = ref(false)
let copyTimer = null

const isUser = computed(() => props.message.role === 'user')
const turn = computed(() => props.message)

const STATUS_MAP = {
  running: { text: '执行中', icon: 'dot' },
  done: { text: '已完成', icon: 'check' },
  error: { text: '执行失败', icon: 'alert' },
  stopped: { text: '已中断', icon: 'stop' },
}

const status = computed(() => STATUS_MAP[turn.value.status] || { text: '执行中', icon: 'dot' })
const canRetry = computed(() => ['error', 'stopped'].includes(turn.value.status))

function buildSummary() {
  const current = turn.value
  const lines = [`问题：${current.question}`, `状态：${status.value.text}`]
  if (current.duration != null) lines.push(`总耗时：${formatDuration(current.duration)}`)
  if (current.steps.length) {
    lines.push('', '执行过程：')
    const mark = { success: '✓', error: '✗', running: '…', interrupted: '⏹' }
    for (const step of current.steps) {
      const duration = step.duration != null ? `（${formatDuration(step.duration)}）` : ''
      const attempt = step.attempt > 1 ? ` [第 ${step.attempt} 次]` : ''
      lines.push(`  ${mark[step.status] || '·'} ${step.name}${attempt}${duration}`)
    }
  }
  if (current.tables.length) {
    lines.push('', `结果集：${current.tables.map((table) => `${table.rows.length} 行 × ${table.columns.length} 列`).join('，')}`)
  }
  if (current.error) lines.push('', `错误：${current.error}`)
  return lines.join('\n')
}

async function flashCopied() {
  copied.value = true
  clearTimeout(copyTimer)
  copyTimer = setTimeout(() => {
    copied.value = false
  }, 1600)
}

async function copySummary() {
  if (await copyText(buildSummary())) await flashCopied()
}

async function copyQuestion() {
  if (await copyText(props.message.content || '')) await flashCopied()
}
</script>

<template>
  <!-- 用户提问 -->
  <div v-if="isUser" class="user-row da-fade-up">
    <div class="user-bubble">
      <p class="user-text">{{ message.content }}</p>
      <div class="user-meta">
        <span>{{ formatClock(message.at) }}</span>
        <button class="mini" type="button" @click="copyQuestion">
          <AppIcon :name="copied ? 'check' : 'copy'" :size="12"/>
          {{ copied ? '已复制' : '复制' }}
        </button>
      </div>
    </div>
  </div>

  <!-- 助手一次执行 -->
  <article v-else class="turn da-fade-up">
    <header class="turn-head">
      <span class="turn-status" :class="turn.status">
        <AppIcon :name="status.icon" :size="12" :stroke="2.2"/>
        {{ status.text }}
      </span>
      <span class="turn-meta">{{ formatClock(turn.startedAt) }}</span>
      <span v-if="turn.steps.length" class="turn-meta">{{ turn.steps.length }} 个步骤</span>
      <div class="turn-actions">
        <button v-if="canRetry" class="btn btn--sm" type="button" @click="emit('retry', turn.question)">
          <AppIcon name="refresh" :size="13"/>
          重试
        </button>
        <button class="btn btn--sm btn--ghost" type="button" title="复制执行摘要" @click="copySummary">
          <AppIcon :name="copied ? 'check' : 'copy'" :size="13"/>
          摘要
        </button>
      </div>
    </header>

    <StepTimeline :turn="turn"/>

    <ResultTable v-for="table in turn.tables" :key="table.id" :table="table"/>

    <div v-if="turn.error" class="turn-error">
      <AppIcon name="alert" :size="16"/>
      <div class="error-body">
        <strong>执行失败</strong>
        <p>{{ turn.error }}</p>
      </div>
    </div>

    <p v-else-if="turn.empty" class="turn-note">
      <AppIcon name="check" :size="13"/>
      SQL 已执行完成，但没有返回数据行。
    </p>

    <p v-if="turn.status === 'stopped'" class="turn-note is-warning">
      <AppIcon name="stop" :size="13"/>
      已中断本次查询，未得到完整结果。
    </p>
  </article>
</template>

<style scoped>
/* --------------------------------------------------------- 用户气泡 -- */
.user-row {
  display: flex;
  justify-content: flex-end;
  padding: 4px 0;
}

.user-bubble {
  max-width: min(78%, 640px);
  padding: 10px 14px 8px;
  border-radius: var(--radius-lg) var(--radius-lg) 4px var(--radius-lg);
  background: var(--accent);
  color: #fff;
  box-shadow: 0 2px 10px var(--accent-ring);
}

.user-text {
  font-size: 14px;
  line-height: 1.65;
  white-space: pre-wrap;
  word-break: break-word;
}

.user-meta {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 4px;
  color: rgba(255, 255, 255, 0.75);
  font-size: 11px;
}

.mini {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 1px 6px;
  border-radius: 999px;
  color: inherit;
  font-size: 11px;
  transition: background var(--dur-fast) var(--ease);
}

.mini:hover {
  background: rgba(255, 255, 255, 0.18);
}

/* --------------------------------------------------------- 助手卡片 -- */
.turn {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 4px 0;
}

.turn-head {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 26px;
}

.turn-status {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 2px 9px;
  border-radius: 999px;
  background: var(--bg-sunken);
  color: var(--text-dim);
  font-size: 12px;
  font-weight: 600;
}

.turn-status.running {
  background: var(--accent-soft);
  color: var(--accent);
}

.turn-status.done {
  background: var(--success-soft);
  color: var(--success);
}

.turn-status.error {
  background: var(--danger-soft);
  color: var(--danger);
}

.turn-status.stopped {
  background: var(--warning-soft);
  color: var(--warning);
}

.turn-meta {
  color: var(--text-mute);
  font-size: 11.5px;
  font-variant-numeric: tabular-nums;
}

.turn-actions {
  display: flex;
  gap: 6px;
  margin-left: auto;
  opacity: 0;
  transition: opacity var(--dur) var(--ease);
}

.turn:hover .turn-actions,
.turn-actions:focus-within {
  opacity: 1;
}

/* ------------------------------------------------------- 错误与提示 -- */
.turn-error {
  display: flex;
  gap: 10px;
  padding: 11px 13px;
  border: 1px solid var(--danger);
  border-radius: var(--radius-md);
  background: var(--danger-soft);
  color: var(--danger);
}

.error-body strong {
  display: block;
  font-size: 13px;
}

.error-body p {
  margin-top: 2px;
  color: var(--text-dim);
  font-size: 12.5px;
  word-break: break-word;
}

.turn-note {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 2px 2px;
  color: var(--text-mute);
  font-size: 12.5px;
}

.turn-note.is-warning {
  color: var(--warning);
}

@media (max-width: 720px) {
  .user-bubble {
    max-width: 88%;
  }

  .turn-actions {
    opacity: 1;
  }
}
</style>
