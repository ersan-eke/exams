<script setup lang="ts">
import { useSettingsStore } from '@/stores/settings'
import { useAccountStore } from '@/stores/account'
import McpTokens from './McpTokens.vue'
import SlackIntegration from './SlackIntegration.vue'
import NotionIntegration from './NotionIntegration.vue'
import { computed } from 'vue'
import type { AnswerMode, Provider } from '@/types/attempt'

defineEmits<{ close: [] }>()
const settings = useSettingsStore()
const account = useAccountStore()
const modes: { value: AnswerMode; label: string }[] = [
  { value: 'type', label: 'Type' },
  { value: 'draw', label: 'Draw' },
]

const providers: { value: Provider; label: string; keyAt: string }[] = [
  { value: 'anthropic', label: 'Anthropic', keyAt: 'console.anthropic.com' },
  { value: 'google', label: 'Google AI Studio', keyAt: 'aistudio.google.com' },
  { value: 'openrouter', label: 'OpenRouter', keyAt: 'openrouter.ai' },
]
const modelOptions: Record<'anthropic' | 'google', { value: string; label: string }[]> = {
  anthropic: [
    { value: 'claude-sonnet-5-5', label: 'Sonnet 5.5 (best)' },
    { value: 'claude-haiku-5-5', label: 'Haiku 5.5 (about 20× cheaper, for testing)' },
  ],
  google: [
    { value: 'gemini-flash-latest', label: 'Gemini Flash (free tier)' },
    { value: 'gemini-pro-latest', label: 'Gemini Pro' },
  ],
}
const keyAt = computed(() => providers.find((p) => p.value === settings.provider)!.keyAt)
</script>

<template>
  <div class="settings">
    <h3 class="label">Settings</h3>
    <fieldset>
      <legend>Default answer mode</legend>
      <label v-for="m in modes" :key="m.value">
        <input v-model="settings.defaultAnswerMode" type="radio" name="mode" :value="m.value" />
        {{ m.label }}
      </label>
    </fieldset>
    <label class="row">
      <input v-model="settings.attendanceDefault" type="checkbox" />
      Attendance check on by default
    </label>
    <fieldset>
      <legend>LLM provider</legend>
      <label v-for="p in providers" :key="p.value">
        <input v-model="settings.provider" type="radio" name="provider" :value="p.value" />
        {{ p.label }}
      </label>
    </fieldset>
    <label class="field">
      API key
      <input v-model="settings.keys[settings.provider]" type="password" autocomplete="off" />
      <small class="hint">Stays on this device, sent only with grading requests. Get one at {{ keyAt }}.</small>
      <small v-if="settings.provider === 'google'" class="hint">Free tiers may use what you send to improve their models.</small>
    </label>
    <label class="field">
      Model
      <select v-if="settings.provider !== 'openrouter'" v-model="settings.models[settings.provider]">
        <option v-for="m in modelOptions[settings.provider]" :key="m.value" :value="m.value">
          {{ m.label }}
        </option>
      </select>
      <template v-else>
        <input v-model="settings.models.openrouter" type="text" />
        <small class="hint">Pick a model that reads images</small>
      </template>
    </label>
    <McpTokens v-if="account.user" />
    <SlackIntegration v-if="account.user" />
    <NotionIntegration v-if="account.user" />
    <button class="btn" @click="$emit('close')">Close</button>
  </div>
</template>

<style scoped>
.settings {
  display: flex;
  flex-direction: column;
  gap: var(--s4);
}
fieldset {
  border: 0;
  padding: 0;
  margin: 0;
  display: flex;
  gap: var(--s4);
  align-items: center;
}
legend {
  float: left;
  margin-right: var(--s4);
  color: var(--mute);
  padding: 0;
}
.row {
  display: flex;
  gap: var(--s2);
  align-items: center;
}
.field {
  display: flex;
  flex-direction: column;
  gap: var(--s2);
}
.hint {
  color: var(--mute);
}
.btn {
  align-self: flex-start;
  padding: 7px 16px;
  border: 1px solid var(--ink);
}
</style>
