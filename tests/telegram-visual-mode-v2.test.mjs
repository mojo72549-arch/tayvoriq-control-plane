import assert from 'node:assert/strict';
import test from 'node:test';

import worker from '../infra/telegram-approval-worker-v5.js';

function encode(value) {
  return Buffer.from(value, 'utf8').toString('base64');
}

function decode(value) {
  return Buffer.from(value, 'base64').toString('utf8');
}

function pendingState() {
  return {
    trend_selection: {
      session_id: 'morning001',
      status: 'PENDING',
      selected: [2],
      candidates: [1,2,3,4,5].map(number => ({ number, topic: `Trend ${number}`, scope: 'technology_ai' })),
      language: 'Deutsch',
      platform: 'youtube_tiktok',
      target_duration: 35,
    },
  };
}

test('mode callback stores cinematic policy and renders all three mode buttons', async () => {
  const originalFetch = globalThis.fetch;
  const writes = [];
  const telegramBodies = [];

  globalThis.fetch = async (url, options = {}) => {
    const target = String(url);
    if (target.includes('/contents/.automation/tayvoriq-telegram-approval-state.json?ref=main')) {
      return new Response(JSON.stringify({ content: encode(`${JSON.stringify(pendingState())}\n`), sha: 'state-sha' }), {
        status: 200, headers: { 'content-type': 'application/json' },
      });
    }
    if (target.endsWith('/contents/.automation/tayvoriq-telegram-approval-state.json') && options.method === 'PUT') {
      const body = JSON.parse(options.body);
      writes.push(JSON.parse(decode(body.content)));
      return new Response(JSON.stringify({ content: { sha: 'new-state-sha' } }), {
        status: 200, headers: { 'content-type': 'application/json' },
      });
    }
    if (target.includes('/editMessageText') || target.includes('/answerCallbackQuery')) {
      telegramBodies.push({ target, body: JSON.parse(options.body) });
      return new Response(JSON.stringify({ ok: true, result: true }), {
        status: 200, headers: { 'content-type': 'application/json' },
      });
    }
    throw new Error(`Unexpected fetch: ${target}`);
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
          id: 'cb-mode',
          data: 'tayvoriq:trend:mode:morning001:CINEMATIC',
          message: { message_id: 77, chat: { id: '42' } },
        },
      }),
    });

    const response = await worker.fetch(request, {
      TELEGRAM_WEBHOOK_SECRET: 'secret',
      TELEGRAM_CHAT_ID: '42',
      TELEGRAM_BOT_TOKEN: 'token',
      GITHUB_TOKEN: 'gh',
    });

    assert.equal(response.status, 200);
    assert.equal(writes.length, 1);
    assert.equal(writes[0].trend_selection.visual_mode, 'CINEMATIC');
    assert.equal(writes[0].trend_selection.production_policy.min_shots, 6);
    assert.equal(writes[0].trend_selection.production_policy.min_hero_shots, 2);
    assert.equal(writes[0].trend_selection.production_policy.final_quality_min, 85);

    const edit = telegramBodies.find(call => call.target.includes('/editMessageText'));
    assert.ok(edit);
    const callbacks = edit.body.reply_markup.inline_keyboard.flat().map(button => button.callback_data);
    assert.ok(callbacks.includes('tayvoriq:trend:mode:morning001:STANDARD'));
    assert.ok(callbacks.includes('tayvoriq:trend:mode:morning001:CINEMATIC'));
    assert.ok(callbacks.includes('tayvoriq:trend:mode:morning001:MIXED'));
    assert.match(edit.body.text, /Produktionsmodus: 🎬 Cinematic/);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
