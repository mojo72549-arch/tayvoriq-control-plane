import assert from 'node:assert/strict';
import test from 'node:test';
import worker from '../infra/telegram-approval-worker-v7.js';

const env = { TELEGRAM_WEBHOOK_SECRET: 'test-secret', TELEGRAM_CHAT_ID: '42',
  TELEGRAM_BOT_TOKEN: 'test-token', GITHUB_TOKEN: 'test-gh-token', GITHUB_REPOSITORY: 'team/repo' };
const reviewId = '100';

function webhook(action, messageId, secret = env.TELEGRAM_WEBHOOK_SECRET) {
  return new Request('https://worker.example/', { method: 'POST', headers: {
    'X-Telegram-Bot-Api-Secret-Token': secret, 'Content-Type': 'application/json',
  }, body: JSON.stringify({ callback_query: { id: 'telegram-callback',
    data: `tayvoriq:artifact:${action}:${reviewId}`, message: { message_id: messageId, chat: { id: '42' } },
  } }) });
}

test('the rejection reason saves one bound automatic followup without a second choice', async t => {
  const binding = {schema:'tayvoriq-artifact-approval', state:'REJECTED', review_id:reviewId,
    telegram_message_id:123, request_id:'original-1', source_context_sha256:'original-hash'};
  const pointer = {schema:'tayvoriq-active-production-request-v1', state:'COMPLETED', golden_path_run_id:100,
    request_id:binding.request_id, source_context_sha256:binding.source_context_sha256};
  const writes = [];
  const keyboards = [];
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    if (url.endsWith('.json?ref=main')) {
      const data = url.includes('active-production-request') ? pointer : binding;
      return Response.json({encoding:'base64', sha:'known-blob', content:btoa(JSON.stringify(data))});
    }
    if (url.endsWith('.json') && options.method === 'PUT') {
      const body = JSON.parse(options.body);
      assert.equal(body.sha, 'known-blob');
      const saved = JSON.parse(Buffer.from(body.content, 'base64').toString('utf8'));
      writes.push(saved);
      Object.assign(binding, saved);
      return Response.json({});
    }
    if (url.endsWith('/editMessageText')) keyboards.push(JSON.parse(options.body).reply_markup.inline_keyboard);
    if (url.includes('api.telegram.org')) return Response.json({ok:true,result:{message_id:124}});
    throw Error('Unexpected request');
  });
  const submit = () => new Request('https://worker.example/', {method:'POST', headers:{
    'X-Telegram-Bot-Api-Secret-Token':env.TELEGRAM_WEBHOOK_SECRET, 'Content-Type':'application/json'},
    body:JSON.stringify({callback_query:{id:'reason-callback',data:'tayvoriq:reason:100:visuals',
      message:{message_id:124,chat:{id:'42'}}}})});
  assert.equal((await worker.fetch(submit(), env)).status, 200);
  assert.equal((await worker.fetch(submit(), env)).status, 200);
  assert.equal(writes.length, 1);
  assert.equal(writes[0].rejection_reason_code, 'visuals');
  assert.equal(writes[0].followup_action, 'auto');
  assert.deepEqual(keyboards, [[], []]);
  pointer.golden_path_run_id = 101;
  assert.equal((await worker.fetch(submit(), env)).status, 409);
  assert.equal(writes.length, 1);
});

for (const [action, messageId, secret, status, changes] of [
  ['approve', 123, env.TELEGRAM_WEBHOOK_SECRET, 200, ['APPROVED']],
  ['reject', 123, env.TELEGRAM_WEBHOOK_SECRET, 200, ['REJECTED']],
  ['approve', 124, env.TELEGRAM_WEBHOOK_SECRET, 409, []],
  ['approve', 123, 'wrong', 401, []],
]) {
  test(`artifact ${action} with message ${messageId} and expected status ${status}`, async t => {
    const binding = { schema: 'tayvoriq-artifact-approval', state: 'PENDING', review_id: reviewId, telegram_message_id: 123 };
    const writes = [];
    t.mock.method(globalThis, 'fetch', async (url, options) => {
      if (url.endsWith('.json?ref=main')) return Response.json({ encoding: 'base64', sha: 'known-pending-blob', content: btoa(JSON.stringify(binding)) });
      if (url.endsWith('.json') && options.method === 'PUT') {
        const record = JSON.parse(options.body);
        assert.equal(record.sha, 'known-pending-blob');
        const saved = JSON.parse(atob(record.content));
        assert.equal(saved.telegram_message_id, 123);
        assert.equal(saved.decided_via, 'telegram_callback');
        writes.push(saved.state);
        return Response.json({});
      }
      if (url.endsWith('/answerCallbackQuery') || url.endsWith('/editMessageReplyMarkup')) return Response.json({ok: true});
      throw new Error('Unexpected request');
    });
    const result = await worker.fetch(webhook(action, messageId, secret), env);
    assert.equal(result.status, status);
    assert.deepEqual(writes, changes);
  });
}
