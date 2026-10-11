<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'

import AppIcon from './AppIcon.vue'

const MAX_HEIGHT = 168

const props = defineProps({
  running: { type: Boolean, default: false },
})

const emit = defineEmits(['send', 'stop'])

const text = ref('')
const textareaEl = ref(null)
const composing = ref(false)

const canSend = computed(() => text.value.trim().length > 0 && !props.running)
const rows = computed(() => text.value.split('\n').length)

/** 等待计时：让「正在执行」是看得见在走的，而不是像卡死 */
const waitedMs = ref(0)
let waitTimer = null

const waitedText = computed(() => {
  const seconds = waitedMs.value / 1000
  return `${seconds < 10 ? seconds.toFixed(1) : Math.round(seconds)} 秒`
})

watch(
    () => props.running,
    (isRunning) => {
      clearInterval(waitTimer)
      waitTimer = null
      if (!isRunning) return
      const startedAt = Date.now()
      waitedMs.value = 0
      waitTimer = setInterval(() => {
        waitedMs.value = Date.now() - startedAt
      }, 200)
    },
    { immediate: true },
)

onBeforeUnmount(() => clearInterval(waitTimer))

function resize() {
  const el = textareaEl.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT)}px`
}

watch(text, () => nextTick(resize))

function submit() {
  if (!canSend.value) return
  emit('send', text.value.trim())
  text.value = ''
  nextTick(() => {
    resize()
    focus()
  })
}

function onKeydown(event) {
  if (event.key !== 'Enter' || event.shiftKey) return
  // 中文输入法组词中的回车不触发发送
  if (composing.value || event.isComposing) return
  event.preventDefault()
  submit()
}

function onStop() {
  emit('stop')
  focus()
}

function focus() {
  textareaEl.value?.focus()
}

function setValue(value) {
  text.value = value
  nextTick(() => {
    resize()
    focus()
  })
}

function clear() {
  text.value = ''
  nextTick(resize)
}

defineExpose({ focus, setValue, clear })
</script>

<template>
  <div class="composer">
    <div class="composer-box" :class="{ 'is-running': running }">
      <textarea
          ref="textareaEl"
          v-model="text"
          class="composer-input"
          rows="1"
          spellcheck="false"
          :placeholder="running ? '正在执行查询，可点击右侧按钮中断…' : '用一句话描述你想查的数据，例如：统计华北地区的销售总额'"
          :disabled="running"
          @keydown="onKeydown"
          @compositionstart="composing = true"
          @compositionend="composing = false"
      />

      <button
          v-if="running"
          class="composer-action is-stop"
          type="button"
          title="中断本次查询"
          aria-label="中断本次查询"
          @click="onStop"
      >
        <AppIcon name="stop" :size="15"/>
      </button>
      <button
          v-else
          class="composer-action is-send"
          type="button"
          :disabled="!canSend"
          title="发送（Enter）"
          aria-label="发送"
          @click="submit"
      >
        <AppIcon name="send" :size="16"/>
      </button>
    </div>

    <div class="composer-hint">
      <span v-if="running" class="running-hint">
        <span class="da-spinner"/>
        正在执行 {{ waitedText }}，步骤会实时显示在上方
      </span>
      <span v-else>
        <kbd>Enter</kbd> 发送 · <kbd>Shift</kbd> + <kbd>Enter</kbd> 换行
      </span>
      <span v-if="rows > 1" class="line-count">{{ rows }} 行</span>
    </div>
  </div>
</template>

<style scoped>
.composer {
  padding: 0 20px 18px;
}

.composer-box {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  max-width: 780px;
  margin: 0 auto;
  padding: 8px 8px 8px 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius-xl);
  background: var(--bg-elev);
  box-shadow: var(--shadow-2);
  transition: border-color var(--dur-fast) var(--ease), box-shadow var(--dur-fast) var(--ease);
}

.composer-box:focus-within {
  border-color: var(--accent);
  box-shadow: var(--shadow-2), 0 0 0 3px var(--accent-soft);
}

.composer-box.is-running {
  border-color: var(--warning);
  box-shadow: var(--shadow-2), 0 0 0 3px var(--warning-soft);
}

.composer-input {
  flex: 1;
  min-height: 24px;
  max-height: 168px;
  padding: 7px 0 6px;
  border: none;
  outline: none;
  background: transparent;
  resize: none;
  font-size: 14.5px;
  line-height: 1.6;
  overflow-y: auto;
}

.composer-input::placeholder {
  color: var(--text-mute);
}

.composer-input:disabled {
  cursor: default;
  color: var(--text-dim);
}

.composer-action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  transition: background var(--dur-fast) var(--ease),
  transform var(--dur-fast) var(--ease),
  opacity var(--dur-fast) var(--ease);
}

.composer-action.is-send {
  background: var(--accent);
  color: #fff;
  box-shadow: 0 2px 8px var(--accent-ring);
}

.composer-action.is-send:hover:not(:disabled) {
  background: var(--accent-strong);
}

.composer-action.is-send:disabled {
  background: var(--bg-sunken);
  color: var(--text-mute);
  box-shadow: none;
  cursor: not-allowed;
}

.composer-action.is-stop {
  background: var(--warning-soft);
  color: var(--warning);
}

.composer-action.is-stop:hover {
  background: var(--warning);
  color: #fff;
}

.composer-action:active:not(:disabled) {
  transform: scale(0.94);
}

.composer-hint {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  max-width: 780px;
  margin: 8px auto 0;
  height: 16px;
  color: var(--text-mute);
  font-size: 11.5px;
}

.running-hint {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--warning);
}

.line-count {
  font-variant-numeric: tabular-nums;
}

kbd {
  display: inline-block;
  padding: 1px 5px;
  border: 1px solid var(--border);
  border-bottom-width: 2px;
  border-radius: 4px;
  background: var(--bg-sunken);
  font-family: var(--font-sans);
  font-size: 10.5px;
}

@media (max-width: 640px) {
  .composer {
    padding: 0 12px 12px;
  }

  .composer-hint {
    font-size: 11px;
  }
}
</style>
