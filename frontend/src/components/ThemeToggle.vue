<script setup>
import { computed } from 'vue'

import AppIcon from './AppIcon.vue'
import { useTheme } from '../composables/useTheme.js'

const { mode, label, cycle } = useTheme()

const icon = computed(() => ({ light: 'sun', dark: 'moon', auto: 'monitor' }[mode.value] || 'monitor'))
</script>

<template>
  <button
      class="theme-toggle icon-btn"
      type="button"
      :title="`主题：${label}（点击切换）`"
      :aria-label="`主题：${label}`"
      @click="cycle"
  >
    <AppIcon :name="icon" :size="17"/>
  </button>
</template>

<style scoped>
.theme-toggle {
  width: 32px;
  height: 32px;
}
</style>
