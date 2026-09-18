<script setup lang="ts">
import { ref } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { api } from '@/api/client'
import PageHeader from '@/components/PageHeader.vue'
import StatusPill from '@/components/StatusPill.vue'

const discordUserId = ref('')
const health = useQuery({ queryKey: ['health'], queryFn: api.health })

function connectGoogle(): void {
  if (discordUserId.value.trim()) window.location.href = api.google.connectUrl(discordUserId.value.trim())
}
</script>

<template>
  <div class="page">
    <PageHeader eyebrow="CONNECTIONS / 05" title="연동 설정" description="외부 서비스 연결 상태와 API 기능 준비 여부를 확인합니다." />
    <section class="settings-grid">
      <article class="panel integration-card">
        <div class="integration-card__icon">G</div>
        <div class="integration-card__body">
          <div><h2>Google Calendar</h2><StatusPill label="사용자 연결 필요" tone="amber" /></div>
          <p>라이브 일정과 티켓 마감일을 개인 캘린더에 등록합니다.</p>
          <label>Discord 사용자 ID<UInput v-model="discordUserId" inputmode="numeric" placeholder="123456789012345678" /></label>
          <UButton class="button button--primary" :disabled="!discordUserId.trim()" @click="connectGoogle">Google 계정 연결</UButton>
        </div>
      </article>
      <article class="panel integration-card">
        <div class="integration-card__icon integration-card__icon--discord">D</div>
        <div class="integration-card__body">
          <div><h2>Discord 라우트</h2><StatusPill label="웹 API 준비 중" tone="muted" /></div>
          <p>봇의 slash command에서는 설정할 수 있지만, 웹 관리 API는 아직 제공되지 않습니다.</p>
          <code>/route_add · /route_list · /route_delete · /route_test</code>
        </div>
      </article>
      <article class="panel integration-card">
        <div class="integration-card__icon integration-card__icon--api">A</div>
        <div class="integration-card__body">
          <div><h2>FastAPI</h2><StatusPill :label="health.isError.value ? '연결 실패' : '정상 연결'" :tone="health.isError.value ? 'amber' : 'green'" /></div>
          <p>아티스트, 소스, 일정 후보와 Wiki Studio의 유일한 데이터 경계입니다.</p>
          <UButton class="button button--ghost" @click="health.refetch()">상태 다시 확인</UButton>
        </div>
      </article>
    </section>
    <section class="safety-banner">
      <div class="safety-banner__mark">!</div>
      <div><p class="eyebrow">HUMAN IN THE LOOP</p><h2>결제와 응모의 마지막 단계는 사람이 수행합니다.</h2><p>이 콘솔은 일정과 링크를 정리하지만 CAPTCHA 우회, 자동 구매, 자동 응모 제출은 실행하지 않습니다.</p></div>
    </section>
  </div>
</template>
