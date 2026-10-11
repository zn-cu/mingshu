<script setup>
import AppIcon from './AppIcon.vue'

defineProps({
  samples: { type: Array, default: () => [] },
})

const emit = defineEmits(['pick'])
</script>

<template>
  <div class="empty">
    <div class="hero">
      <div class="logo">
        <AppIcon name="database" :size="26" :stroke="1.6"/>
      </div>
      <h2>用一句话问你的数据仓库</h2>
      <p class="lead">
        系统会抽取关键词、向量召回字段与指标、筛选相关表，再生成 SQL 并在数仓执行，
        全过程以执行时间线的形式实时展示。
      </p>
    </div>

    <div v-if="samples.length" class="samples">
      <div class="samples-title">可以这样问</div>
      <div class="sample-grid">
        <button
            v-for="sample in samples"
            :key="sample"
            type="button"
            class="sample"
            @click="emit('pick', sample)"
        >
          <AppIcon name="sparkles" :size="15"/>
          <span>{{ sample }}</span>
          <AppIcon class="sample-arrow" name="chevronRight" :size="14"/>
        </button>
      </div>
    </div>

    <p class="footnote">
      每次提问都是独立的一次图执行（后端暂无多轮上下文），对话记录仅保存在本机浏览器。
    </p>
  </div>
</template>

<style scoped>
.empty {
  max-width: 720px;
  margin: 0 auto;
  padding: clamp(24px, 7vh, 72px) 4px 8px;
  animation: da-fade-up var(--dur) var(--ease) both;
}

.hero {
  text-align: center;
}

.logo {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 54px;
  height: 54px;
  margin-bottom: 18px;
  border-radius: var(--radius-lg);
  background: linear-gradient(135deg, var(--accent), #7c5cff);
  color: #fff;
  box-shadow: 0 8px 24px var(--accent-ring);
}

h2 {
  font-size: 22px;
  font-weight: 650;
  letter-spacing: -0.01em;
}

.lead {
  margin: 10px auto 0;
  max-width: 560px;
  color: var(--text-dim);
  font-size: 13.5px;
  line-height: 1.75;
}

.samples {
  margin-top: 32px;
}

.samples-title {
  margin-bottom: 10px;
  color: var(--text-mute);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.06em;
}

.sample-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 10px;
}

.sample {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg-elev);
  color: var(--text-dim);
  font-size: 13px;
  text-align: left;
  transition: border-color var(--dur-fast) var(--ease),
  transform var(--dur-fast) var(--ease),
  box-shadow var(--dur-fast) var(--ease),
  color var(--dur-fast) var(--ease);
}

.sample span {
  flex: 1;
}

.sample :deep(svg:first-child) {
  color: var(--accent);
  flex: none;
}

.sample-arrow {
  color: var(--text-mute);
  opacity: 0;
  transform: translateX(-3px);
  transition: opacity var(--dur-fast) var(--ease), transform var(--dur-fast) var(--ease);
}

.sample:hover {
  border-color: var(--accent);
  color: var(--text);
  box-shadow: var(--shadow-1);
  transform: translateY(-1px);
}

.sample:hover .sample-arrow {
  opacity: 1;
  transform: none;
}

.sample:active {
  transform: translateY(0) scale(0.995);
}

.footnote {
  margin-top: 26px;
  color: var(--text-mute);
  font-size: 12px;
  text-align: center;
}
</style>
