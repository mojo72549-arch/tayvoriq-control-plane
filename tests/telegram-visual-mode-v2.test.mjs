import assert from 'node:assert/strict';
import test from 'node:test';

import selectionWorker from '../infra/telegram-approval-worker-v5.js';
import approvalWorker from '../infra/telegram-approval-worker-v6.js';

function encode(value) {
  return Buffer.from(value, 'utf8').toString('base64');
}

function decode(value) {
  return Buffer.from(value, 'base64').toString('utf8');
}

function pendingState({ visualMode = '', targetDuration = 35 } = {}) {
  const state = {
    trend_selection: {
      session_id: 'morning001',
      status: 'PENDING',
      selected: [2],
      candidates: [1,2,3,4,5].map(number => ({ number, topic: `Trend ${number}`, scope: 'technology_ai' })),
      language: 'Deutsch',
      platform: 'youtube_tiktok',
      target_duration: targetDuration,
    },
  };
  if (visualMode) state.trend_selection.visual_mode = visualMode;
  return state;
}

test('mode callback stores cinematic policy and renders all three mode buttons', async () => {
  const originalFetch = globalThis.fetch;
  const writes = [];
  const telegramBodies = [];
  globalThis.fetch = async (url, options = {}) => {
    const target = String(url);
    if (target.includes('/contents/.automation/tayvoriq-telegram-approval-state.json?ref=main')) {
      return new Response(JSON.stringify({ content: encode(`${JSON.stringify(pendingState())}\n`), sha: 'state-sha' }), { status:200 });
    }
    if (target.endsWith('/contents/.automation/tayvoriq-telegram-approval-state.json') && options.method === 'PUT') {
      const body = JSON.parse(options.body);
      writes.push(JSON.parse(decode(body.content)));
      return new Response(JSON.stringify({ content: { sha: 'new-state-sha' } }), { status:200 });
    }
    if (target.includes('/editMessageText') || target.includes('/answerCallbackQuery')) {
      telegramBodies.push({ target, body: JSON.parse(options.body) });
      return new Response(JSON.stringify({ ok:true, result:true }), { status:200 });
    }
    throw new Error(`Unexpected fetch: ${target}`);
  };
  try {
    const response = await selectionWorker.fetch(new Request('https://worker.example/', {
      method:'POST', headers:{'content-type':'application/json','X-Telegram-Bot-Api-Secret-Token':'secret'},
      body:JSON.stringify({callback_query:{id:'cb-mode',data:'tayvoriq:trend:mode:morning001:CINEMATIC',message:{message_id:77,chat:{id:'42'}}}}),
    }), { TELEGRAM_WEBHOOK_SECRET:'secret', TELEGRAM_CHAT_ID:'42', TELEGRAM_BOT_TOKEN:'token', GITHUB_TOKEN:'gh' });
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
  } finally { globalThis.fetch = originalFetch; }
});

test('approval is blocked until a visual mode is explicitly selected', async () => {
  const originalFetch = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, options = {}) => {
    const target = String(url); calls.push({ target, options });
    if (target.includes('/contents/.automation/tayvoriq-telegram-approval-state.json?ref=main')) {
      return new Response(JSON.stringify({ content:encode(`${JSON.stringify(pendingState())}\n`), sha:'state-sha' }), {status:200});
    }
    if (target.includes('/answerCallbackQuery')) return new Response(JSON.stringify({ok:true}), {status:200});
    throw new Error(`Unexpected fetch: ${target}`);
  };
  try {
    const response = await approvalWorker.fetch(new Request('https://worker.example/', {
      method:'POST', headers:{'content-type':'application/json','X-Telegram-Bot-Api-Secret-Token':'secret'},
      body:JSON.stringify({callback_query:{id:'cb-approve',data:'tayvoriq:trend:approve:morning001',message:{message_id:77,chat:{id:'42'}}}}),
    }), { TELEGRAM_WEBHOOK_SECRET:'secret', TELEGRAM_CHAT_ID:'42', TELEGRAM_BOT_TOKEN:'token', GITHUB_TOKEN:'gh' });
    assert.equal(response.status, 200);
    assert.equal(await response.text(), 'no visual mode');
    const answer = calls.find(call => call.target.includes('/answerCallbackQuery'));
    assert.match(JSON.parse(answer.options.body).text, /Standard, Cinematic oder Mixed/);
    assert.equal(calls.filter(call => call.target.includes('/queue/trend-relay/')).length, 0);
  } finally { globalThis.fetch = originalFetch; }
});

test('cinematic approval locks mode, clamps duration and queues production policy', async () => {
  const originalFetch = globalThis.fetch;
  const queuePayloads = [];
  let stateSha = 0;
  let state = pendingState({ visualMode:'CINEMATIC', targetDuration:40 });
  globalThis.fetch = async (url, options = {}) => {
    const target = String(url);
    if (target.includes('/contents/.automation/tayvoriq-telegram-approval-state.json?ref=main')) {
      return new Response(JSON.stringify({ content:encode(`${JSON.stringify(state)}\n`), sha:'state-sha' }), {status:200});
    }
    if (target.endsWith('/contents/.automation/tayvoriq-telegram-approval-state.json') && options.method === 'PUT') {
      const body=JSON.parse(options.body); state=JSON.parse(decode(body.content)); stateSha += 1;
      return new Response(JSON.stringify({content:{sha:`state-${stateSha}`}}), {status:200});
    }
    if (target.includes('/contents/queue/trend-relay/') && options.method === 'PUT') {
      const body=JSON.parse(options.body); queuePayloads.push(JSON.parse(decode(body.content)));
      return new Response(JSON.stringify({content:{sha:'queue-sha'}}), {status:201});
    }
    if (target.includes('/answerCallbackQuery') || target.includes('/editMessageReplyMarkup') || target.includes('/sendMessage')) {
      return new Response(JSON.stringify({ok:true,result:true}), {status:200});
    }
    throw new Error(`Unexpected fetch: ${target}`);
  };
  try {
    const response = await approvalWorker.fetch(new Request('https://worker.example/', {
      method:'POST', headers:{'content-type':'application/json','X-Telegram-Bot-Api-Secret-Token':'secret'},
      body:JSON.stringify({callback_query:{id:'cb-approve',data:'tayvoriq:trend:approve:morning001',message:{message_id:77,chat:{id:'42'}}}}),
    }), { TELEGRAM_WEBHOOK_SECRET:'secret', TELEGRAM_CHAT_ID:'42', TELEGRAM_BOT_TOKEN:'token', GITHUB_TOKEN:'gh' });
    assert.equal(response.status, 200);
    assert.equal(queuePayloads.length, 1);
    assert.equal(queuePayloads[0].visual_mode, 'CINEMATIC');
    assert.equal(queuePayloads[0].target_duration, '25');
    assert.equal(queuePayloads[0].production_policy.min_shots, 6);
    assert.equal(queuePayloads[0].production_policy.min_hero_shots, 2);
    assert.equal(queuePayloads[0].production_policy.final_quality_min, 85);
    assert.equal(state.trend_selection.status, 'QUEUED');
    assert.equal(state.trend_selection.visual_mode, 'CINEMATIC');
    assert.equal(state.trend_selection.target_duration, 25);
  } finally { globalThis.fetch = originalFetch; }
});
