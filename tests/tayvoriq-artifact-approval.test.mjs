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
