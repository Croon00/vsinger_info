<script setup lang="ts">
// Lucide "music" geometry; the two notes hop in turn and color in on hover.
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
    class="nav-icon nav-icon-music"
  >
    <g class="nav-icon-music-note nav-icon-music-note-left">
      <path d="M9 18V5" />
      <circle class="nav-icon-fill nav-icon-music-head-left" cx="6" cy="18" r="3" />
    </g>
    <path class="nav-icon-music-beam" d="m9 5 12-2" />
    <g class="nav-icon-music-note nav-icon-music-note-right">
      <path d="M21 3v13" />
      <circle class="nav-icon-fill nav-icon-music-head-right" cx="18" cy="16" r="3" />
    </g>
  </svg>
</template>
