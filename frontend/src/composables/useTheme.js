import { computed, ref, watch } from 'vue'

const STORAGE_KEY = 'mingshu.theme'
export const THEME_MODES = ['light', 'dark', 'auto']

function readStored() {
  try {
    const value = localStorage.getItem(STORAGE_KEY)
    return THEME_MODES.includes(value) ? value : 'auto'
  } catch {
    return 'auto'
  }
}

const prefersDark = ref(false)
if (typeof window !== 'undefined' && window.matchMedia) {
  const query = window.matchMedia('(prefers-color-scheme: dark)')
  prefersDark.value = query.matches
  query.addEventListener?.('change', (event) => {
    prefersDark.value = event.matches
  })
}

const mode = ref(readStored())

const resolved = computed(() => {
  if (mode.value === 'auto') return prefersDark.value ? 'dark' : 'light'
  return mode.value
})

watch(
    resolved,
    (value) => {
      document.documentElement.dataset.theme = value
    },
    { immediate: true },
)

watch(
    mode,
    (value) => {
      document.documentElement.dataset.themeMode = value
      try {
        localStorage.setItem(STORAGE_KEY, value)
      } catch {
        /* 忽略写入失败（隐私模式） */
      }
    },
    { immediate: true },
)

export function useTheme() {
  function setMode(next) {
    if (THEME_MODES.includes(next)) mode.value = next
  }

  /** 在 亮 → 暗 → 跟随系统 之间循环 */
  function cycle() {
    const index = THEME_MODES.indexOf(mode.value)
    mode.value = THEME_MODES[(index + 1) % THEME_MODES.length]
  }

  const label = computed(() => ({ light: '亮色', dark: '暗色', auto: '跟随系统' }[mode.value]))

  return { mode, resolved, label, setMode, cycle }
}
