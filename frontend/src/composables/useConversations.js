import { computed, ref } from 'vue'

import { uid } from '../utils/id.js'
import { formatDay, formatClock } from '../utils/format.js'

const STORAGE_KEY = 'mingshu.conversations.v1'
const MAX_CONVERSATIONS = 50
const MAX_MESSAGES_PER_CONVERSATION = 80

export const DEFAULT_TITLE = '新的对话'

function sanitize(raw) {
  if (!raw || !Array.isArray(raw.conversations)) return []

  return raw.conversations
      .filter((item) => item && typeof item.id === 'string' && Array.isArray(item.messages))
      .slice(0, MAX_CONVERSATIONS)
      .map((item) => ({
        id: item.id,
        title: typeof item.title === 'string' && item.title ? item.title : DEFAULT_TITLE,
        createdAt: Number(item.createdAt) || Date.now(),
        updatedAt: Number(item.updatedAt) || Number(item.createdAt) || Date.now(),
        messages: item.messages
            .filter((message) => message && typeof message.role === 'string')
            .map(normalizeMessage),
      }))
}

/**
 * 刷新页面时可能残留「执行中」的历史记录（流已断），
 * 这里统一收敛为「已中断」，避免时间线一直转圈。
 */
function normalizeMessage(message) {
  if (message.role !== 'assistant' || message.status !== 'running') return message

  const endedAt = Date.now()
  return {
    ...message,
    status: 'interrupted',
    endedAt,
    duration: message.startedAt ? endedAt - message.startedAt : null,
    steps: (message.steps || []).map((step) =>
        step.status === 'running'
            ? {
              ...step,
              status: 'interrupted',
              endedAt,
              duration: step.startedAt ? endedAt - step.startedAt : 0,
            }
            : step,
    ),
  }
}

function load() {
  try {
    const text = localStorage.getItem(STORAGE_KEY)
    if (!text) return []
    return sanitize(JSON.parse(text))
  } catch {
    return []
  }
}

const conversations = ref(load())
const activeId = ref(conversations.value[0]?.id ?? null)
/** 持久化失败时置位，界面上给出提示 */
const storageWarning = ref(false)

function persist() {
  const payload = conversations.value
      .slice(0, MAX_CONVERSATIONS)
      .map((conversation) => ({
        ...conversation,
        messages: conversation.messages.slice(-MAX_MESSAGES_PER_CONVERSATION),
      }))

  for (let attempt = 0; attempt < 4; attempt += 1) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ version: 1, conversations: payload }))
      storageWarning.value = false
      return
    } catch {
      // 多半是配额超限：丢掉最旧的会话后重试
      if (payload.length > 1) payload.pop()
      else {
        try {
          localStorage.removeItem(STORAGE_KEY)
        } catch {
          /* 忽略 */
        }
        storageWarning.value = true
        return
      }
    }
  }
}

function createConversation({ activate = true } = {}) {
  const conversation = {
    id: uid('conv'),
    title: DEFAULT_TITLE,
    createdAt: Date.now(),
    updatedAt: Date.now(),
    messages: [],
  }
  conversations.value.unshift(conversation)
  if (activate) activeId.value = conversation.id
  persist()

  // 返回 ref 内部的响应式代理：调用方（useChat）会直接往它里面写消息，
  // 返回原始对象的话那些修改不会触发渲染。
  return conversations.value.find((item) => item.id === conversation.id) ?? conversation
}

// 首次访问时自动建一个会话
if (!conversations.value.length) createConversation()
if (!activeId.value || !conversations.value.some((c) => c.id === activeId.value)) {
  activeId.value = conversations.value[0]?.id ?? null
}

const activeConversation = computed(
    () => conversations.value.find((conversation) => conversation.id === activeId.value) ?? null,
)

const orderedConversations = computed(() =>
    [...conversations.value].sort((a, b) => b.createdAt - a.createdAt),
)

/** 侧边栏用的展示信息 */
const conversationItems = computed(() =>
    orderedConversations.value.map((conversation) => ({
      id: conversation.id,
      title: conversation.title,
      messageCount: conversation.messages.filter((m) => m.role === 'user').length,
      updatedAt: conversation.updatedAt,
      day: formatDay(conversation.updatedAt),
      clock: formatClock(conversation.updatedAt),
    })),
)

function selectConversation(id) {
  if (conversations.value.some((conversation) => conversation.id === id)) activeId.value = id
}

function removeConversation(id) {
  const index = conversations.value.findIndex((conversation) => conversation.id === id)
  if (index === -1) return

  conversations.value.splice(index, 1)
  if (activeId.value === id) {
    activeId.value = conversations.value[0]?.id ?? null
  }
  if (!conversations.value.length) createConversation()
  persist()
}

function clearConversation(id = activeId.value) {
  const conversation = conversations.value.find((item) => item.id === id)
  if (!conversation) return
  conversation.messages = []
  conversation.updatedAt = Date.now()
  persist()
}

function clearAllConversations() {
  conversations.value = []
  activeId.value = null
  createConversation()
  persist()
}

function renameConversation(id, title) {
  const conversation = conversations.value.find((item) => item.id === id)
  if (!conversation) return
  const next = String(title || '').trim()
  conversation.title = next || DEFAULT_TITLE
  persist()
}

/** 会话有内容变化时调用，刷新时间戳并落盘 */
function touchConversation(id) {
  const conversation = conversations.value.find((item) => item.id === id)
  if (!conversation) return
  conversation.updatedAt = Date.now()
  persist()
}

function ensureConversation() {
  if (activeConversation.value) return activeConversation.value
  return createConversation()
}

export function useConversations() {
  return {
    conversations,
    conversationItems,
    activeId,
    activeConversation,
    storageWarning,
    createConversation,
    selectConversation,
    removeConversation,
    clearConversation,
    clearAllConversations,
    renameConversation,
    touchConversation,
    ensureConversation,
  }
}
