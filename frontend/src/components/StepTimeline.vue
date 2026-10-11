<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import AppIcon from './AppIcon.vue'
import { groupByPhase, stepMeta, summarizeSteps, STATUS_TEXT } from '../utils/steps.js'
import { formatDuration } from '../utils/format.js'

const props = defineProps({
  turn: { type: Object, required: true },
})

const expanded = ref(true)
const now = ref(Date.now())
let timer = null

const groups = computed(() => groupByPhase(props.turn.steps || []))
const summary = computed(() => summarizeSteps(props.turn.steps || []))

const statusIcon = (status) =>
    ({ running: 'dot', success: 'check', error: 'x', interrupted: 'stop' }[status] || 'dot')

const summaryText = computed(() => {
  const { total, done, failed, interrupted } = summary.value
  if (!total) {
    return props.turn.status === 'running' ? '正在准备…' : '未执行任何步骤'
  }
  const parts = [`${done}/${total} 步已完成`]
  if (failed) parts.push(`${failed} 步失败`)
  if (interrupted) parts.push(`${interrupted} 步中断`)
  return parts.join(' · ')
})

const elapsed = computed(() => {
  const { startedAt, endedAt, status } = props.turn
  if (!startedAt) return 0
  const end = endedAt ?? (status === 'running' ? now.value : startedAt)
  return Math.max(0, end - startedAt)
})

function startTimer() {
  stopTimer()
  timer = setInterval(() => {
    now.value = Date.now()
  }, 200)
}

function stopTimer() {
  if (timer) clearInterval(timer)
  timer = null
}

watch(
    () => props.turn.status,
    (status) => {
      if (status === 'running') startTimer()
      else stopTimer()
    },
)

onMounted(() => {
  if (props.turn.status === 'running') startTimer()
})

onBeforeUnmount(stopTimer)
</script>

<template>
  <section class="timeline">
    <header class="timeline-head">
      <span class="state-dot" :class="turn.status"/>
      <span class="head-title">执行过程</span>
      <span class="head-summary">{{ summaryText }}</span>
      <span class="head-elapsed">
        <AppIcon name="clock" :size="13"/>
        {{ formatDuration(elapsed) }}
      </span>
      <button class="head-toggle" type="button" @click="expanded = !expanded">
        <AppIcon :name="expanded ? 'chevronDown' : 'chevronRight'" :size="13"/>
        {{ expanded ? '收起细节' : '展开细节' }}
      </button>
    </header>

    <div v-show="expanded" class="timeline-body">
      <div v-for="group in groups" :key="group.phase" class="phase">
        <div class="phase-head">
          <span class="phase-label">{{ group.label }}</span>
          <span class="phase-hint">{{ group.hint }}</span>
        </div>

        <ul class="steps">
          <li v-for="step in group.steps" :key="step.id" class="step" :class="step.status">
            <span class="node">
              <AppIcon :name="statusIcon(step.status)" :size="10" :stroke="2.6"/>
            </span>
            <span class="step-main">
              <span class="step-name">
                {{ step.name }}
                <em v-if="step.attempt > 1" class="attempt">第 {{ step.attempt }} 次</em>
              </span>
              <span class="step-hint">{{ stepMeta(step.name).hint }}</span>
            </span>
            <span class="step-time">
              <template v-if="step.status === 'running'">
                <span class="da-spinner"/>
                进行中
              </template>
              <template v-else-if="step.duration != null">{{ formatDuration(step.duration) }}</template>
              <template v-else>{{ STATUS_TEXT[step.status] || '' }}</template>
            </span>
          </li>
        </ul>
      </div>
    </div>
  </section>
</template>

<style scoped>
.timeline {
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg-sunken);
  overflow: hidden;
}

/* ----------------------------------------------------------- 头部 ----- */
.timeline-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 12px;
  border-bottom: 1px solid transparent;
  font-size: 12.5px;
}

.timeline-body {
  border-top: 1px solid var(--border);
}

.state-dot {
  flex: none;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--text-mute);
}

.state-dot.running {
  background: var(--accent);
  animation: da-pulse 1.1s ease-in-out infinite;
}

.state-dot.done {
  background: var(--success);
}

.state-dot.error {
  background: var(--danger);
}

.state-dot.stopped {
  background: var(--warning);
}

.head-title {
  font-weight: 600;
  color: var(--text);
}

.head-summary {
  color: var(--text-dim);
}

.head-elapsed {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-left: auto;
  color: var(--text-mute);
  font-variant-numeric: tabular-nums;
}

.head-toggle {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 2px 6px;
  border-radius: var(--radius-xs);
  color: var(--text-mute);
  font-size: 12px;
}

.head-toggle:hover {
  background: var(--bg-hover);
  color: var(--text);
}

/* --------------------------------------------------------- 阶段/步骤 -- */
.timeline-body {
  padding: 6px 12px 12px;
}

.phase + .phase {
  margin-top: 12px;
}

.phase-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 6px 0 4px;
}

.phase-label {
  color: var(--text-dim);
  font-size: 11.5px;
  font-weight: 650;
  letter-spacing: 0.04em;
}

.phase-hint {
  color: var(--text-mute);
  font-size: 11px;
}

.steps {
  position: relative;
  margin: 0;
  padding: 0;
  list-style: none;
}

/* 竖向连接线 */
.steps::before {
  content: '';
  position: absolute;
  left: 9px;
  top: 10px;
  bottom: 10px;
  width: 1px;
  background: var(--border);
}

.step {
  position: relative;
  display: grid;
  grid-template-columns: 20px minmax(0, 1fr) auto;
  align-items: center;
  gap: 9px;
  padding: 5px 0;
}

.node {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 19px;
  height: 19px;
  border-radius: 50%;
  border: 1.5px solid var(--border-strong);
  background: var(--bg-elev);
  color: var(--text-mute);
  z-index: 1;
}

.step.success .node {
  border-color: var(--success);
  background: var(--success-soft);
  color: var(--success);
}

.step.error .node {
  border-color: var(--danger);
  background: var(--danger-soft);
  color: var(--danger);
}

.step.running .node {
  border-color: var(--accent);
  background: var(--accent-soft);
  color: var(--accent);
  animation: da-pulse 1.1s ease-in-out infinite;
}

.step.interrupted .node {
  border-color: var(--warning);
  background: var(--warning-soft);
  color: var(--warning);
}

.step-main {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.step-name {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--text);
  font-size: 13px;
}

.step.running .step-name {
  font-weight: 600;
}

.step.error .step-name {
  color: var(--danger);
}

.attempt {
  padding: 0 5px;
  border-radius: 999px;
  background: var(--warning-soft);
  color: var(--warning);
  font-size: 10.5px;
  font-style: normal;
}

.step-hint {
  overflow: hidden;
  color: var(--text-mute);
  font-size: 11.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.step-time {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--text-mute);
  font-size: 11.5px;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.step.running .step-time {
  color: var(--accent);
}

.step.error .step-time {
  color: var(--danger);
}
</style>
