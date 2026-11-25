<script setup lang="ts">
// Explore menu icon: a listener wearing cat-ear headphones. Drawn on Lucide's grid
// (24px, 2px currentColor strokes) so it sits with the other menu icons. The fills are
// transparent until the menu item is hovered, focused or pressed (see .explore-icon in style.css).
</script>
<template>
  <svg
    class="explore-icon"
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
  >
    <g class="explore-icon-ear explore-icon-ear-left">
      <path class="explore-icon-ear-shape" d="M5.3 7.9 4.8 2.6l4.6 2.5Z" />
      <path class="explore-icon-ear-inner" stroke="none" d="m5.9 6.6-.3-2.7 2.4 1.3Z" />
    </g>
    <g class="explore-icon-ear explore-icon-ear-right">
      <path class="explore-icon-ear-shape" d="m18.7 7.9.5-5.3-4.6 2.5Z" />
      <path class="explore-icon-ear-inner" stroke="none" d="m18.1 6.6.3-2.7-2.4 1.3Z" />
    </g>
    <path d="M4.5 11a7.5 7.5 0 0 1 15 0" />
    <circle class="explore-icon-face" cx="12" cy="12.5" r="4" />
    <rect class="explore-icon-cup" x="3" y="10" width="3" height="5.5" rx="1.5" />
    <rect class="explore-icon-cup" x="18" y="10" width="3" height="5.5" rx="1.5" />
    <path d="M6.5 22c.7-2.4 2.9-3.5 5.5-3.5s4.8 1.1 5.5 3.5" />
  </svg>
</template>
