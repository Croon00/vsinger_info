<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Search, X, ChevronLeft, ChevronRight } from '@lucide/vue'
import type { Live } from '@/api/types'
import { artistStatistics, filterAndSortSongs, type SongSort } from '@/lib/artist-statistics'
import { formatDate } from '@/lib/dates'
import { Button } from '@/components/ui/button'
import { Field, FieldGroup, FieldLabel } from '@/components/ui/field'
import { InputGroup, InputGroupAddon, InputGroupInput } from '@/components/ui/input-group'
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectGroup,
  SelectItem,
} from '@/components/ui/select'
import {
  Table,
  TableHeader,
  TableHead,
  TableBody,
  TableRow,
  TableCell,
} from '@/components/ui/table'
import {
  Pagination,
  PaginationContent,
  PaginationItem,
  PaginationEllipsis,
  PaginationPrevious,
  PaginationNext,
} from '@/components/ui/pagination'
import { Progress } from '@/components/ui/progress'
import ResourceState from '@/components/ResourceState.vue'

const props = defineProps<{ lives: Live[] }>()
const query = ref('')
const sort = ref<SongSort>('most')
const page = ref(1)
const artistPage = ref(1)
const pageSize = 10
const stats = computed(() => artistStatistics(props.lives))
const songs = computed(() => filterAndSortSongs(stats.value.songs, query.value, sort.value))
function paginate<T>(items: T[]): T[][] {
  return Array.from({ length: Math.ceil(items.length / pageSize) }, (_, index) =>
    items.slice(index * pageSize, (index + 1) * pageSize),
  )
}
const songPages = computed(() => paginate(songs.value))
const artistPages = computed(() => paginate(stats.value.artists))
watch(
  () => props.lives,
  () => {
    artistPage.value = 1
  },
)
watch([query, sort, () => props.lives], () => {
  page.value = 1
})
const number = (value: number) => value.toLocaleString('ko-KR')
const date = (value: string | null) =>
  value ? formatDate(value, { year: 'numeric', month: '2-digit', day: '2-digit' }) : '날짜 미등록'
</script>

<template>
  <div class="artist-statistics">
    <div class="statistics-columns">
      <section class="song-statistics" aria-labelledby="song-statistics-heading">
        <div class="section-heading">
          <h2 id="song-statistics-heading">부른 곡</h2>
          <span class="statistics-note">{{ number(stats.uniqueSongs) }}곡</span>
        </div>
        <form role="search" aria-label="부른 곡 검색" @submit.prevent>
          <FieldGroup class="statistics-toolbar">
            <Field>
              <FieldLabel for="statistics-search" class="sr-only">
                곡명 또는 원곡 아티스트
              </FieldLabel>
              <InputGroup>
                <InputGroupAddon><Search /></InputGroupAddon>
                <InputGroupInput
                  id="statistics-search"
                  v-model="query"
                  placeholder="곡명, 아티스트 검색"
                />
                <InputGroupAddon v-if="query" align="inline-end">
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    aria-label="통계 검색어 지우기"
                    @click="query = ''"
                  >
                    <X />
                  </Button>
                </InputGroupAddon>
              </InputGroup>
            </Field>
            <Field class="statistics-sort">
              <FieldLabel for="statistics-sort" class="sr-only">곡 정렬순서</FieldLabel>
              <Select v-model="sort">
                <SelectTrigger id="statistics-sort" class="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    <SelectItem value="most">많이 부른 순</SelectItem>
                    <SelectItem value="least">적게 부른 순</SelectItem>
                    <SelectItem value="recent">최근에 부른 순</SelectItem>
                    <SelectItem value="oldest">오래전에 부른 순</SelectItem>
                  </SelectGroup>
                </SelectContent>
              </Select>
            </Field>
          </FieldGroup>
        </form>
        <ResourceState
          :empty="!songs.length"
          :title="stats.uniqueSongs ? '검색 결과가 없습니다' : '아직 집계할 세트리스트가 없어요'"
          :description="
            stats.uniqueSongs
              ? '다른 곡명이나 아티스트로 검색해 보세요.'
              : '세트리스트가 등록되면 통계가 표시됩니다.'
          "
        >
          <div class="statistics-pages">
            <div
              v-for="(entries, pageIndex) in songPages"
              :key="pageIndex"
              class="statistics-page"
              :aria-hidden="pageIndex !== page - 1 ? true : undefined"
              :inert="pageIndex !== page - 1"
            >
              <Table class="statistics-table" aria-label="부른 곡 통계">
                <TableHeader>
                  <TableRow>
                    <TableHead class="w-12">순위</TableHead>
                    <TableHead>곡 / 아티스트</TableHead>
                    <TableHead class="statistics-date-column w-28">최근 부른 날</TableHead>
                    <TableHead class="w-18 text-right">횟수</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  <TableRow
                    v-for="song in entries"
                    :key="song.key"
                    :class="{ 'statistics-song-row': pageIndex === page - 1 }"
                  >
                    <TableCell>
                      <span class="statistics-rank">{{ song.rank }}</span>
                    </TableCell>
                    <TableCell class="min-w-0 whitespace-normal">
                      <div class="statistics-song-title">{{ song.title }}</div>
                      <div class="statistics-song-artist">{{ song.artist }}</div>
                      <div class="statistics-mobile-date">
                        최근 {{ date(song.lastPerformedAt) }}
                      </div>
                    </TableCell>
                    <TableCell class="statistics-date-column">
                      <time :datetime="song.lastPerformedAt ?? undefined" class="statistics-date">
                        {{ date(song.lastPerformedAt) }}
                      </time>
                    </TableCell>
                    <TableCell class="text-right">
                      <span class="statistics-count">
                        {{ number(song.count) }}
                        <small>회</small>
                      </span>
                    </TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </div>
          </div>
          <div class="statistics-pagination">
            <Pagination
              v-model:page="page"
              :total="songs.length"
              :items-per-page="pageSize"
              :sibling-count="0"
              show-edges
              aria-label="부른 곡 페이지"
              class="m-0 w-auto"
            >
              <PaginationContent v-slot="{ items }">
                <PaginationPrevious size="icon" aria-label="이전 페이지">
                  <ChevronLeft />
                </PaginationPrevious>
                <template v-for="(item, index) in items" :key="index">
                  <PaginationItem
                    v-if="item.type === 'page'"
                    :value="item.value"
                    :is-active="item.value === page"
                    :aria-label="`${item.value} 페이지`"
                  >
                    {{ item.value }}
                  </PaginationItem>
                  <PaginationEllipsis v-else />
                </template>
                <PaginationNext size="icon" aria-label="다음 페이지">
                  <ChevronRight />
                </PaginationNext>
              </PaginationContent>
            </Pagination>
          </div>
        </ResourceState>
      </section>

      <section class="original-artist-statistics" aria-labelledby="original-artist-heading">
        <div class="section-heading">
          <h2 id="original-artist-heading">원곡 아티스트</h2>
          <span class="statistics-note">{{ number(stats.uniqueArtists) }}명</span>
        </div>
        <ResourceState :empty="!stats.artists.length" title="아직 아티스트 기록이 없어요">
          <div class="statistics-pages">
            <div
              v-for="(entries, pageIndex) in artistPages"
              :key="pageIndex"
              class="statistics-page"
              :aria-hidden="pageIndex !== artistPage - 1 ? true : undefined"
              :inert="pageIndex !== artistPage - 1"
            >
              <ol class="statistics-artists" :start="pageIndex * pageSize + 1">
                <li v-for="(artist, index) in entries" :key="artist.key">
                  <span class="statistics-rank">{{ pageIndex * pageSize + index + 1 }}</span>
                  <div class="statistics-artist-body">
                    <div class="statistics-artist-heading">
                      <h3>{{ artist.name }}</h3>
                      <span class="statistics-artist-count">
                        {{ number(artist.count) }}회
                        <span>{{ artist.percentage.toFixed(1) }}%</span>
                      </span>
                    </div>
                    <Progress
                      :model-value="artist.percentage"
                      :max="100"
                      :aria-label="`${artist.name} 가창 비율`"
                      :aria-valuetext="`${artist.percentage.toFixed(1)}%, ${artist.count}회`"
                      class="h-1.5"
                    />
                  </div>
                </li>
              </ol>
            </div>
          </div>
          <div class="statistics-pagination">
            <Pagination
              v-model:page="artistPage"
              :total="stats.artists.length"
              :items-per-page="pageSize"
              :sibling-count="0"
              show-edges
              aria-label="원곡 아티스트 페이지"
              class="m-0 w-auto"
            >
              <PaginationContent v-slot="{ items }">
                <PaginationPrevious size="icon" aria-label="이전 페이지">
                  <ChevronLeft />
                </PaginationPrevious>
                <template v-for="(item, index) in items" :key="index">
                  <PaginationItem
                    v-if="item.type === 'page'"
                    :value="item.value"
                    :is-active="item.value === artistPage"
                    :aria-label="`${item.value} 페이지`"
                  >
                    {{ item.value }}
                  </PaginationItem>
                  <PaginationEllipsis v-else />
                </template>
                <PaginationNext size="icon" aria-label="다음 페이지">
                  <ChevronRight />
                </PaginationNext>
              </PaginationContent>
            </Pagination>
          </div>
        </ResourceState>
      </section>
    </div>
  </div>
</template>
