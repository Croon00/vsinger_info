<script setup lang="ts">
// Lucide "panels-top-left" geometry; the three panels light up in turn on hover.
</script>
<template>
  <svg
    xmlns="http://www.w3.org/2000/svg"
    width="24"
    height="24"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="2"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    class="nav-icon nav-icon-multiview"
  >
    <path
      class="nav-icon-fill nav-icon-panel nav-icon-panel-top"
      stroke="none"
      d="M3 9V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v4Z"
    />
    <path
      class="nav-icon-fill nav-icon-panel nav-icon-panel-side"
      stroke="none"
      d="M9 9v12H5a2 2 0 0 1-2-2V9Z"
    />
    <path
      class="nav-icon-fill nav-icon-panel nav-icon-panel-main"
      stroke="none"
      d="M9 9h12v10a2 2 0 0 1-2 2H9Z"
    />
    <rect width="18" height="18" x="3" y="3" rx="2" />
    <path d="M3 9h18" />
    <path d="M9 21V9" />
  </svg>
</template>
