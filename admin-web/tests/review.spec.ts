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
