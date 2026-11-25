<script setup lang="ts">
// Lucide "calendar-days" geometry; the page tilts, rings bounce and the header/dates color in.
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
    class="nav-icon nav-icon-calendar"
  >
    <g class="nav-icon-calendar-page">
      <path
        class="nav-icon-fill nav-icon-calendar-header"
        stroke="none"
        d="M3 9V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v4Z"
      />
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <path d="M3 9h18" />
      <path class="nav-icon-calendar-date nav-icon-calendar-date-a" d="M8 13h.01" />
      <path class="nav-icon-calendar-date nav-icon-calendar-date-b" d="M12 13h.01" />
      <path class="nav-icon-calendar-date nav-icon-calendar-date-a" d="M16 13h.01" />
      <path class="nav-icon-calendar-date nav-icon-calendar-date-b" d="M8 17h.01" />
      <path class="nav-icon-calendar-date nav-icon-calendar-date-a" d="M12 17h.01" />
      <path class="nav-icon-calendar-date nav-icon-calendar-date-b" d="M16 17h.01" />
    </g>
    <g class="nav-icon-calendar-rings">
      <path d="M8 2v3" />
      <path d="M16 2v3" />
    </g>
  </svg>
</template>
