import assert from 'node:assert/strict';
import test from 'node:test';
import { requestResearchTick } from '../infra/tayvoriq-research-clock.js';

const env = {GITHUB_REPOSITORY:'example/automation', GITHUB_TOKEN:'fixture'};
const now = Date.parse('2026-11-23T12:30:00Z');
const retry = {state:'WAITING', slot:'morning', berlin_date:'2026-11-23',
  retry_at_epoch:now/1000 - 10, valid_until_epoch:now/1000 + 900};

function github(queue, receipt, files = {}) {
  const posts = [];
  const fetcher = async (url, request) => {
    if (url.endsWith('/dispatches')) {
      posts.push(JSON.parse(request.body));
      return new Response(null, {status:204});
    }
    const path = url.split('/contents/')[1].split('?')[0];
    const data = files[path] ?? (path.endsWith('/research-retry.json') ? queue :
      path.includes('/deliveries/') ? receipt : null);
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

const pointer = '.github/state/tayvoriq-active-production-request.json';
const decision = '.automation/tayvoriq-artifact-decisions/123.json';
const status = '.automation/tayvoriq-agent-v2/review-trend-status/review-evening-123.json';
const boundReview = {
  [pointer]: {state:'COMPLETED', golden_path_run_id:123, selection_id:'20261122-evening-agentv2',
    request_id:'telegram-123-trend-1', source_context_sha256:'verified-context'},
  [decision]: {state:'REJECTED', review_id:'123', request_id:'telegram-123-trend-1',
    source_context_sha256:'verified-context', rejection_reason:'Original-Aufnahmen nötig', followup_action:'new_trends'},
};

test('a rejected review wakes the same bound replacement selection outside ordinary research hours', async () => {
  const {fetcher, posts} = github(null, null, boundReview);
  assert.equal(await requestResearchTick(now, env, now, fetcher), true);
  assert.deepEqual(posts[0].client_payload, {berlin_date:'2026-11-23', mode:'review', slot:'evening',
    selection_id:'review-evening-123', scheduled_epoch:now/1000});
});

test('a replacement is not woken after a verified result or when the decision is for a different review', async () => {
  const delivered = {selection_id:'review-evening-123', telegram_delivery_verified:true, telegram_message_id:8};
  for (const [receipt, files] of [
    [delivered, boundReview],
    [null, {...boundReview, [status]:{selection_id:'review-evening-123', state:'BLOCKED', telegram_notices:{BLOCKED:9}}}],
    [null, {...boundReview, [decision]:{...boundReview[decision], request_id:'different-request'}}],
  ]) {
    const {fetcher,posts} = github(null,receipt,files);
    assert.equal(await requestResearchTick(now,env,now,fetcher), false);
    assert.equal(posts.length,0);
  }
});

test('a failed bound repair wakes replacement research, while an ongoing repair does not', async () => {
  const choices = {...boundReview, [decision]:{...boundReview[decision],followup_action:'auto'}};
  const repair = '.github/state/rejected-review-repairs/123.json';
  for (const state of ['FAILED','RUNNING']) {
    const {fetcher,posts} = github(null,null,{...choices,[repair]:{state,rejected_run_id:123,
      request_id:'telegram-123-trend-1',source_context_sha256:'verified-context'}});
    assert.equal(await requestResearchTick(now,env,now,fetcher), state === 'FAILED');
    assert.equal(posts.length, Number(state === 'FAILED'));
  }
});
