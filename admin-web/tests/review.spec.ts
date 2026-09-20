import { test, expect } from '@playwright/test'
test('local review workflow, dependency selection, keyboard and responsive layout', async ({
  page,
}, testInfo) => {
  const errors: string[] = []
  page.on('pageerror', (e) => errors.push(e.message))
  await page.goto('/')
  await expect(page.getByText('첫 검수 묶음을 만들어 주세요')).toBeVisible()
  await page.screenshot({
    path: testInfo.outputPath('desktop-empty.png'),
    fullPage: true,
  })
  await page.getByRole('button', { name: '새 검수 묶음' }).first().click()
  await page.getByLabel('묶음 이름').fill('브라우저 검수 테스트')
  await page.getByRole('button', { name: '만들기', exact: true }).click()
  await expect(
    page.getByText('JSON을 가져오거나 자료를 추가하세요.'),
  ).toBeVisible()
  await page.getByRole('button', { name: '추가', exact: true }).click()
  await page.getByLabel('주소용 이름').fill('browser-test')
  await page.getByLabel('원어 이름', { exact: false }).fill('ブラウザ検証')
  await page.getByLabel('한국어 이름').fill('브라우저 검증')
  await page.getByLabel('상징색', { exact: true }).fill('#6B8BC8')
  await expect(page.getByRole('img', { name: '상징색 #6B8BC8' })).toBeVisible()
  await expect(page.getByLabel('라이트 일정 미리보기')).toContainText('ブラウザ検証 공연')
  await expect(page.getByLabel('다크 일정 미리보기')).toBeVisible()
  await page.getByLabel('상징색', { exact: true }).fill('#bad')
  await expect(page.getByLabel('상징색', { exact: true })).toHaveAttribute('aria-invalid', 'true')
  await page.getByLabel('상징색', { exact: true }).fill('#6B8BC8')
  await page.route('https://preview.test/**', async route => {
    if (route.request().url().includes('broken')) return route.fulfill({ status: 404, body: '' })
    return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="80" height="80"><rect width="80" height="80" fill="#6B8BC8"/></svg>' })
  })
  await page.getByLabel('프로필 이미지 주소', { exact: true }).fill('https://preview.test/avatar.svg')
  await expect(page.getByAltText('ブラウザ検証 프로필 미리보기')).toBeVisible()
  await page.getByLabel('프로필 이미지 주소', { exact: true }).fill('https://preview.test/broken.svg')
  await expect(page.getByText('이미지를 불러올 수 없습니다. 주소를 확인하세요.')).toBeVisible()
  await page.getByLabel('프로필 이미지 주소', { exact: true }).fill('https://preview.test/recovered.svg')
  await expect(page.getByAltText('ブラウザ検証 프로필 미리보기')).toBeVisible()
  await page.getByLabel('라이트 일정 미리보기').scrollIntoViewIfNeeded()
  await page.screenshot({ path: testInfo.outputPath('artist-appearance.png'), fullPage: true })
  await page.getByLabel('활동 형태').click()
  await page.getByRole('option', { name: '개인', exact: true }).click()
  await page.getByRole('button', { name: '초안 추가' }).click()
  await expect(
    page.getByRole('heading', { name: 'ブラウザ検証' }),
  ).toBeVisible()
  await page.getByRole('button', { name: '승인', exact: true }).click()
  await expect(page.getByRole('button', { name: '다시 검수' })).toBeVisible()
  await expect(
    page.getByRole('button', { name: '반영 미리보기' }),
  ).toBeEnabled()
  await page.getByLabel('한국어 이름').fill('이름 수정')
  await expect(page.getByRole('button', { name: '초안 저장' })).toBeVisible()
  await page.getByRole('button', { name: '초안 저장' }).click()
  await expect(
    page.getByRole('button', { name: '승인', exact: true }),
  ).toBeVisible()
  await page.getByRole('tab', { name: '원본 · 변경' }).click()
  await expect(page.getByRole('heading', { name: '입력 원본' })).toBeVisible()
  await page.getByRole('tab', { name: '정보', exact: true }).click()
  await page.screenshot({
    path: testInfo.outputPath('desktop-review.png'),
    fullPage: true,
  })
  await page.getByRole('button', { name: '추가', exact: true }).click()
  await page.getByLabel('자료 종류').click()
  await page.getByRole('option', { name: /별칭/ }).click()
  await page.getByRole('dialog').getByRole('button', { name: '아티스트 필수', exact: true }).click()
  await page.getByRole('button', { name: /ブラウザ検証.*초안/ }).click()
  await expect(
    page
      .getByRole('dialog')
      .getByRole('button', { name: '아티스트 필수', exact: true }),
  ).toHaveText('ブラウザ検証')
  await page.getByLabel('검색용 다른 이름').fill('browser alias')
  await page.getByRole('button', { name: '초안 추가' }).click()
  await expect(
    page.getByRole('heading', { name: 'browser alias' }),
  ).toBeVisible()
  await page.getByRole('button', { name: 'JSON 가져오기' }).click()
  await page
    .getByLabel('파일 선택')
    .setInputFiles({
      name: 'related.json',
      mimeType: 'application/json',
      buffer: Buffer.from(
        JSON.stringify({
          schema_version: '1',
          entities: [
            {
              client_ref: 'song:test',
              entity_type: 'songs',
              data: { title_native: 'Test song', language_code: 'en' },
            },
          ],
        }),
      ),
    })
  await expect(page.getByText('1개 가져옴')).toBeVisible()
  await page.keyboard.press('Escape')
  await page
    .locator('button.catalog-row')
    .filter({ hasText: 'Test song' })
    .click()
  await expect(page.getByLabel('원어 제목')).toHaveValue('Test song')
  await page.reload()
  await expect(page.getByText('Test song', { exact: true })).toBeVisible()
  await page.setViewportSize({ width: 390, height: 844 })
  await page.getByText('Test song', { exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Test song' })).toBeVisible()
  await page.screenshot({
    path: testInfo.outputPath('mobile-review.png'),
    fullPage: true,
  })
  const sizes = await page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    width: innerWidth,
  }))
  expect(sizes.scroll).toBeLessThanOrEqual(sizes.width + 1)
  await page.getByRole('button', { name: '목록', exact: true }).click()
  await expect(page.getByPlaceholder('이름 또는 제목 검색')).toBeVisible()
  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' })
  await page.screenshot({
    path: testInfo.outputPath('mobile-dark.png'),
    fullPage: true,
  })
  await page.getByRole('button',{name:'묶음 삭제',exact:true}).click()
  await page.getByRole('button',{name:'취소',exact:true}).click()
  await expect(page.getByText('Test song',{exact:true})).toBeVisible()
  await page.getByRole('button',{name:'묶음 삭제',exact:true}).click()
  await page.getByRole('button',{name:'검수 묶음 삭제',exact:true}).click()
  await expect(page.getByText('첫 검수 묶음을 만들어 주세요')).toBeVisible()
  await page.reload()
  await expect(page.getByText('첫 검수 묶음을 만들어 주세요')).toBeVisible()
  expect(errors).toEqual([])
})

test('approval advances only on success and stops at the last pending item',async({page})=>{
  await page.goto('/')
  await expect(page.getByText('첫 검수 묶음을 만들어 주세요')).toBeVisible()
  await page.evaluate(async()=>{
    const {csrf}=await (await fetch('/api/admin/session')).json()
    const post=async(path:string,data:any)=>(await (await fetch('/api/admin'+path,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(data)})).json()).data
    const batch=await post('/batches',{name:'Next approval test'})
    for(const [ref,title] of [['first','First song'],['invalid',''],['last','Last song']]){
      await post('/drafts',{batch_id:batch.id,client_ref:ref,entity_type:'songs',data:{title_native:title}})
    }
  })
  await page.reload()
  await page.locator('button.catalog-row').filter({hasText:'First song'}).click()
  await page.getByRole('button',{name:'승인',exact:true}).click()
  await expect(page.getByRole('heading',{name:'invalid',exact:true})).toBeVisible()
  await page.getByRole('button',{name:'승인',exact:true}).click()
  await expect(page.getByRole('heading',{name:'invalid',exact:true})).toBeVisible()
  await expect(page.getByRole('button',{name:'승인',exact:true})).toBeEnabled()
  await page.getByLabel('원어 제목').fill('Fixed song')
  await page.getByRole('button',{name:'초안 저장'}).click()
  await page.getByRole('button',{name:'승인',exact:true}).click()
  await expect(page.getByRole('heading',{name:'Last song',exact:true})).toBeVisible()
  await page.getByRole('button',{name:'승인',exact:true}).click()
  await expect(page.getByRole('button',{name:'다시 검수'})).toBeVisible()
  await expect(page.getByRole('heading',{name:'Last song',exact:true})).toBeVisible()
})

test('platform registration combines account and artist review', async ({ page }, testInfo) => {
  await page.goto('/')
  await page.evaluate(async () => {
    const { csrf } = await (await fetch('/api/admin/session')).json()
    const post = async (path: string, data: any) => {
      const response = await fetch('/api/admin' + path, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf }, body: JSON.stringify(data) })
      if (!response.ok) throw new Error(await response.text())
      return (await response.json()).data
    }
    const batch = await post('/batches', { name: 'Platform test' })
    await post('/drafts', { batch_id: batch.id, client_ref: 'platform-artist', entity_type: 'artists', data: { slug: 'platform-artist', name_native: 'Platform Artist', entity_kind: 'solo' } })
  })
  await page.reload()
  await expect(page.locator('[data-slot=sidebar]').getByText('외부 플랫폼 등록')).toHaveCount(0)
  await expect(page.getByRole('tab', { name: '외부 플랫폼 등록', exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: '추가', exact: true }).click()
  await page.getByLabel('자료 종류').click()
  await page.getByRole('option', { name: '외부 플랫폼 등록', exact: true }).click()
  await page.getByRole('combobox', { name: '플랫폼 필수', exact: true }).click()
  await page.getByRole('option', { name: 'youtube', exact: true }).click()
  await page.getByLabel('주소', { exact: false }).fill('https://youtube.com/@platform-test')
  await page.getByLabel('계정 이름', { exact: true }).fill('@platform-test')
  await page.getByRole('button', { name: '아티스트 추가', exact: true }).click()
  await page.getByRole('button', { name: '아티스트 필수', exact: true }).click()
  await page.getByRole('button', { name: /Platform Artist.*초안/ }).click()
  await page.getByRole('button', { name: '계정과 연결 저장' }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(page.locator('button.catalog-row')).toHaveCount(2)
  await expect(page.locator('button.catalog-row').filter({ hasText: '외부 플랫폼 등록' })).toHaveCount(1)
  await expect(page.locator('button.catalog-row').filter({ hasText: '아티스트와 계정 연결' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '승인', exact: true })).toBeEnabled()
  await page.getByRole('button', { name: '승인', exact: true }).click()
  await expect(page.getByRole('button', { name: '다시 검수', exact: true })).toBeVisible()
  await expect(page.getByText('승인 · 반영 대기', { exact: true })).toHaveCount(0)
  await page.getByLabel('계정 이름', { exact: true }).fill('@edited')
  await page.getByRole('button', { name: '곡', exact: true }).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await page.getByRole('button', { name: /계속 편집|취소/ }).last().click()
  await page.getByRole('button', { name: '계정과 연결 저장' }).click()
  await expect(page.getByRole('button', { name: '승인', exact: true })).toBeEnabled()
  await page.screenshot({ path: testInfo.outputPath('platform-desktop.png'), fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: testInfo.outputPath('platform-mobile.png'), fullPage: true })
})
