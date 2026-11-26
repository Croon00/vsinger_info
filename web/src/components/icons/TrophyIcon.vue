<script setup lang="ts">
// Lucide "trophy" geometry; the cup turns gold, hops and two sparkles pop on hover.
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
    class="nav-icon nav-icon-trophy"
  >
    <g class="nav-icon-trophy-cup">
      <path
        class="nav-icon-fill nav-icon-trophy-bowl"
        d="M6 9a6 6 0 0 0 12 0V3a1 1 0 0 0-1-1H7a1 1 0 0 0-1 1z"
      />
      <path d="M6.084 10H4.5A2.5 2.5 0 0 1 2 7.5V5a1 1 0 0 1 1-1h3" />
      <path d="M17.916 10H19.5A2.5 2.5 0 0 0 22 7.5V5a1 1 0 0 0-1-1h-3" />
      <path d="M10 14.66V17a1 1 0 0 1-1 1 2 2 0 0 0-2 2v2" />
      <path d="M14 14.66V17a1 1 0 0 0 1 1 2 2 0 0 1 2 2v2" />
    </g>
    <path d="M4 22h16" />
    <path
      class="nav-icon-trophy-spark nav-icon-trophy-spark-left"
      stroke-width="1.5"
      d="M1.5 1.5l1 1m0-1-1 1"
    />
    <path
      class="nav-icon-trophy-spark nav-icon-trophy-spark-right"
      stroke-width="1.5"
      d="M21.5 13.5l1 1m0-1-1 1"
    />
  </svg>
</template>
