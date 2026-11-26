<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { disconnectIntegration, listIntegrations, type Connection } from '@/lib/integrations'

const enabled = ref(false)
const connections = ref<Connection[]>([])
const error = ref('')
const notice = ref('')

async function run(fn: () => Promise<void>) {
  error.value = ''
  try {
    await fn()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Something went wrong'
  }
}

onMounted(() => {
  // The OAuth callback redirects back with ?integration=slack|failed.
  const url = new URL(location.href)
  const result = url.searchParams.get('integration')
  if (result === 'slack' || result === 'failed') {
    notice.value = result === 'slack' ? 'Slack connected.' : 'Connecting Slack failed, try again.'
    url.searchParams.delete('integration')
    history.replaceState(history.state, '', url)
  }
  run(async () => {
    const s = (await listIntegrations()).slack
    enabled.value = s.enabled
    connections.value = s.connections
  })
})

const disconnect = (id: string) =>
  run(async () => {
    await disconnectIntegration(id)
    connections.value = connections.value.filter((c) => c.id !== id)
  })
</script>

<template>
  <section v-if="enabled || error || notice" class="slack">
    <h4 class="label">Slack</h4>
    <p v-if="notice" class="hint" role="status">{{ notice }}</p>
    <p v-if="error" class="err" role="alert">{{ error }}</p>
    <template v-if="enabled">
      <ul v-if="connections.length">
        <li v-for="c in connections" :key="c.id">
          <span>{{ c.workspace }}</span>
          <button
            class="btn disconnect"
            type="button"
            :aria-label="`Disconnect ${c.workspace}`"
            @click="disconnect(c.id)"
          >
            Disconnect
          </button>
        </li>
      </ul>
      <small v-if="connections.length" class="hint">Use /quiz &lt;subject&gt; in Slack</small>
      <a class="btn" href="/api/integrations/slack/connect">{{ connections.length ? 'Add another workspace' : 'Add to Slack' }}</a>
    </template>
  </section>
</template>

<style scoped>
.slack {
  display: flex;
  flex-direction: column;
  gap: var(--s4);
}
.hint {
  color: var(--mute);
}
.err {
  color: var(--bad);
  margin: 0;
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
