<script setup lang="ts">
import LiveApp from './LiveApp.vue'
import PracticePrototype from './PracticePrototype.vue'
const live=new URLSearchParams(location.search).get('mode')==='live'
</script>
<template><LiveApp v-if="live" /><PracticePrototype v-else /></template>
