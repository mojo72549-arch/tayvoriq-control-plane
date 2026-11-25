import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import worker from '../infra/telegram-approval-worker-v3.js';
import approvalWorker from '../infra/telegram-approval-worker-v2.js';

test('a Control Center selection consumption retires its Telegram approval buttons', async()=>{
  const originalFetch=globalThis.fetch;
  const selectionId='20261125-morning-agentv2',messageId=500;
  for(const trendId of ['1','2']){
    const calls=[];
    globalThis.fetch=async(url,options={})=>{
      const value=String(url);calls.push(value);
      if(value.includes('/selections/'+selectionId+'.json'))return Response.json({selection_id:selectionId,
        trends:[{id:'1',title:'Freigegebenes Thema'},{id:'2',title:'Anderer Vorschlag'}]});
      if(value.includes('/contents/')){
        if(value.includes('/requests/'))return Response.json({},{status:404});
        const data={selection_id:selectionId,request_id:'telegram-500-trend-1',state:'COMPLETED'};
        return Response.json({sha:'current',encoding:'base64',content:Buffer.from(JSON.stringify(data)).toString('base64')});
      }
      if(value.includes('/answerCallbackQuery')||value.includes('/editMessageReplyMarkup'))return Response.json({ok:true,result:true});
      throw Error('Unexpected action: '+value);
    };
    try{
      const response=await approvalWorker.fetch(new Request('https://worker.example/',{method:'POST',
        headers:{'Content-Type':'application/json','X-Telegram-Bot-Api-Secret-Token':'secret'},
        body:JSON.stringify({callback_query:{id:'callback-'+trendId,data:`approve_trend:${selectionId}:${trendId}`,
          message:{message_id:messageId,chat:{id:'42'}}}})}),
        {TELEGRAM_WEBHOOK_SECRET:'secret',TELEGRAM_CHAT_ID:'42',TELEGRAM_BOT_TOKEN:'token',GITHUB_TOKEN:'test-token'});
      assert.equal(response.status,trendId==='1'?200:409);
      assert.equal(calls.filter(url=>url.endsWith('/dispatches')).length,0);
      assert.equal(calls.filter(url=>url.includes('/sendMessage')).length,0);
      assert.ok(calls.some(url=>url.includes('/editMessageReplyMarkup')));
    }finally{globalThis.fetch=originalFetch;}
  }
});

test('stale trend callback is blocked without a chat error message', async () => {
  const calls = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url: String(url), options });
    if (String(url).endsWith('/state/tayvoriq-active-trend-selections.json')) {
      return new Response('not found', { status: 404 });
    }
    if (String(url).endsWith('/.github/run-now/tayvoriq-trend-request.json')) {
      return new Response(JSON.stringify({
        selection_id: '20260825-e-agentv2-g21',
        target_date: '2026-08-25',
        slot: 'evening',
      }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      });
    }
    if (String(url).includes('/selections/old-selection-1234.json')) {
      return new Response('not found', { status: 404 });
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

test('same-day morning and evening selections remain independently approvable', async () => {
  const calls = [];
  const originalFetch = globalThis.fetch;
  const morningSelection = {
    selection_id: '20260825-m-agentv2-g21',
    target_date: '2026-08-25',
    date: '2026-08-25',
    slot: 'morning',
    superseded: false,
    trends: [{
      id: '1',
      title: 'Testtrend',
      score: 91,
      criteria: { aktualitaet: 91 },
      sources: ['https://example.com/one', 'https://example.org/two'],
    }],
  };
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url: String(url), options });
    if (String(url).endsWith('/state/tayvoriq-active-trend-selections.json')) {
      return new Response('not found', { status: 404 });
    }
    if (String(url).endsWith('/.github/run-now/tayvoriq-trend-request.json')) {
      return new Response(JSON.stringify({
        selection_id: '20260825-e-agentv2-g21',
        target_date: '2026-08-25',
        date: '2026-08-25',
        slot: 'evening',
      }), { status: 200, headers: { 'content-type': 'application/json' } });
    }
    if (String(url).includes('/selections/20260825-m-agentv2-g21.json')) {
      return new Response(JSON.stringify(morningSelection), {
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
    if (String(url).includes('/editMessageText')) {
      return new Response(JSON.stringify({ ok: true, result: { message_id: 2201 } }), {
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
          id: 'cb-2',
          data: 'select_trend:20260825-m-agentv2-g21:1',
          message: { message_id: 2201, chat: { id: '42' } },
        },
      }),
    });
    const response = await worker.fetch(request, {
      TELEGRAM_WEBHOOK_SECRET: 'secret',
      TELEGRAM_CHAT_ID: '42',
      TELEGRAM_BOT_TOKEN: 'token',
      GITHUB_REPOSITORY: 'mojo72549-arch/tayvoriq-control-plane',
    });

    assert.equal(response.status, 200);
    assert.equal(await response.text(), 'ok');
    assert.equal(calls.filter(call => call.url.includes('/editMessageText')).length, 1);
    assert.equal(calls.filter(call => call.url.includes('/editMessageReplyMarkup')).length, 0);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('an unexpired manifest activates both recovery selections without replacing the canonical request', async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async url => {
    if (String(url).endsWith('/state/tayvoriq-active-trend-selections.json')) {
      return new Response(JSON.stringify({
        target_date: '2026-08-25',
        active_selection_ids: ['20260825-m-agentv2-g21', '20260825-e-agentv2-g21'],
        expires_at: '2999-08-26T04:00:00Z',
      }), { status: 200, headers: { 'content-type': 'application/json' } });
    }
    if (String(url).includes('/selections/20260825-m-agentv2-g21.json')) {
      return new Response(JSON.stringify({
        selection_id: '20260825-m-agentv2-g21',
        target_date: '2026-08-25',
        slot: 'morning',
        superseded: false,
      }), { status: 200, headers: { 'content-type': 'application/json' } });
    }
    throw new Error(`Unexpected fetch: ${url}`);
  };

  try {
    const { selectionIsActive } = await import('../infra/telegram-approval-worker-v3.js');
    assert.equal(await selectionIsActive({
      GITHUB_REPOSITORY: 'mojo72549-arch/tayvoriq-control-plane',
    }, '20260825-m-agentv2-g21'), true);
  } finally {
    globalThis.fetch = originalFetch;
  }
});


test('review approval verifies committed package with authenticated retry and no callback chat spam', () => {
  const source = readFileSync(new URL('../infra/telegram-approval-worker-v2.js', import.meta.url), 'utf8');
  const verifier = source.split('async function verifyCommittedReviewPackage', 2)[1]
    .split('async function upsertApprovalRecord', 1)[0];
  assert.match(source, /verifyCommittedReviewPackage\(env, runId\)/);
  assert.match(verifier, /Authorization: `Bearer \$\{env\.GITHUB_TOKEN\}`/);
  assert.match(verifier, /cache: 'no-store'/);
  assert.match(verifier, /attempt <= 3/);
  assert.match(verifier, /transient: true/);

  const approval = source.split('const packageCheck = await verifyCommittedReviewPackage\(env, runId\);', 2)[1]
    .split('const approval = await upsertApprovalRecord', 1)[0];
  assert.match(approval, /if \(callback\?\.id\)/);
  assert.match(approval, /await answerCallback\(env, callback\.id, callbackText, true\)/);
  assert.match(approval, /else \{[\s\S]*await requireTelegramMessage/);
});

test('the text preview submits exactly the chosen version and rejects a superseded wording', async () => {
  const originalFetch = globalThis.fetch;
  const selectionId = 'a'.repeat(40);
  const title = 'FlixTrain im DB Navigator';
  const source = {
    editorial_story_contract_version: 2,
    story_first_script_body: 'Dein ICE kommt zu spät. Der FlixTrain fährt weg.',
    story_first_script_body_b: 'Bei der Buchung gibt es zwei Fahrkarten.',
    cinematic_brief: { opening_visual: { subject: 'Bahnsteig' } },
  };
  const trend = { id: '1', title, sources: ['https://example.org/bahn'], source_context: source };
  const events = [];
  const previews = [];
  globalThis.fetch = async (url, options = {}) => {
    const address = String(url);
    if (address.includes('/selections/')) return Response.json({ selection_id: selectionId, trends: [trend] });
    if (address.includes('/contents/')) return Response.json({}, { status: 404 });
    if (address.endsWith('/dispatches')) {
      events.push(JSON.parse(options.body));
      return new Response(null, { status: 204 });
    }
    if (address.endsWith('/editMessageText')) {
      previews.push(JSON.parse(options.body));
      return Response.json({ ok: true, result: { message_id: 500 } });
    }
    if (address.includes('api.telegram.org')) {
      return Response.json({ ok: true, result: { message_id: 500 } });
    }
    throw Error('Unexpected request: ' + address);
  };
  const env = {
    TELEGRAM_WEBHOOK_SECRET: 'secret', TELEGRAM_CHAT_ID: '42',
    TELEGRAM_BOT_TOKEN: 'token', GITHUB_TOKEN: 'test-token',
  };
  const click = (data) => approvalWorker.fetch(new Request('https://worker.example/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Telegram-Bot-Api-Secret-Token': 'secret' },
    body: JSON.stringify({ callback_query: {
      id: 'callback-test', data, message: { message_id: 500, chat: { id: '42' } },
    } }),
  }), env);

  try {
    assert.equal((await click('select_trend:' + selectionId + ':1')).status, 200);
    const [preview] = previews;
    assert.ok(preview.text.includes('Sprechertext A'));
    assert.ok(preview.text.includes(source.story_first_script_body));
    assert.ok(preview.text.includes(source.story_first_script_body_b));
    assert.ok(preview.text.includes('Bahnsteig'));
    assert.equal(events.length, 0);
    const buttons = preview.reply_markup.inline_keyboard[0];
    assert.equal(buttons.length, 2);
    assert.ok(buttons.every(button => Buffer.byteLength(button.callback_data) <= 64));
    const callback = buttons[1].callback_data;
    const original = source.story_first_script_body_b;
    source.story_first_script_body_b = 'Diese Fassung wurde seit der Vorschau verändert.';
    assert.equal((await click(callback)).status, 409);
    assert.equal(events.length, 0);

    source.story_first_script_body_b = original;
    assert.equal((await click(callback)).status, 200);
    assert.equal(events.length, 1);
    assert.equal(events[0].event_type, 'tayvoriq_trend_approved');
    assert.match(events[0].client_payload.text_approval, /^b:[a-f0-9]{10}$/);
    assert.equal(events[0].client_payload.selection_id, selectionId);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
