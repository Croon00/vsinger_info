<script setup lang="ts">
import {
  Inbox,
  Users,
  Music2,
  Radio,
  CalendarDays,
  Disc3,
  Mic2,
  History,
  Settings2,
  AudioLines,
} from '@lucide/vue'
import {
  Sidebar,
  SidebarContent,
  SidebarHeader,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuItem,
  SidebarMenuButton,
  useSidebar,
} from '@/components/ui/sidebar'
defineProps<{ active: string; connected: boolean; initialized: boolean }>()
const emit = defineEmits<{ navigate: [name: string] }>()
const { setOpenMobile } = useSidebar()
function go(name: string) {
  emit('navigate', name)
  setOpenMobile(false)
}
const items = [
  { name: 'artists', label: '아티스트', icon: Users },
  { name: 'songs', label: '곡', icon: Music2 },
  { name: 'live_archives', label: '라이브 · 세트리스트', icon: Radio },
  { name: 'concerts', label: '공연', icon: CalendarDays },
  { name: 'albums', label: '앨범 · 음원', icon: Disc3 },
  { name: 'covers', label: '커버', icon: Mic2 },
]
</script>
<template>
  <Sidebar>
    <SidebarHeader class="px-5 py-6"
      ><div class="flex items-center gap-2.5">
        <AudioLines class="size-5" /><span class="font-semibold tracking-tight"
          >schedule_music</span
        >
      </div>
      <p class="pl-7.5 text-xs text-muted-foreground">
        카탈로그 관리자
      </p></SidebarHeader
    >
    <SidebarContent>
      <SidebarGroup
        ><SidebarMenu
          ><SidebarMenuItem
            ><SidebarMenuButton
              :is-active="active === 'review'"
              @click="go('review')"
              ><Inbox /><span>검수함</span></SidebarMenuButton
            ></SidebarMenuItem
          ></SidebarMenu
        ></SidebarGroup
      >
      <SidebarGroup
        ><SidebarGroupLabel>카탈로그</SidebarGroupLabel
        ><SidebarMenu
          ><SidebarMenuItem v-for="item in items" :key="item.name"
            ><SidebarMenuButton
              :is-active="active === item.name"
              @click="go(item.name)"
              ><component :is="item.icon" /><span>{{
                item.label
              }}</span></SidebarMenuButton
            ></SidebarMenuItem
          ></SidebarMenu
        ></SidebarGroup
      >
      <SidebarGroup
        ><SidebarGroupLabel>작업 공간</SidebarGroupLabel
        ><SidebarMenu
          ><SidebarMenuItem
            ><SidebarMenuButton
              :is-active="active === 'history'"
              @click="go('history')"
              ><History /><span>반영 이력</span></SidebarMenuButton
            ></SidebarMenuItem
          ><SidebarMenuItem
            ><SidebarMenuButton
              :is-active="active === 'settings'"
              @click="go('settings')"
              ><Settings2 /><span>설정 · 백업</span></SidebarMenuButton
            ></SidebarMenuItem
          ></SidebarMenu
        ></SidebarGroup
      >
    </SidebarContent>
    <SidebarFooter class="p-5"
      ><div class="flex items-center gap-2 text-xs">
        <span
          :class="connected ? 'bg-foreground' : 'bg-muted-foreground'"
          class="size-1.5 rounded-full"
        />{{ connected ? '새 카탈로그 연결됨' : 'DB 연결 확인 필요' }}
      </div>
      <p class="ml-3.5 text-xs text-muted-foreground">
        {{ initialized ? '카탈로그 운영 중' : '초기 데이터 검수 단계' }}
      </p></SidebarFooter
    >
  </Sidebar>
</template>
