import assert from 'node:assert/strict';
import test from 'node:test';

import worker from '../infra/telegram-approval-worker-v3.js';

test('stale trend callback is blocked without a chat error message', async () => {
  const calls = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url: String(url), options });
    if (String(url).includes('raw.githubusercontent.com')) {
      return new Response(JSON.stringify({ selection_id: 'current-selection-9999' }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      });
    }
    if (String(url).includes('/answerCallbackQuery')) {
      return new Response(JSON.stringify({ ok: true, result: true }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      });
    }
    if (String(url).includes('/editMessageReplyMarkup')) {
      return new Response(JSON.stringify({ ok: true, result: { message_id: 1153 } }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      });
    }
    throw new Error(`Unexpected fetch: ${url}`);
  };

  try {
    const request = new Request('https://worker.example/', {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'X-Telegram-Bot-Api-Secret-Token': 'secret',
      },
      body: JSON.stringify({
        callback_query: {
          id: 'cb-1',
          data: 'select_trend:old-selection-1234:1',
          message: { message_id: 1153, chat: { id: '42' } },
        },
      }),
    });
    const response = await worker.fetch(request, {
      TELEGRAM_WEBHOOK_SECRET: 'secret',
      TELEGRAM_CHAT_ID: '42',
      TELEGRAM_BOT_TOKEN: 'token',
      GITHUB_REPOSITORY: 'mojo72549-arch/tayvoriq-control-plane',
    });

    assert.equal(response.status, 409);
    assert.equal(await response.text(), 'stale trend selection');
    assert.equal(calls.filter(call => call.url.includes('/sendMessage')).length, 0);
    assert.equal(calls.filter(call => call.url.includes('/answerCallbackQuery')).length, 1);
    assert.equal(calls.filter(call => call.url.includes('/editMessageReplyMarkup')).length, 1);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
