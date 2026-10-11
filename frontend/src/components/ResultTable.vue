<script setup>
import { computed, ref } from 'vue'

import AppIcon from './AppIcon.vue'
import { copyText, exportCsv, toTsv } from '../utils/export.js'
import { describeCell, estimateColumnWidth, isNumeric, rawText } from '../utils/format.js'

const props = defineProps({
  table: { type: Object, required: true },
})

const PAGE_SIZES = [
  { value: 20, label: '20 行/页' },
  { value: 50, label: '50 行/页' },
  { value: 100, label: '100 行/页' },
  { value: 0, label: '全部' },
]

const sortKey = ref(null)
const sortDir = ref(null)
const page = ref(1)
const pageSize = ref(20)
const copied = ref(false)
let copyTimer = null

const columns = computed(() => props.table.columns || [])
const totalRows = computed(() => (props.table.rows || []).length)

function compareValues(a, b) {
  if (a === b) return 0
  if (a === null || a === undefined) return -1
  if (b === null || b === undefined) return 1
  if (isNumeric(a) && isNumeric(b)) return Number(a) - Number(b)
  if (typeof a === 'boolean' && typeof b === 'boolean') return Number(a) - Number(b)
  return String(a).localeCompare(String(b), 'zh-CN', { numeric: true, sensitivity: 'base' })
}

const sortedRows = computed(() => {
  const rows = props.table.rows || []
  if (!sortKey.value || !sortDir.value) return rows
  const key = sortKey.value
  const direction = sortDir.value === 'asc' ? 1 : -1
  return [...rows].sort((a, b) => compareValues(a?.[key], b?.[key]) * direction)
})

const pageCount = computed(() =>
    pageSize.value ? Math.max(1, Math.ceil(totalRows.value / pageSize.value)) : 1,
)

const pagedRows = computed(() => {
  if (!pageSize.value) return sortedRows.value
  const start = (page.value - 1) * pageSize.value
  return sortedRows.value.slice(start, start + pageSize.value)
})

const rangeText = computed(() => {
  if (!totalRows.value) return '0 行'
  if (!pageSize.value) return `共 ${totalRows.value} 行`
  const start = (page.value - 1) * pageSize.value + 1
  const end = Math.min(page.value * pageSize.value, totalRows.value)
  return `${start}-${end} / 共 ${totalRows.value} 行`
})

/** 先把单元格渲染描述算好，避免模板里对每个单元格重复计算 */
const displayRows = computed(() =>
    pagedRows.value.map((row, rowIndex) => ({
      id: rowIndex,
      cells: columns.value.map((column) => {
        const value = row?.[column]
        const described = describeCell(value)
        return { column, kind: described.kind, text: described.text, raw: rawText(value) }
      }),
    })),
)

const columnWidth = (column) => `${estimateColumnWidth(column, props.table.rows || [])}px`

function toggleSort(column) {
  if (sortKey.value !== column) {
    sortKey.value = column
    sortDir.value = 'asc'
  } else if (sortDir.value === 'asc') {
    sortDir.value = 'desc'
  } else if (sortDir.value === 'desc') {
    sortKey.value = null
    sortDir.value = null
  } else {
    sortDir.value = 'asc'
  }
  page.value = 1
}

function changePage(next) {
  page.value = Math.min(Math.max(1, next), pageCount.value)
}

function changePageSize(value) {
  pageSize.value = Number(value)
  page.value = 1
}

async function onCopy() {
  const ok = await copyText(toTsv(columns.value, sortedRows.value))
  if (!ok) return
  copied.value = true
  clearTimeout(copyTimer)
  copyTimer = setTimeout(() => {
    copied.value = false
  }, 1600)
}

function onExport() {
  exportCsv(columns.value, sortedRows.value)
}

const ariaSort = (column) => {
  if (sortKey.value !== column || !sortDir.value) return 'none'
  return sortDir.value === 'asc' ? 'ascending' : 'descending'
}
</script>

<template>
  <section class="result">
    <header class="result-head">
      <div class="result-title">
        <AppIcon name="table" :size="14"/>
        <span>查询结果</span>
        <span class="chip">{{ totalRows }} 行</span>
        <span class="chip">{{ columns.length }} 列</span>
        <span v-if="table.truncated" class="chip chip--warn">
          <AppIcon name="alert" :size="11"/>
          已截断 · 上限 {{ table.rowLimit ?? '—' }} 行
        </span>
        <span v-if="sortKey" class="chip chip--accent">
          按 {{ sortKey }} {{ sortDir === 'asc' ? '升序' : '降序' }}
        </span>
      </div>
      <div class="result-actions">
        <button class="btn btn--sm" type="button" :disabled="!totalRows" @click="onCopy">
          <AppIcon :name="copied ? 'check' : 'copy'" :size="13"/>
          {{ copied ? '已复制' : '复制' }}
        </button>
        <button class="btn btn--sm" type="button" :disabled="!totalRows" @click="onExport">
          <AppIcon name="download" :size="13"/>
          导出 CSV
        </button>
      </div>
    </header>

    <div v-if="!totalRows" class="result-empty">
      <AppIcon name="search" :size="18"/>
      <p>SQL 执行成功，但没有匹配到任何数据行。</p>
    </div>

    <template v-else>
      <div class="table-scroll">
        <table class="data-table">
          <thead>
          <tr>
            <th
                v-for="column in columns"
                :key="column"
                :style="{ minWidth: columnWidth(column) }"
                :aria-sort="ariaSort(column)"
                scope="col"
            >
              <button class="th-inner" type="button" @click="toggleSort(column)">
                <span class="th-label">{{ column }}</span>
                <AppIcon
                    class="th-sort"
                    :class="{ 'is-active': sortKey === column }"
                    :name="sortKey === column && sortDir === 'desc' ? 'arrowDown' : sortKey === column ? 'arrowUp' : 'sort'"
                    :size="12"
                />
              </button>
            </th>
          </tr>
          </thead>
          <tbody>
          <tr v-for="row in displayRows" :key="row.id">
            <td
                v-for="cell in row.cells"
                :key="cell.column"
                :class="['cell', `is-${cell.kind}`]"
                :title="cell.raw"
            >
              {{ cell.text }}
            </td>
          </tr>
          </tbody>
        </table>
      </div>

      <footer v-if="pageSize && totalRows > pageSize" class="result-foot">
        <span class="range">{{ rangeText }}</span>
        <div class="pager">
          <button class="icon-btn" type="button" :disabled="page <= 1" title="上一页" @click="changePage(page - 1)">
            <AppIcon name="chevronLeft" :size="15"/>
          </button>
          <span class="page-num">{{ page }} / {{ pageCount }}</span>
          <button class="icon-btn" type="button" :disabled="page >= pageCount" title="下一页"
                  @click="changePage(page + 1)">
            <AppIcon name="chevronRight" :size="15"/>
          </button>
        </div>
        <select class="page-size" :value="pageSize" @change="changePageSize($event.target.value)">
          <option v-for="option in PAGE_SIZES" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>
      </footer>

      <p v-if="table.truncated" class="truncate-note">
        <AppIcon name="alert" :size="14"/>
        <span>
          服务端限制了单次返回行数（上限 {{ table.rowLimit ?? '—' }} 行），
          当前只是截断后的前 {{ totalRows }} 行，<strong>不是完整结果</strong>。
          需要全量数据请改用聚合，或在问题里缩小范围（例如加上时间区间）。
        </span>
      </p>
    </template>
  </section>
</template>

<style scoped>
.result {
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg-elev);
  overflow: hidden;
}

.result-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-sunken);
}

.result-title {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
  color: var(--text);
  font-size: 12.5px;
  font-weight: 600;
}

.chip--accent {
  background: var(--accent-soft);
  color: var(--accent);
}

.chip--warn {
  background: var(--warning-soft);
  color: var(--warning);
}

.result-actions {
  display: flex;
  gap: 6px;
  margin-left: auto;
}

/* ------------------------------------------------------------- 表格 -- */
.table-scroll {
  max-height: min(58vh, 520px);
  overflow: auto;
}

.data-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  font-size: 12.5px;
}

.data-table th {
  position: sticky;
  top: 0;
  z-index: 2;
  padding: 0;
  border-bottom: 1px solid var(--border-strong);
  background: var(--bg-elev);
  text-align: left;
  font-weight: 600;
  white-space: nowrap;
}

.th-inner {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 8px 12px;
  color: var(--text-dim);
  font-size: 12px;
  font-weight: 600;
}

.th-inner:hover {
  background: var(--bg-hover);
  color: var(--text);
}

.th-label {
  overflow: hidden;
  text-overflow: ellipsis;
}

.th-sort {
  flex: none;
  opacity: 0.35;
  transition: opacity var(--dur-fast) var(--ease);
}

.th-sort.is-active {
  color: var(--accent);
  opacity: 1;
}

.data-table td {
  max-width: 420px;
  padding: 7px 12px;
  border-bottom: 1px solid var(--border);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.data-table tbody tr:last-child td {
  border-bottom: none;
}

.data-table tbody tr:nth-child(even) {
  background: var(--bg-zebra);
}

.data-table tbody tr:hover td {
  background: var(--bg-hover);
}

.cell.is-number {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.cell.is-null {
  color: var(--text-mute);
  font-style: italic;
}

.cell.is-boolean {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-dim);
}

/* --------------------------------------------------- 空态与分页 -- */
.result-empty {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 22px 16px;
  color: var(--text-mute);
  font-size: 13px;
}

.result-foot {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  border-top: 1px solid var(--border);
  background: var(--bg-sunken);
  font-size: 12px;
  color: var(--text-dim);
}

.range {
  font-variant-numeric: tabular-nums;
}

.pager {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-left: auto;
}

.page-num {
  min-width: 54px;
  text-align: center;
  font-variant-numeric: tabular-nums;
}

.page-size {
  height: 28px;
  padding: 0 6px;
  border: 1px solid var(--border);
  border-radius: var(--radius-xs);
  background: var(--bg-elev);
  color: var(--text-dim);
  font-size: 12px;
}

/* --------------------------------------------------------- 截断提示 -- */
.truncate-note {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin: 0;
  padding: 10px 12px;
  border-top: 1px solid var(--border);
  background: var(--warning-soft);
  color: var(--warning);
  font-size: 12px;
  line-height: 1.65;
}

.truncate-note strong {
  font-weight: 650;
}

.truncate-note :deep(svg) {
  flex: none;
  margin-top: 2px;
}
</style>
