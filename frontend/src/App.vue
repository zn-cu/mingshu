<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'

import AppIcon from './components/AppIcon.vue'
import AppSidebar from './components/AppSidebar.vue'
import ChatInput from './components/ChatInput.vue'
import ChatMessage from './components/ChatMessage.vue'
import EmptyState from './components/EmptyState.vue'
import { useChat } from './composables/useChat.js'
import { useConversations } from './composables/useConversations.js'

const SAMPLES = [
  '统计华北地区的销售总额',
  '最近 7 天每天的订单量是多少',
  '各品类的平均客单价对比',
  '哪些客户贡献的销售额最高',
]

const {
  conversationItems,
  activeId,
  activeConversation,
  storageWarning,
  createConversation,
  selectConversation,
  removeConversation,
  clearConversation,
  clearAllConversations,
} = useConversations()

const { running, send, stop } = useChat()

const drawerOpen = ref(false)
const scrollEl = ref(null)
const inputRef = ref(null)
const atBottom = ref(true)

const messages = computed(() => activeConversation.value?.messages ?? [])
const currentTitle = computed(() => activeConversation.value?.title || '新的对话')
const questionCount = computed(() => messages.value.filter((message) => message.role === 'user').length)

/** 把流式进展折叠成一个字符串，用于触发自动滚动 */
const streamTick = computed(() => {
  const list = messages.value
  const last = list[list.length - 1]
  return [
    list.length,
    last?.steps?.length ?? 0,
    last?.tables?.length ?? 0,
    last?.status ?? '',
  ].join(':')
})

function scrollToBottom(behavior = 'auto') {
  const el = scrollEl.value
  if (!el) return
  el.scrollTo({ top: el.scrollHeight, behavior })
}

function onScroll() {
  const el = scrollEl.value
  if (!el) return
  atBottom.value = el.scrollHeight - el.scrollTop - el.clientHeight < 80
}

watch(streamTick, async () => {
  await nextTick()
  if (atBottom.value) scrollToBottom()
})

watch(activeId, async () => {
  drawerOpen.value = false
  atBottom.value = true
  await nextTick()
  scrollToBottom()
})

onMounted(async () => {
  await nextTick()
  scrollToBottom()
  inputRef.value?.focus()
})

function onSend(text) {
  send(text)
}

function onPickSample(sample) {
  inputRef.value?.setValue(sample)
}

function onNewConversation() {
  createConversation()
  nextTick(() => inputRef.value?.focus())
}

function onRemoveConversation(id) {
  const item = conversationItems.value.find((entry) => entry.id === id)
  if (item && !window.confirm(`删除对话「${item.title}」？`)) return
  removeConversation(id)
}

function onClearCurrent() {
  if (!messages.value.length) return
  if (!window.confirm('清空当前对话的全部消息？')) return
  clearConversation()
}

function onClearAll() {
  if (!conversationItems.value.length) return
  if (!window.confirm('清空全部对话记录？该操作不可恢复。')) return
  clearAllConversations()
}
</script>

<template>
  <div class="shell">
    <AppSidebar
        :items="conversationItems"
        :active-id="activeId"
        :storage-warning="storageWarning"
        :open="drawerOpen"
        @new="onNewConversation"
        @select="selectConversation"
        @remove="onRemoveConversation"
        @clear-all="onClearAll"
        @close="drawerOpen = false"
    />

    <div v-if="drawerOpen" class="overlay" @click="drawerOpen = false"/>

    <main class="main">
      <header class="topbar">
        <button
            class="icon-btn menu-btn"
            type="button"
            aria-label="打开侧栏"
            @click="drawerOpen = true"
        >
          <AppIcon name="panel" :size="17"/>
        </button>

        <div class="title">
          <h1>{{ currentTitle }}</h1>
          <span class="sub">
            <template v-if="questionCount">{{ questionCount }} 次提问</template>
            <template v-else>尚未提问</template>
          </span>
        </div>

        <span class="endpoint mono">POST /api/query</span>

        <button
            v-if="messages.length"
            class="btn btn--sm btn--danger"
            type="button"
            @click="onClearCurrent"
        >
          <AppIcon name="trash" :size="13"/>
          清空对话
        </button>
      </header>

      <div ref="scrollEl" class="stream" @scroll.passive="onScroll">
        <div class="stream-inner">
          <EmptyState v-if="!messages.length" :samples="SAMPLES" @pick="onPickSample"/>

          <ChatMessage
              v-for="message in messages"
              :key="message.id"
              :message="message"
              @retry="onSend"
          />

          <div class="tail"/>
        </div>

        <Transition name="fade">
          <button
              v-if="!atBottom"
              class="to-bottom"
              type="button"
              title="回到底部"
              aria-label="回到底部"
              @click="scrollToBottom('smooth')"
          >
            <AppIcon name="arrowDown" :size="16"/>
          </button>
        </Transition>
      </div>

      <ChatInput ref="inputRef" :running="running" @send="onSend" @stop="stop"/>
    </main>
  </div>
</template>

<style scoped>
.shell {
  display: flex;
  height: 100%;
  overflow: hidden;
}

.main {
  position: relative;
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
  height: 100%;
}

/* ----------------------------------------------------------- 顶栏 -- */
.topbar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: none;
  height: var(--topbar-h);
  padding: 0 18px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-elev);
}

.menu-btn {
  display: none;
}

.title {
  display: flex;
  flex-direction: column;
  min-width: 0;
  line-height: 1.3;
}

.title h1 {
  overflow: hidden;
  font-size: 14px;
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.title .sub {
  color: var(--text-mute);
  font-size: 11.5px;
}

.endpoint {
  margin-left: auto;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--bg-sunken);
  color: var(--text-mute);
  font-size: 11px;
}

/* --------------------------------------------------------- 消息流 -- */
.stream {
  position: relative;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
}

.stream-inner {
  display: flex;
  flex-direction: column;
  gap: 18px;
  max-width: 820px;
  margin: 0 auto;
  padding: 20px 20px 0;
}

.tail {
  height: 12px;
}

.to-bottom {
  position: sticky;
  bottom: 12px;
  left: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  margin-right: 24px;
  border: 1px solid var(--border);
  border-radius: 50%;
  background: var(--bg-elev);
  color: var(--text-dim);
  box-shadow: var(--shadow-2);
}

.to-bottom:hover {
  color: var(--accent);
  border-color: var(--accent);
}

/* --------------------------------------------------------- 遮罩层 -- */
.overlay {
  position: fixed;
  inset: 0;
  z-index: 30;
  background: rgba(15, 23, 42, 0.45);
  backdrop-filter: blur(2px);
}

/* ----------------------------------------------------------- 动效 -- */
.fade-enter-active,
.fade-leave-active {
  transition: opacity var(--dur) var(--ease), transform var(--dur) var(--ease);
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
  transform: translateY(6px);
}

@media (min-width: 901px) {
  .overlay {
    display: none;
  }
}

@media (max-width: 900px) {
  .menu-btn {
    display: inline-flex;
  }

  .endpoint {
    display: none;
  }

  .stream-inner {
    padding: 16px 14px 0;
  }
}
</style>
