<script setup lang="ts">
import { ref, watch } from 'vue'
import SideMenu from './SideMenu.vue'
import SettingsPanel from './SettingsPanel.vue'
import Modal from '@/components/ui/Modal.vue'
import { useAccountStore } from '@/stores/account'

// OAuth callback lands on /?integration=...; open settings so the Slack card can show the result.
const settingsOpen = ref(new URLSearchParams(location.search).has('integration'))
const accountOpen = ref(false)
const account = useAccountStore()
const providerNames: Record<string, string> = { github: 'GitHub', google: 'Google' }
watch(
  () => account.loginFailed || account.loginDenied,
  (shown) => {
    if (shown) accountOpen.value = true
  },
  { immediate: true },
)
</script>

<template>
  <div class="frame">
    <header class="top">
      <span class="brand">Examen</span>
      <span class="icons">
        <button aria-label="Settings" @click="settingsOpen = true">⚙</button>
        <span class="account">
          <button aria-label="Account" @click="accountOpen = !accountOpen">◯</button>
          <span v-if="accountOpen" class="pop">
            <template v-if="account.user">
              Signed in as {{ account.user.name ?? account.user.email }}
              <button class="link" @click="account.logout()">Sign out</button>
            </template>
            <template v-else-if="account.providers.length">
              <span v-if="account.loginFailed" class="err">Sign-in failed, try again.</span>
              <span v-if="account.loginDenied" class="err">This account isn't invited. Ask the owner for access.</span>
              Sign in to keep uploads in your account:
              <a
                v-for="p in account.providers"
                :key="p"
                class="link"
                :href="`/api/auth/${p}/login`"
              >
                {{ providerNames[p] ?? p }}
              </a>
            </template>
            <template v-else>Sign-in isn't set up on this server</template>
          </span>
        </span>
      </span>
    </header>
    <div class="body">
      <SideMenu />
      <main class="main"><slot /></main>
    </div>
    <Modal :open="settingsOpen" @close="settingsOpen = false">
      <SettingsPanel @close="settingsOpen = false" />
    </Modal>
  </div>
</template>

<style scoped>
.frame {
  display: flex;
  flex-direction: column;
  min-height: 100%;
}
.top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 20px;
  border-bottom: 1px solid var(--line);
}
.brand {
  letter-spacing: 0.18em;
  text-transform: uppercase;
  font-size: var(--fs-sm);
}
.icons {
  display: flex;
  gap: var(--s4);
  color: var(--mute);
  font-size: var(--fs-lg);
}
.account {
  position: relative;
}
.err {
  display: block;
  color: var(--bad);
}
.pop {
  position: absolute;
  z-index: 1; /* .body is positioned and comes later, so it would sit on top and take the clicks */
  right: 0;
  top: 100%;
  margin-top: var(--s2);
  white-space: nowrap;
  background: var(--white);
  border: 1px solid var(--line);
  padding: var(--s2) var(--s3);
  font-size: var(--fs);
  color: var(--ink);
}
.link {
  margin-left: var(--s2);
  text-decoration: underline;
}
.body {
  position: relative;
  display: flex;
  flex: 1;
}
.main {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
