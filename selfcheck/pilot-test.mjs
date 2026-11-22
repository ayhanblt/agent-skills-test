import {chromium} from 'playwright';
import assert from 'node:assert/strict';
const browser = await chromium.launch({executablePath:process.env.PILOT_CHROME});
try {
  const a=await (await browser.newContext()).newPage();
  const b=await (await browser.newContext()).newPage();
  await Promise.all([a.goto(process.env.BASE_URL),b.goto(process.env.BASE_URL)]);
  for(const p of [a,b]) await p.getByText('1 seat available').waitFor();
  await Promise.all([a.getByRole('button').click(),b.getByRole('button').click()]);
  await Promise.all([a,b].map(p=>p.getByText(/^(Confirmed|Sold out)$/).waitFor()));
  const results=await Promise.all([a,b].map(p=>p.getByRole('status').textContent()));
  assert.deepEqual(results.sort(),['Confirmed','Sold out']);
} finally { await browser.close(); }
