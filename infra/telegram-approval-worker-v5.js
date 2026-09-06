import v2 from './telegram-approval-worker-v2.js';

const STATE_REPOSITORY = 'mojo72549-arch/tayvoriq-control-plane';
const STATE_PATH = '.automation/tayvoriq-telegram-approval-state.json';
const RELAY_WORKFLOW = 'tayvoriq-smart-trend-relay.yml';
const CALLBACK_RE = /^tayvoriq:trend:(toggle|approve|reset):([A-Za-z0-9_-]{1,32})(?::([1-5]))?$/;

export default {
  async fetch(request, env) {
    if (request.method !== 'POST') return v2.fetch(request, env);

    const suppliedSecret = request.headers.get('X-Telegram-Bot-Api-Secret-Token') || '';
    if (!env.TELEGRAM_WEBHOOK_SECRET || suppliedSecret !== env.TELEGRAM_WEBHOOK_SECRET) {
      return v2.fetch(request, env);
    }

    let update;
    try { update = await request.clone().json(); }
    catch { return v2.fetch(request, env); }

    const callback = update.callback_query;
    const message = update.message || callback?.message;
    const chatId = String(message?.chat?.id || '');
    const callbackData = String(callback?.data || '').trim();

    const match = callbackData.match(CALLBACK_RE);
    if (match) {
      if (!chatId || chatId !== String(env.TELEGRAM_CHAT_ID)) {
        if (callback?.id) await answerCallback(env, callback.id, 'Nicht autorisierter Chat.', true);
        return new Response('ignored');
      }
      try {
        return await handleTrendCallback(env, callback, chatId, match);
      } catch (error) {
        console.error('trend callback failed', String(error));
        if (callback?.id) await answerCallback(env, callback.id, 'Trend-Aktion konnte nicht verarbeitet werden.', true);
        try { await sendMessage(env, chatId, `❌ Trend-Aktion fehlgeschlagen: ${String(error).slice(0, 500)}`); } catch {}
        // Always acknowledge Telegram updates to prevent webhook retry storms.
        return new Response('trend callback acknowledged after failure', { status: 200 });
      }
    }

    const typed = parseNumbers(update.message?.text);
    if (typed.length && chatId && chatId === String(env.TELEGRAM_CHAT_ID)) {
      try {
        const handled = await handleTypedSelection(env, chatId, typed);
        if (handled) return new Response('ok');
      } catch (error) {
        console.error('typed trend selection failed', String(error));
        return new Response('typed selection acknowledged after failure', { status: 200 });
      }
    }

    return v2.fetch(request, env);
  },
};

async function handleTrendCallback(env, callback, chatId, match) {
  const [, action, sessionId, numberText] = match;
  const callbackId = String(callback?.id || '');
  const messageId = Number(callback?.message?.message_id || 0);
  let loaded = await loadState(env);
  const state = loaded.state;
  const session = state?.trend_selection;

  if (!session || String(session.session_id || '') !== sessionId) {
    if (callbackId) await answerCallback(env, callbackId, 'Diese Trendauswahl ist nicht mehr aktuell.', true);
    return new Response('stale selection', { status: 200 });
  }

  const status = String(session.status || '').toUpperCase();
  if (status !== 'PENDING') {
    if (callbackId) await answerCallback(env, callbackId, `Trendauswahl bereits verarbeitet: ${status}.`);
    if (messageId) await clearKeyboard(env, chatId, messageId);
    return new Response('already processed');
  }

  if (action === 'toggle') {
    const number = Number(numberText || 0);
    if (!Number.isInteger(number) || number < 1 || number > 5) {
      if (callbackId) await answerCallback(env, callbackId, 'Ungültige Trendnummer.', true);
      return new Response('invalid number', { status: 200 });
    }
    const selected = new Set((Array.isArray(session.selected) ? session.selected : []).map(Number));
    selected.has(number) ? selected.delete(number) : selected.add(number);
    session.selected = [...selected].sort((a,b)=>a-b);
    session.updated_at = new Date().toISOString();
    loaded = await saveState(env, state, loaded.sha, `Update Telegram trend selection ${sessionId}`);
    await refreshTrendMessage(env, chatId, session, messageId);
    if (callbackId) await answerCallback(env, callbackId, 'Auswahl aktualisiert.');
    return new Response('ok');
  }

  if (action === 'reset') {
    session.selected = [];
    session.updated_at = new Date().toISOString();
    loaded = await saveState(env, state, loaded.sha, `Reset Telegram trend selection ${sessionId}`);
    await refreshTrendMessage(env, chatId, session, messageId);
    if (callbackId) await answerCallback(env, callbackId, 'Auswahl zurückgesetzt.');
    return new Response('ok');
  }

  const selected = [...new Set((Array.isArray(session.selected) ? session.selected : []).map(Number))]
    .filter(n => n >= 1 && n <= 5).sort((a,b)=>a-b);
  if (!selected.length) {
    if (callbackId) await answerCallback(env, callbackId, 'Bitte zuerst mindestens einen Trend auswählen.', true);
    return new Response('no selection');
  }

  session.status = 'RELEASING';
  session.released_at = new Date().toISOString();
  session.dispatches = session.dispatches && typeof session.dispatches === 'object' ? session.dispatches : {};
  loaded = await saveState(env, state, loaded.sha, `Lock Telegram trend release ${sessionId}`);

  const candidates = new Map((Array.isArray(session.candidates) ? session.candidates : [])
    .map(c => [Number(c?.number || 0), c]));
  const failures = [];
  for (const number of selected) {
    const candidate = candidates.get(number);
    if (!candidate || !String(candidate.topic || '').trim()) {
      failures.push(`${number}: Kandidat fehlt`);
      session.dispatches[String(number)] = { status: 'FAILED', error: 'candidate missing', failed_at: new Date().toISOString() };
      continue;
    }
    try {
      await dispatchRelay(env, candidate, session);
      session.dispatches[String(number)] = { status: 'DISPATCHED', topic: String(candidate.topic).trim(), dispatched_at: new Date().toISOString() };
    } catch (error) {
      const detail = String(error).slice(0, 260);
      failures.push(`${number}: ${detail}`);
      session.dispatches[String(number)] = { status: 'FAILED', topic: String(candidate.topic).trim(), error: detail, failed_at: new Date().toISOString() };
    }
  }

  session.status = failures.length ? 'PARTIAL_FAILURE' : 'DISPATCHED';
  session.completed_at = new Date().toISOString();
  await saveState(env, state, loaded.sha, `Complete Telegram trend release ${sessionId}`);

  if (callbackId) await answerCallback(env, callbackId,
    failures.length ? 'Freigabe verarbeitet; mindestens ein Request ist fehlgeschlagen.' : 'Trend freigegeben. Request-Workflow gestartet.',
    Boolean(failures.length));
  if (messageId) await clearKeyboard(env, chatId, messageId);

  const topics = selected.map(n => String(candidates.get(n)?.topic || '').trim()).filter(Boolean);
  let text = ['✅ Trend freigegeben.','',`Auswahl: ${selected.join(', ')}`,...topics.map(t=>`• ${t}`),'','Der Request-Workflow wurde gestartet.'].join('\n');
  if (failures.length) text += `\n\n⚠️ Fehler:\n${failures.join('\n')}`;
  await sendMessage(env, chatId, text);
  return new Response('ok');
}

async function handleTypedSelection(env, chatId, numbers) {
  const loaded = await loadState(env);
  const session = loaded.state?.trend_selection;
  if (!session || String(session.status || '').toUpperCase() !== 'PENDING') return false;
  session.selected = [...new Set(numbers)].sort((a,b)=>a-b);
  session.updated_at = new Date().toISOString();
  await saveState(env, loaded.state, loaded.sha, `Set Telegram trend selection ${session.session_id || ''}`);
  await refreshTrendMessage(env, chatId, session, Number(session.message_id || 0));
  await sendMessage(env, chatId, `🟡 Auswahl ${session.selected.join(', ')} vorgemerkt. Noch kein Workflow gestartet – bitte jetzt „Trend freigeben“ klicken.`);
  return true;
}

function parseNumbers(value) {
  const text = String(value || '').trim().toLowerCase();
  if (!text) return [];
  const normalized = text.replace(/\b(?:und|and)\b/g, ',').replace(/[+&;/|]/g, ',').replace(/\s+/g, ',');
  if (!/^,*[1-5](?:,*[1-5])*,*$/.test(normalized)) return [];
  return [...new Set((normalized.match(/[1-5]/g) || []).map(Number))].sort((a,b)=>a-b);
}

function trendText(session) {
  const selected = new Set((Array.isArray(session.selected) ? session.selected : []).map(Number));
  const lines = ['🔥 TAYVORIQ – Trendauswahl',''];
  for (const c of Array.isArray(session.candidates) ? session.candidates : []) {
    const n = Number(c?.number || 0);
    lines.push(`${selected.has(n) ? '✅' : `${n}️⃣`} ${String(c?.topic || '').trim()}`);
  }
  lines.push('',`Ausgewählt: ${selected.size ? [...selected].sort((a,b)=>a-b).join(', ') : 'noch nichts'}`,'','Nummer(n) senden oder unten auswählen. Erst „Trend freigeben“ startet den Request-Workflow.');
  return lines.join('\n');
}

function trendKeyboard(session) {
  const sessionId = String(session.session_id || '').replace(/[^A-Za-z0-9_-]/g,'').slice(0,32);
  const selected = new Set((Array.isArray(session.selected) ? session.selected : []).map(Number));
  const row = [];
  for (let n=1;n<=5;n++) row.push({ text: selected.has(n) ? `✅ ${n}` : String(n), callback_data: `tayvoriq:trend:toggle:${sessionId}:${n}` });
  return { inline_keyboard: [row,[
    { text:'✅ Trend freigeben', callback_data:`tayvoriq:trend:approve:${sessionId}` },
    { text:'✏️ Auswahl ändern', callback_data:`tayvoriq:trend:reset:${sessionId}` }
  ]]};
}

async function refreshTrendMessage(env, chatId, session, messageId) {
  const target = Number(messageId || session.message_id || 0);
  const payload = { chat_id: chatId, text: trendText(session), disable_web_page_preview: true, reply_markup: trendKeyboard(session) };
  if (target) payload.message_id = target;
  const method = target ? 'editMessageText' : 'sendMessage';
  const r = await telegramMethod(env, method, payload);
  if (!r.ok) {
    const detail = await r.text();
    if (!detail.includes('message is not modified')) throw new Error(`Telegram ${method} ${r.status}: ${detail.slice(0,220)}`);
  }
}

async function clearKeyboard(env, chatId, messageId) {
  if (!messageId) return;
  await telegramMethod(env,'editMessageReplyMarkup',{chat_id:chatId,message_id:messageId,reply_markup:{inline_keyboard:[]}});
}

async function answerCallback(env, callbackId, text, alert=false) {
  if (!callbackId) return;
  await telegramMethod(env,'answerCallbackQuery',{callback_query_id:callbackId,text:String(text||'').slice(0,190),show_alert:Boolean(alert)});
}

async function sendMessage(env, chatId, text) {
  const r = await telegramMethod(env,'sendMessage',{chat_id:chatId,text:String(text||'').slice(0,4000),disable_web_page_preview:true});
  if (!r.ok) throw new Error(`Telegram sendMessage failed: ${r.status}`);
}

function telegramMethod(env, method, payload) {
  return fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/${method}`, {
    method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)
  });
}

function ghHeaders(env) {
  return { Authorization:`Bearer ${env.GITHUB_TOKEN}`, Accept:'application/vnd.github+json', 'X-GitHub-Api-Version':'2022-11-28', 'User-Agent':'tayvoriq-telegram-approval', 'Content-Type':'application/json' };
}

function decodeContent(value) {
  const binary = atob(String(value || '').replace(/\n/g,''));
  return new TextDecoder().decode(Uint8Array.from(binary, c => c.charCodeAt(0)));
}

function encodeContent(value) {
  const bytes = new TextEncoder().encode(String(value || ''));
  let binary=''; for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}

async function loadState(env) {
  const url = `https://api.github.com/repos/${STATE_REPOSITORY}/contents/${STATE_PATH}?ref=main`;
  const r = await fetch(url,{headers:ghHeaders(env)});
  if (!r.ok) throw new Error(`Control-State nicht erreichbar: GitHub ${r.status} ${(await r.text()).slice(0,180)}`);
  const payload = await r.json();
  return { state: JSON.parse(decodeContent(payload.content)), sha: String(payload.sha || '') };
}

async function saveState(env, state, sha, message) {
  state.last_checked_at = new Date().toISOString();
  const url = `https://api.github.com/repos/${STATE_REPOSITORY}/contents/${STATE_PATH}`;
  const r = await fetch(url,{method:'PUT',headers:ghHeaders(env),body:JSON.stringify({message,content:encodeContent(`${JSON.stringify(state,null,2)}\n`),sha,branch:'main'})});
  if (!r.ok) throw new Error(`Control-State konnte nicht gespeichert werden: GitHub ${r.status} ${(await r.text()).slice(0,220)}`);
  const payload = await r.json();
  return { state, sha: String(payload?.content?.sha || '') };
}

async function dispatchRelay(env, candidate, session) {
  const url = `https://api.github.com/repos/${STATE_REPOSITORY}/actions/workflows/${RELAY_WORKFLOW}/dispatches`;
  const r = await fetch(url,{method:'POST',headers:ghHeaders(env),body:JSON.stringify({ref:'main',inputs:{
    trend_mode:'manual_topic', trend_scope:String(candidate.scope || 'auto_scope'), topic:String(candidate.topic || '').trim(),
    language:String(session.language || 'Deutsch'), platform:String(session.platform || 'youtube_tiktok'),
    target_duration:String(Number(session.target_duration || 40)), llm_provider:String(session.llm_provider || 'auto'), telegram_notify:'true'
  }})});
  if (r.status !== 204) throw new Error(`Relay-Workflow GitHub ${r.status}: ${(await r.text()).slice(0,220)}`);
}
