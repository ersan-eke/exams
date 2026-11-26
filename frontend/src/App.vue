<script setup lang="ts">
import { RouterView, useRoute } from 'vue-router'
import AppFrame from '@/components/frame/AppFrame.vue'

const route = useRoute()
</script>

<template>
  <RouterView v-if="route.meta.focus" />
  <AppFrame v-else><RouterView /></AppFrame>
</template>
