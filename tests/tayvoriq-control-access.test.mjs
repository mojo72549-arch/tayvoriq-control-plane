import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {controlAccess} from '../infra/tayvoriq-control-access.js';

const env={TELEGRAM_CHAT_ID:'42',TELEGRAM_WEBHOOK_SECRET:'webhook',GITHUB_TOKEN:'test',TELEGRAM_BOT_TOKEN:'test'};
const message={text:'/control',chat:{type:'private',id:42},from:{id:42,is_bot:false}};
const update=(m,secret='webhook')=>new Request('https://worker.example/',{method:'POST',headers:{'X-Telegram-Bot-Api-Secret-Token':secret},body:JSON.stringify({message:m})});
test('only the private owner command produces a grant, and GitHub only receives its digest',async t=>{
  const calls=[];
  t.mock.method(globalThis,'fetch',async(url,options)=>{
    calls.push({url,body:JSON.parse(options.body)});return Response.json({ok:true});
  });
  assert.equal(await controlAccess(update(message,'wrong'),env),null);
  assert.equal(await controlAccess(update({...message,text:'/help'}),env),null);
  for(const change of [{chat:{type:'group',id:42}},{from:{id:7,is_bot:false}},{chat:{type:'private',id:7}},{from:{id:42,is_bot:true}}])
    assert.equal((await controlAccess(update({...message,...change}),env)).status,200);
  assert.equal(calls.length,0);
  assert.equal((await controlAccess(update(message),env)).status,200);
  assert.equal(calls.length,2);
  const [stored,sent]=calls, link=new URL(sent.body.reply_markup.inline_keyboard[0][0].url);
  const token=new URLSearchParams(link.hash.slice(1)).get('access');
  assert.match(token,/^[-_A-Za-z0-9]{43}$/);
  const grant=JSON.parse(Buffer.from(stored.body.content,'base64'));
  assert.deepEqual(grant.allowed_hosts,[link.host]);assert.equal(sent.body.chat_id,'42');
  assert.equal(grant.token_sha256,createHash('sha256').update(token).digest('hex'));
  assert.ok(stored.url.endsWith(grant.token_sha256+'.json'));
  assert.ok(!JSON.stringify(grant).includes(token));
  assert.equal(Date.parse(grant.link_expires_at)-Date.parse(grant.issued_at),600000);
});
