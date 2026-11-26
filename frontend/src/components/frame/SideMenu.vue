<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'

const KEY = 'examen.menuCollapsed'

function read(): boolean {
  try {
    return localStorage.getItem(KEY) === '1'
  } catch {
    return false
  }
}

const stored = ref(read())
watch(stored, (v) => {
  try {
    localStorage.setItem(KEY, v ? '1' : '0')
  } catch {
    // storage unavailable
  }
})

// below 760 px the menu is a rail that opens over the page; that state is local,
// so the stored (wide-screen) preference is untouched
const mq = typeof window !== 'undefined' && window.matchMedia ? window.matchMedia('(max-width: 759px)') : null
const narrow = ref(mq?.matches ?? false)
const narrowOpen = ref(false)
const onMedia = (e: MediaQueryListEvent) => {
  narrow.value = e.matches
  narrowOpen.value = false
}
mq?.addEventListener('change', onMedia)
onBeforeUnmount(() => mq?.removeEventListener('change', onMedia))

const collapsed = computed(() => (narrow.value ? !narrowOpen.value : stored.value))
function toggle() {
  if (narrow.value) narrowOpen.value = !narrowOpen.value
  else stored.value = !stored.value
}

const groups = [
  [
    { to: '/', label: 'New exam', short: 'N' },
    { to: '/my-exams', label: 'My exams', short: 'M' },
    { to: '/statistics', label: 'Statistics', short: 'S' },
  ],
  [
    { to: '/practice', label: 'Practice', short: 'P' },
    { to: '/quizzes', label: 'Quizzes', short: 'Q' },
    { to: '/ask', label: 'Ask', short: 'A' },
  ],
]
</script>

<template>
  <nav class="menu" :class="{ collapsed, narrow }" aria-label="Main">
    <div class="head">
      <span v-if="!collapsed" class="label">Menu</span>
      <button
        class="toggle"
        :aria-label="collapsed ? 'Expand menu' : 'Collapse menu'"
        @click="toggle"
      >
        {{ collapsed ? '»' : '«' }}
      </button>
    </div>
    <template v-for="(group, i) in groups" :key="i">
      <div v-if="i > 0" class="sep"></div>
      <RouterLink
        v-for="item in group"
        :key="item.to"
        :to="item.to"
        class="item"
        :title="item.label"
        active-class="on"
        exact-active-class="on"
        @click="narrowOpen = false"
      >
        <span v-if="collapsed" class="short">{{ item.short }}</span>
        <span v-else class="text">{{ item.label }}</span>
      </RouterLink>
    </template>
  </nav>
</template>

<style scoped>
.menu {
  width: 190px;
  border-right: 1px solid var(--line);
  padding: 14px 0;
  flex-shrink: 0;
}
.menu.collapsed {
  width: 52px;
}
.menu.narrow:not(.collapsed) {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
  z-index: 2;
  background: var(--white);
}
.head {
  display: flex;
  justify-content: space-between;
  padding: 2px 18px 12px;
  color: var(--mute);
}
.collapsed .head {
  justify-content: center;
  padding: 2px 0 12px;
}
.item {
  display: block;
  padding: 7px 18px;
  color: var(--mute);
  text-decoration: none;
}
.collapsed .item {
  text-align: center;
  padding: 7px 0;
}
.item.on {
  color: var(--ink);
  background: var(--soft);
  box-shadow: inset 2px 0 0 var(--ink);
}
.sep {
  height: 1px;
  background: var(--line);
  margin: 10px 18px;
}
</style>
