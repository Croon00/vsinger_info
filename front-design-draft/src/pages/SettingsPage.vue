<script setup lang="ts">
import { Monitor, Moon, Sun, Palette, AudioLines } from '@lucide/vue'
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card'
import { FieldGroup, Field, FieldTitle, FieldDescription } from '@/components/ui/field'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { theme, type Theme } from '@/composables/preferences'
</script>
<template>
  <div class="page-container settings-page page-enter">
    <div class="page-heading">
      <p class="eyebrow">MAKE YOURSELF AT HOME</p>
      <h1>나에게 편안한 공간.</h1>
      <p>음악을 만나는 화면도, 내 취향에 맞게.</p>
    </div>
    <Card>
      <CardHeader>
        <CardTitle>화면 테마</CardTitle>
        <CardDescription>기기 설정에 맞추거나 원하는 테마를 선택하세요.</CardDescription>
      </CardHeader>
      <CardContent>
        <FieldGroup>
          <Field>
            <FieldTitle id="theme-label" class="sr-only">테마 선택</FieldTitle>
            <ToggleGroup
              type="single"
              :model-value="theme"
              @update:model-value="
                (v) => {
                  if (v) theme = v as Theme
                }
              "
              variant="outline"
              :spacing="2"
              aria-labelledby="theme-label"
              class="theme-picker"
            >
              <ToggleGroupItem value="system">
                <Monitor />
                <span>시스템</span>
              </ToggleGroupItem>
              <ToggleGroupItem value="light">
                <Sun />
                <span>라이트</span>
              </ToggleGroupItem>
              <ToggleGroupItem value="dark">
                <Moon />
                <span>다크</span>
              </ToggleGroupItem>
            </ToggleGroup>
            <FieldDescription>선택한 설정은 이 브라우저에 저장됩니다.</FieldDescription>
          </Field>
        </FieldGroup>
      </CardContent>
    </Card>
    <div class="settings-note">
      <AudioLines class="size-5" />
      <p>
        더 편안한 음악 생활을 위한 설정을
        <br />
        차근차근 준비하고 있어요.
      </p>
    </div>
  </div>
</template>
