<script setup>
import { computed } from 'vue'

/**
 * 内联 SVG 图标集（零依赖）。
 * 统一 24×24 视框、currentColor 描边，随字号与主题自适应。
 */
const ICONS = {
  plus: ['M12 5v14M5 12h14'],
  send: ['M12 20V5', 'M5 11l7-7 7 7'],
  stop: ['M8 8h8v8H8z'],
  trash: ['M4 7h16', 'M9.5 7V4.5h5V7', 'M6.5 7l1 13h9l1-13', 'M10.5 11v6M13.5 11v6'],
  sun: ['M12 8.5a3.5 3.5 0 100 7 3.5 3.5 0 000-7', 'M12 3v1.8M12 19.2V21M3 12h1.8M19.2 12H21', 'M6.2 6.2l1.3 1.3M16.5 16.5l1.3 1.3M6.2 17.8l1.3-1.3M16.5 7.5l1.3-1.3'],
  moon: ['M20.5 14.3A8.7 8.7 0 019.7 3.5a8.5 8.5 0 1010.8 10.8z'],
  monitor: ['M3 5h18v11H3z', 'M8.5 20h7', 'M12 16v4'],
  check: ['M5 12.5l4.5 4.5L19 7'],
  x: ['M6 6l12 12M18 6L6 18'],
  alert: ['M12 4l8.5 15.5h-17z', 'M12 10v4.5', 'M12 17.2h.01'],
  copy: ['M9 9h10v10H9z', 'M5.5 15V5.5H15'],
  download: ['M12 4v10', 'M8 10.5l4 4 4-4', 'M5 20h14'],
  chevronDown: ['M6 9.5l6 6 6-6'],
  chevronRight: ['M9.5 6l6 6-6 6'],
  chevronLeft: ['M14.5 6l-6 6 6 6'],
  refresh: ['M4.5 12a7.5 7.5 0 0112.8-5.3', 'M19.5 12a7.5 7.5 0 01-12.8 5.3', 'M17.5 3v4h-4', 'M6.5 21v-4h4'],
  search: ['M11 4.5a6.5 6.5 0 100 13 6.5 6.5 0 000-13', 'M20 20l-4.6-4.6'],
  hash: ['M9.5 4L7.5 20', 'M16.5 4l-2 16', 'M4 9h16', 'M3 15h16'],
  columns: ['M4 5h16v14H4z', 'M4 10h16', 'M10 5v14'],
  metric: ['M5 20V12M11 20V5.5M17 20v-5.5', 'M3 20h18'],
  layers: ['M12 3.5l8 4.2-8 4.2-8-4.2 8-4.2z', 'M4 12.5l8 4.2 8-4.2', 'M4 16.8l8 4.2 8-4.2'],
  filter: ['M4 5h16l-6.2 7.3V19l-3.6 1.8v-8.5L4 5z'],
  calendar: ['M4 6.5h16V20H4z', 'M8.5 3.5v4M15.5 3.5v4', 'M4 11.5h16'],
  sparkles: ['M11 4l1.5 4.2L16.7 9.7l-4.2 1.5L11 15.4 9.5 11.2 5.3 9.7l4.2-1.5z', 'M18.5 14.5l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8z'],
  shield: ['M12 3.5l7 2.8v5.6c0 4.3-2.9 7.7-7 8.6-4.1-.9-7-4.3-7-8.6V6.3l7-2.8z', 'M9 12l2 2 4-4'],
  wrench: ['M4 20l7.5-7.5', 'M14.5 4.5l5 5-3 3-5-5 3-3z', 'M13.5 8.5l2 2'],
  play: ['M8.5 5.5l10 6.5-10 6.5z'],
  dot: ['M12 9.5a2.5 2.5 0 100 5 2.5 2.5 0 000-5'],
  database: ['M12 3.2c4.2 0 7.5 1.2 7.5 2.8S16.2 8.8 12 8.8 4.5 7.6 4.5 6 7.8 3.2 12 3.2z', 'M4.5 6v12c0 1.6 3.3 2.8 7.5 2.8s7.5-1.2 7.5-2.8V6', 'M4.5 12c0 1.6 3.3 2.8 7.5 2.8s7.5-1.2 7.5-2.8'],
  table: ['M4 5h16v14H4z', 'M4 10h16', 'M10.5 5v14'],
  clock: ['M12 4.2a7.8 7.8 0 100 15.6 7.8 7.8 0 000-15.6', 'M12 8.2V12l2.8 1.8'],
  history: ['M12 8v4.2l3 1.8', 'M3.6 12a8.4 8.4 0 108.4-8.4A8.4 8.4 0 004.7 6.8', 'M4 3v4h4'],
  message: ['M4 5.5h16v10.5H9.5L4.5 20V5.5z'],
  sort: ['M8 6v12', 'M5 15l3 3 3-3', 'M16 18V6', 'M13 9l3-3 3 3'],
  menu: ['M4 7h16M4 12h16M4 17h16'],
  panel: ['M4 5h16v14H4z', 'M10 5v14'],
  arrowDown: ['M12 5v14', 'M6 13l6 6 6-6'],
  arrowUp: ['M12 19V5', 'M6 11l6-6 6 6'],
}

const props = defineProps({
  name: { type: String, required: true },
  size: { type: [Number, String], default: 16 },
  stroke: { type: [Number, String], default: 1.7 },
})

const paths = computed(() => ICONS[props.name] || ICONS.dot)
</script>

<template>
  <svg
      :width="size"
      :height="size"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      :stroke-width="stroke"
      stroke-linecap="round"
      stroke-linejoin="round"
      aria-hidden="true"
      focusable="false"
  >
    <path v-for="(d, index) in paths" :key="index" :d="d"/>
  </svg>
</template>
