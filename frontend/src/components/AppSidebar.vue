<script setup>
import { computed } from 'vue'

import AppIcon from './AppIcon.vue'
import ThemeToggle from './ThemeToggle.vue'
import { useTheme } from '../composables/useTheme.js'

const props = defineProps({
  items: { type: Array, default: () => [] },
  activeId: { type: String, default: null },
  storageWarning: { type: Boolean, default: false },
  open: { type: Boolean, default: false },
})

const emit = defineEmits(['new', 'select', 'remove', 'clear-all', 'close'])

const { label: themeLabel } = useTheme()

/** 按「今天 / 昨天 / 日期」分组，保持传入顺序（新的在前） */
const groups = computed(() => {
  const result = []
  let current = null
  for (const item of props.items) {
    if (!current || current.label !== item.day) {
      current = { label: item.day, items: [] }
      result.push(current)
    }
    current.items.push(item)
  }
  return result
})

function onSelect(id) {
  emit('select', id)
  emit('close')
}
</script>

<template>
  <aside class="sidebar" :class="{ 'is-open': open }">
    <div class="brand">
      <div class="brand-logo">
        <AppIcon name="database" :size="17" :stroke="1.9"/>
      </div>
      <div class="brand-text">
        <strong>Data Agent</strong>
        <span>自然语言查询数仓</span>
      </div>
      <button class="icon-btn close-btn" type="button" aria-label="关闭侧栏" @click="emit('close')">
        <AppIcon name="x" :size="16"/>
      </button>
    </div>

    <div class="new-wrap">
      <button class="btn btn--primary new-btn" type="button" @click="emit('new'); emit('close')">
        <AppIcon name="plus" :size="15"/>
        新建对话
      </button>
    </div>

    <nav class="conv-list">
      <template v-for="group in groups" :key="group.label">
        <div class="conv-group">{{ group.label }}</div>
        <div
            v-for="item in group.items"
            :key="item.id"
            class="conv"
            :class="{ 'is-active': item.id === activeId }"
            role="button"
            tabindex="0"
            @click="onSelect(item.id)"
            @keydown.enter="onSelect(item.id)"
            @keydown.space.prevent="onSelect(item.id)"
        >
          <AppIcon class="conv-icon" name="message" :size="14"/>
          <span class="conv-body">
            <span class="conv-title">{{ item.title }}</span>
            <span class="conv-meta">
              <template v-if="item.messageCount">{{ item.messageCount }} 次提问 · </template>{{ item.clock }}
            </span>
          </span>
          <button
              class="conv-remove"
              type="button"
              :aria-label="`删除对话：${item.title}`"
              :title="`删除「${item.title}」`"
              @click.stop="emit('remove', item.id)"
          >
            <AppIcon name="trash" :size="13"/>
          </button>
        </div>
      </template>

      <p v-if="!items.length" class="conv-empty">还没有对话记录</p>
    </nav>

    <footer class="sidebar-foot">
      <ThemeToggle/>
      <span class="foot-label">{{ themeLabel }}</span>
      <button class="btn btn--sm btn--ghost clear-all" type="button" @click="emit('clear-all')">
        清空全部
      </button>
    </footer>

    <p v-if="storageWarning" class="storage-warning">
      <AppIcon name="alert" :size="13"/>
      浏览器本地存储不可用，对话记录无法保存。
    </p>
  </aside>
</template>

<style scoped>
.sidebar {
  display: flex;
  flex-direction: column;
  width: var(--sidebar-w);
  flex: none;
  height: 100%;
  border-right: 1px solid var(--border);
  background: var(--bg-elev);
}

/* ------------------------------------------------------------- 品牌 -- */
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  height: var(--topbar-h);
  padding: 0 12px 0 14px;
  flex: none;
}

.brand-logo {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 9px;
  background: linear-gradient(135deg, var(--accent), #7c5cff);
  color: #fff;
  flex: none;
}

.brand-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
  line-height: 1.25;
}

.brand-text strong {
  font-size: 13.5px;
  font-weight: 650;
}

.brand-text span {
  color: var(--text-mute);
  font-size: 11px;
}

.close-btn {
  display: none;
  margin-left: auto;
}

/* --------------------------------------------------------- 新建对话 -- */
.new-wrap {
  padding: 4px 12px 10px;
  flex: none;
}

.new-btn {
  width: 100%;
}

/* ----------------------------------------------------------- 列表 -- */
.conv-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 0 8px 12px;
}

.conv-group {
  padding: 12px 8px 5px;
  color: var(--text-mute);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.05em;
}

.conv {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 8px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background var(--dur-fast) var(--ease);
}

.conv:hover {
  background: var(--bg-hover);
}

.conv.is-active {
  background: var(--bg-active);
}

.conv-icon {
  flex: none;
  color: var(--text-mute);
}

.conv.is-active .conv-icon {
  color: var(--accent);
}

.conv-body {
  display: flex;
  flex-direction: column;
  min-width: 0;
  flex: 1;
  line-height: 1.35;
}

.conv-title {
  overflow: hidden;
  color: var(--text);
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.conv-meta {
  color: var(--text-mute);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}

.conv-remove {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  flex: none;
  border-radius: var(--radius-xs);
  color: var(--text-mute);
  opacity: 0;
  transition: opacity var(--dur-fast) var(--ease), background var(--dur-fast) var(--ease);
}

.conv:hover .conv-remove,
.conv-remove:focus-visible {
  opacity: 1;
}

.conv-remove:hover {
  background: var(--danger-soft);
  color: var(--danger);
}

.conv-empty {
  padding: 16px 8px;
  color: var(--text-mute);
  font-size: 12.5px;
}

/* ----------------------------------------------------------- 底部 -- */
.sidebar-foot {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: none;
  padding: 8px 12px;
  border-top: 1px solid var(--border);
}

.foot-label {
  color: var(--text-mute);
  font-size: 12px;
}

.clear-all {
  margin-left: auto;
}

.storage-warning {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: none;
  padding: 8px 14px 12px;
  color: var(--warning);
  font-size: 11.5px;
}

/* --------------------------------------------------------- 响应式 -- */
@media (max-width: 900px) {
  .sidebar {
    position: fixed;
    top: 0;
    left: 0;
    z-index: 40;
    transform: translateX(-100%);
    box-shadow: var(--shadow-3);
    transition: transform var(--dur) var(--ease);
  }

  .sidebar.is-open {
    transform: none;
  }

  .close-btn {
    display: inline-flex;
  }
}
</style>
