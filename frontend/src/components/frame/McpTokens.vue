<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { createToken, listTokens, revokeToken, type AccessToken } from '@/lib/tokens'

const tokens = ref<AccessToken[]>([])
const name = ref('')
const fresh = ref<{ id: string; token: string } | null>(null)
const error = ref('')

const command = computed(
  () =>
    `claude mcp add --transport http exam-sim ${location.origin}/mcp --header "Authorization: Bearer ${fresh.value?.token}"`,
)

async function run(fn: () => Promise<void>) {
  error.value = ''
  try {
    await fn()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Something went wrong'
  }
}

const refresh = async () => {
  tokens.value = await listTokens()
}
onMounted(() => run(refresh))

const create = () =>
  run(async () => {
    fresh.value = null
    fresh.value = await createToken(name.value)
    name.value = ''
    await refresh()
  })
const revoke = (id: string) =>
  run(async () => {
    await revokeToken(id)
    tokens.value = tokens.value.filter((t) => t.id !== id)
    if (fresh.value?.id === id) fresh.value = null
  })
const copy = () => run(() => navigator.clipboard.writeText(fresh.value!.token))
const lastUsed = (t: AccessToken) =>
  t.lastUsedAt === null ? 'never' : new Date(t.lastUsedAt).toLocaleDateString()
</script>

<template>
  <section class="mcp">
    <h4 class="label">MCP access (Claude Code / Desktop)</h4>
    <form class="create" @submit.prevent="create">
      <label class="field">
        Token name
        <input v-model="name" type="text" maxlength="100" required placeholder="e.g. laptop" />
      </label>
      <button class="btn" type="submit">Create</button>
    </form>
    <p v-if="error" class="err" role="alert">{{ error }}</p>
    <div v-if="fresh" class="fresh">
      <label class="field">
        New token
        <input :value="fresh.token" type="text" readonly />
      </label>
      <button class="btn copy" type="button" @click="copy">Copy</button>
      <code>{{ command }}</code>
      <small class="hint">Shown once. Revoke it here if it leaks.</small>
    </div>
    <ul v-if="tokens.length">
      <li v-for="t in tokens" :key="t.id">
        <span>{{ t.name }}</span>
        <small class="hint">last used: {{ lastUsed(t) }}</small>
        <button
          class="btn revoke"
          type="button"
          :aria-label="`Revoke ${t.name}`"
          @click="revoke(t.id)"
        >
          Revoke
        </button>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.mcp {
  display: flex;
  flex-direction: column;
  gap: var(--s4);
}
.create {
  display: flex;
  gap: var(--s4);
  align-items: flex-end;
}
.field,
.fresh {
  display: flex;
  flex-direction: column;
  gap: var(--s2);
}
.hint {
  color: var(--mute);
}
.err {
  color: var(--bad);
  margin: 0;
}
code {
  word-break: break-all;
}
ul {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: var(--s2);
}
li {
  display: flex;
  gap: var(--s4);
  align-items: center;
}
.btn {
  align-self: flex-start;
  padding: 7px 16px;
  border: 1px solid var(--ink);
}
</style>
