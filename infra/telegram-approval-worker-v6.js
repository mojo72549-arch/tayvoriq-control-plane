import v5 from './telegram-approval-worker-v5.js';

const STATE_REPOSITORY = 'mojo72549-arch/tayvoriq-control-plane';
const STATE_PATH = '.automation/tayvoriq-telegram-approval-state.json';
const APPROVE_RE = /^tayvoriq:trend:approve:([A-Za-z0-9_-]{1,32})$/;
const VISUAL_MODES = new Set(['STANDARD', 'CINEMATIC', 'MIXED']);

export default {
  async fetch(request, env) {
    if (request.method !== 'POST') return v5.fetch(request, env);

    const suppliedSecret = request.headers.get('X-Telegram-Bot-Api-Secret-Token') || '';
    if (!env.TELEGRAM_WEBHOOK_SECRET || suppliedSecret !== env.TELEGRAM_WEBHOOK_SECRET) {
      return v5.fetch(request, env);
    }

    let update;
    try { update = await request.clone().json(); }
    catch { return v5.fetch(request, env); }

    const callback = update.callback_query;
    const data = String(callback?.data || '').trim();
    const match = data.match(APPROVE_RE);
    if (!match) return v5.fetch(request, env);

    const chatId = String(callback?.message?.chat?.id || '');
    if (!chatId || chatId !== String(env.TELEGRAM_CHAT_ID)) {
      if (callback?.id) await answerCallback(env, callback.id, 'Nicht autorisierter Chat.', true);
      return new Response('ignored', { status: 200 });
    }

    try {
      return await handleApprove(env, callback, chatId, match[1]);
    } catch (error) {
      console.error('v6 trend approval failed', String(error));
      if (callback?.id) await answerCallback(env, callback.id, 'Trend-Freigabe konnte nicht verarbeitet werden.', true);
      try { await sendMessage(env, chatId, `❌ Trend-Freigabe fehlgeschlagen: ${String(error).slice(0, 500)}`); } catch {}
      return new Response('approval acknowledged after failure', { status: 200 });
    }
  },
};

async function handleApprove(env, callback, chatId, sessionId) {
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
    return new Response('already processed', { status: 200 });
  }

  const selected = [...new Set((Array.isArray(session.selected) ? session.selected : []).map(Number))]
    .filter(n => n >= 1 && n <= 5).sort((a, b) => a - b);
  if (!selected.length) {
    if (callbackId) await answerCallback(env, callbackId, 'Bitte zuerst mindestens einen Trend auswählen.', true);
    return new Response('no selection', { status: 200 });
  }

  const visualMode = normalizeVisualMode(session.visual_mode);
  if (!visualMode) {
    if (callbackId) await answerCallback(env, callbackId, 'Bitte zuerst Standard, Cinematic oder Mixed wählen.', true);
    return new Response('no visual mode', { status: 200 });
  }
  session.visual_mode = visualMode;
  session.production_policy = productionPolicy(visualMode);
  session.target_duration = targetDurationForMode(session.target_duration, visualMode);

  session.status = 'RELEASING';
  session.released_at = new Date().toISOString();
  session.dispatches = session.dispatches && typeof session.dispatches === 'object' ? session.dispatches : {};
  loaded = await saveState(env, state, loaded.sha, `Lock Telegram trend release ${sessionId} ${visualMode}`);

  const candidates = new Map((Array.isArray(session.candidates) ? session.candidates : [])
    .map(c => [Number(c?.number || 0), c]));
  const failures = [];

  for (const number of selected) {
    const candidate = candidates.get(number);
    if (!candidate || !String(candidate.topic || '').trim()) {
      failures.push(`${number}: Kandidat fehlt`);
      session.dispatches[String(number)] = {
        status: 'FAILED', error: 'candidate missing', failed_at: new Date().toISOString()
      };
      continue;
    }

    try {
      const queuePath = await enqueueRelay(env, candidate, session);
      session.dispatches[String(number)] = {
        status: 'QUEUED',
        topic: String(candidate.topic).trim(),
        visual_mode: visualMode,
        queue_path: queuePath,
        queued_at: new Date().toISOString(),
      };
    } catch (error) {
      const detail = String(error).slice(0, 260);
      failures.push(`${number}: ${detail}`);
      session.dispatches[String(number)] = {
        status: 'FAILED', topic: String(candidate.topic).trim(), error: detail, failed_at: new Date().toISOString()
      };
    }
  }

  session.status = failures.length ? 'PARTIAL_FAILURE' : 'QUEUED';
  session.completed_at = new Date().toISOString();
  await saveState(env, state, loaded.sha, `Complete Telegram trend release ${sessionId}`);

  if (callbackId) {
    await answerCallback(
      env,
      callbackId,
      failures.length ? 'Freigabe verarbeitet; mindestens ein Request ist fehlgeschlagen.' : 'Trend freigegeben. Request wurde sicher eingereiht.',
      Boolean(failures.length),
    );
  }
  if (messageId) await clearKeyboard(env, chatId, messageId);

  const topics = selected.map(n => String(candidates.get(n)?.topic || '').trim()).filter(Boolean);
  let text = [
    '✅ Trend freigegeben.',
    '',
    `Auswahl: ${selected.join(', ')}`,
    `Modus: ${modeLabel(visualMode)}`,
    `Zieldauer: ${session.target_duration} Sekunden`,
    ...topics.map(t => `• ${t}`),
    '',
    failures.length ? 'Mindestens ein Request konnte nicht eingereiht werden.' : 'Der Request wurde in die Produktions-Queue gestellt und wird automatisch ins Studio weitergereicht.',
  ].join('\n');
  if (failures.length) text += `\n\n⚠️ Fehler:\n${failures.join('\n')}`;
  await sendMessage(env, chatId, text);
  return new Response('ok', { status: 200 });
}

function normalizeVisualMode(value) {
  const mode = String(value || '').trim().toUpperCase();
  return VISUAL_MODES.has(mode) ? mode : '';
}

function modeLabel(mode) {
  return ({ STANDARD:'⚡ Standard', CINEMATIC:'🎬 Cinematic', MIXED:'🔥 Mixed' })[mode] || 'nicht gewählt';
}

function productionPolicy(mode) {
  const common = {
    allow_real_footage: true,
    allow_stock: true,
    allow_generated_video: true,
    cohesion_min: 80,
    audio_min: 82,
  };
  if (mode === 'CINEMATIC') return { ...common, min_shots:6, max_shots:8, min_hero_shots:2, final_quality_min:85 };
  if (mode === 'MIXED') return { ...common, min_shots:6, max_shots:8, min_hero_shots:1, final_quality_min:82 };
  return { ...common, min_shots:4, max_shots:8, min_hero_shots:0, final_quality_min:78 };
}

function targetDurationForMode(value, mode) {
  const requested = Number(value || 35);
  if (mode === 'CINEMATIC') return Math.max(15, Math.min(25, requested));
  if (mode === 'MIXED') return Math.max(15, Math.min(30, requested));
  return Math.max(15, Math.min(35, requested));
}

async function enqueueRelay(env, candidate, session) {
  const cleanSession = String(session.session_id || 'trend').replace(/[^A-Za-z0-9_-]/g, '').slice(0, 32) || 'trend';
  const number = Number(candidate.number || 0);
  const stamp = Date.now();
  const path = `queue/trend-relay/${cleanSession}-${number}-${stamp}.json`;
  const visualMode = normalizeVisualMode(session.visual_mode);
  if (!visualMode) throw new Error('visual mode missing after approval lock');
  const payload = {
    session_id: cleanSession,
    candidate_number: number,
    trend_mode: 'manual_topic',
    trend_scope: String(candidate.scope || 'auto_scope'),
    topic: String(candidate.topic || '').trim(),
    language: String(session.language || 'Deutsch'),
    platform: String(session.platform || 'youtube_tiktok'),
    target_duration: String(Number(session.target_duration || 35)),
    llm_provider: String(session.llm_provider || 'auto'),
    telegram_notify: 'true',
    visual_mode: visualMode,
    production_policy: session.production_policy || productionPolicy(visualMode),
    queued_at: new Date().toISOString(),
    source: 'telegram-worker-v6-visual-modes-v2',
  };

  const url = `https://api.github.com/repos/${STATE_REPOSITORY}/contents/${path}`;
  const r = await fetch(url, {
    method: 'PUT',
    headers: ghHeaders(env),
    body: JSON.stringify({
      message: `Queue TAYVORIQ trend ${cleanSession} #${number} ${visualMode}`,
      content: encodeContent(`${JSON.stringify(payload, null, 2)}\n`),
      branch: 'main',
    }),
  });
  if (r.status !== 201 && r.status !== 200) {
    throw new Error(`Relay-Queue GitHub ${r.status}: ${(await r.text()).slice(0, 220)}`);
  }
  return path;
}

function ghHeaders(env) {
  return {
    Authorization: `Bearer ${env.GITHUB_TOKEN}`,
    Accept: 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
    'User-Agent': 'tayvoriq-telegram-approval',
    'Content-Type': 'application/json',
  };
}

function decodeContent(value) {
  const binary = atob(String(value || '').replace(/\n/g, ''));
  return new TextDecoder().decode(Uint8Array.from(binary, c => c.charCodeAt(0)));
}

function encodeContent(value) {
  const bytes = new TextEncoder().encode(String(value || ''));
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}

async function loadState(env) {
  const url = `https://api.github.com/repos/${STATE_REPOSITORY}/contents/${STATE_PATH}?ref=main`;
  const r = await fetch(url, { headers: ghHeaders(env) });
  if (!r.ok) throw new Error(`Control-State nicht erreichbar: GitHub ${r.status} ${(await r.text()).slice(0, 180)}`);
  const payload = await r.json();
  return { state: JSON.parse(decodeContent(payload.content)), sha: String(payload.sha || '') };
}

async function saveState(env, state, sha, message) {
  state.last_checked_at = new Date().toISOString();
  const url = `https://api.github.com/repos/${STATE_REPOSITORY}/contents/${STATE_PATH}`;
  const r = await fetch(url, {
    method: 'PUT',
    headers: ghHeaders(env),
    body: JSON.stringify({
      message,
      content: encodeContent(`${JSON.stringify(state, null, 2)}\n`),
      sha,
      branch: 'main',
    }),
  });
  if (!r.ok) throw new Error(`Control-State konnte nicht gespeichert werden: GitHub ${r.status} ${(await r.text()).slice(0, 220)}`);
  const payload = await r.json();
  return { state, sha: String(payload?.content?.sha || '') };
}

function telegramMethod(env, method, payload) {
  return fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/${method}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

async function answerCallback(env, callbackId, text, alert = false) {
  if (!callbackId) return;
  await telegramMethod(env, 'answerCallbackQuery', {
    callback_query_id: callbackId,
    text: String(text || '').slice(0, 190),
    show_alert: Boolean(alert),
  });
}

async function clearKeyboard(env, chatId, messageId) {
  if (!messageId) return;
  await telegramMethod(env, 'editMessageReplyMarkup', {
    chat_id: chatId,
    message_id: messageId,
    reply_markup: { inline_keyboard: [] },
  });
}

async function sendMessage(env, chatId, text) {
  const r = await telegramMethod(env, 'sendMessage', {
    chat_id: chatId,
    text: String(text || '').slice(0, 4000),
    disable_web_page_preview: true,
  });
  if (!r.ok) throw new Error(`Telegram sendMessage failed: ${r.status}`);
}