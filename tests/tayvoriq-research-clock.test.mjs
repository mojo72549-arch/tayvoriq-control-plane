import assert from 'node:assert/strict';
import test from 'node:test';
import { requestResearchTick } from '../infra/tayvoriq-research-clock.js';

const env = {GITHUB_REPOSITORY:'example/automation', GITHUB_TOKEN:'fixture'};
const now = Date.parse('2026-11-23T12:30:00Z');
const retry = {state:'WAITING', slot:'morning', berlin_date:'2026-11-23',
  retry_at_epoch:now/1000 - 10, valid_until_epoch:now/1000 + 900};

function github(queue, receipt) {
  const posts = [];
  const fetcher = async (url, request) => {
    if (url.endsWith('/dispatches')) {
      posts.push(JSON.parse(request.body));
      return new Response(null, {status:204});
    }
    const data = url.includes('/research-retry.json') ? queue : receipt;
    return data ? Response.json({encoding:'base64',content:btoa(JSON.stringify(data))}) :
      new Response(null, {status:404});
  };
  return {fetcher, posts};
}

test('an overdue retry wakes the original slot without a GitHub schedule event', async () => {
  const {fetcher, posts} = github(retry, null);
  assert.equal(await requestResearchTick(now, env, now, fetcher), true);
  assert.deepEqual(posts[0], {event_type:'tayvoriq_research_tick',client_payload:{
    berlin_date:'2026-11-23',slot:'morning',mode:'retry',scheduled_epoch:now/1000,
  }});
});

test('expired, delivered and not-yet-due work does not dispatch', async () => {
  for (const [queue, receipt] of [
    [{...retry,valid_until_epoch:now/1000}, null],
    [{...retry,retry_at_epoch:now/1000+10}, null],
    [retry,{selection_id:'20261123-morning-agentv2',telegram_delivery_verified:true,telegram_message_id:48}],
  ]) {
    const {fetcher,posts} = github(queue,receipt);
    assert.equal(await requestResearchTick(now,env,now,fetcher), false);
    assert.equal(posts.length,0);
  }
});

test('catch-up follows Berlin summer time and targets the evening slot', async () => {
  const summer = Date.parse('2026-08-23T17:05:00Z');
  const {fetcher, posts} = github(null, null);
  assert.equal(await requestResearchTick(summer,env,summer,fetcher), true);
  assert.equal(posts[0].client_payload.slot,'evening');
  assert.equal(posts[0].client_payload.mode,'catchup');
});
