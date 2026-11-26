import './styles/tokens.css'

import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
import { useAccountStore } from './stores/account'
import { startSync } from './lib/sync'

const app = createApp(App)

const pinia = createPinia()
app.use(pinia)
app.use(router)

app.mount('#app')
const account = useAccountStore(pinia)
startSync(() => account.user !== null)
void account.load()
