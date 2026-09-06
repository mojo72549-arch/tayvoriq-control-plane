import v2 from './telegram-approval-worker-v2.js';

const STUDIO_REPOSITORY = 'mojo72549-arch/shorts-agent-studio';
const STUDIO_STATE_PATH = '.automation/tayvoriq-telegram-approval-state.json';
const STUDIO_TREND_WORKFLOW = 'tayvoriq-smart-trend-run.yml';
const STUDIO_TREND_CALLBACK = /^tayvoriq:trend:(toggle|approve|reset):([A-Za-z0-9_-]{1,32})(?::([1-5]))?$/;

export default {
  async fetch(request, env) {
    if (request.method !== 'POST') return v2.fetch(request, env);

    const suppliedSecret = request.headers.get('X-Telegram-Bot-Api-Secret-Token') || '';
    if (!env.TELEGRAM_WEBHOOK_SECRET || suppliedSecret !== env.TELEGRAM_WEBHOOK_SECRET) {
      return v2.fetch(request, env);
    }

    let update;
    try {
      update = await request.clone().json();
    } catch {
      return v2.fetch(request, env);
    }

    const callback = update.callback_query;
    const message = update.message || callback?.message;
    const callbackData = String(callback?.data || '').trim();
    const chatId = String(message?.chat?.id || '');

    const studioMatch = callbackData.match(STUDIO_TREND_CALLBACK);
    if (studioMatch) {
      if (!chatId || chatId !== String(env.TELEGRAM_CHAT_ID)) {
        if (callback?.id) {
          await answerStudioCallback(env, callback.id, 'Nicht autorisierter Chat.', true);
        }
        return new Response('ignored');
      }
      return handleStudioTrendCallback(env, callback, chatId, studioMatch);
    }

    const typedSelection = parseStudioTrendNumbers(update.message?.text);
    if (typedSelection.length && chatId && chatId === String(env.TELEGRAM_CHAT_ID)) {
      const handled = await handleStudioTypedSelection(env, chatId, typedSelection);
      if (handled) return new Response('ok');
    }

    const selectionId = selectionFromCallback(callbackData);
    if (!selectionId || !chatId || chatId !== String(env.TELEGRAM_CHAT_ID)) {
      return v2.fetch(request, env);
    }

    const activeSelection = await selectionIsActive(env, selectionId);
    if (activeSelection) {
      const selectMatch = callbackData.match(/^select_trend:([A-Za-z0-9_-]{4,40}):([1-5])$/);
      if (selectMatch) {
        return handleTrendPreview(env, callback, chatId, selectMatch[1], selectMatch[2]);
      }
      return v2.fetch(request, env);
    }

    if (callback?.id) {
      await telegramMethod(env, 'answerCallbackQuery', {
        callback_query_id: callback.id,
        text: 'Diese Auswahl ist veraltet. Nutze die neueste Rangliste.',
        show_alert: false,
      });
    }
    if (callback?.message?.message_id) {
      await telegramMethod(env, 'editMessageReplyMarkup', {
        chat_id: chatId,
        message_id: callback.message.message_id,
        reply_markup: { inline_keyboard: [] },
      });
    }

    return new Response('stale trend selection', { status: 409 });
  },
};

async function handleStudioTrendCallback(env, callback, chatId, match) {
  const callbackId = String(callback?.id || '').trim();
  const messageId = Number(callback?.message?.message_id || 0);
  const [, action, sessionId, numberText] = match;

  try {
    let loaded = await loadStudioState(env);
    const state = loaded.state;
    const session = state?.trend_selection;
    if (!session || String(session.session_id || '') !== sessionId) {
      if (callbackId) await answerStudioCallback(env, callbackId, 'Diese Trendauswahl ist nicht mehr aktuell.', true);
      return new Response('stale studio trend selection', { status: 409 });
    }

    const status = String(session.status || '').toUpperCase();
    if (status !== 'PENDING') {
      if (callbackId) await answerStudioCallback(env, callbackId, `Trendauswahl bereits verarbeitet: ${status}.`);
      if (messageId) await clearStudioKeyboard(env, chatId, messageId);
      return new Response('studio trend already processed');
    }

    if (action === 'toggle') {
      const number = Number(numberText || 0);
      if (!Number.isInteger(number) || number < 1 || number > 5) {
        if (callbackId) await answerStudioCallback(env, callbackId, 'Ungültige Trendnummer.', true);
        return new Response('invalid trend number', { status: 400 });
      }
      const selected = new Set((Array.isArray(session.selected) ? session.selected : []).map(Number));
      if (selected.has(number)) selected.delete(number);
      else selected.add(number);
      session.selected = [...selected].filter(value => value >= 1 && value <= 5).sort((a, b) => a - b);
      session.updated_at = new Date().toISOString();
      loaded = await saveStudioState(env, state, loaded.sha, `Update Telegram trend selection ${sessionId}`);
      await refreshStudioTrendMessage(env, chatId, session, messageId);
      if (callbackId) await answerStudioCallback(env, callbackId, 'Auswahl aktualisiert.');
      return new Response('ok');
    }

    if (action === 'reset') {
      session.selected = [];
      session.updated_at = new Date().toISOString();
      loaded = await saveStudioState(env, state, loaded.sha, `Reset Telegram trend selection ${sessionId}`);
      await refreshStudioTrendMessage(env, chatId, session, messageId);
      if (callbackId) await answerStudioCallback(env, callbackId, 'Auswahl zurückgesetzt.');
      return new Response('ok');
    }

    const selected = [...new Set((Array.isArray(session.selected) ? session.selected : []).map(Number))]
      .filter(value => value >= 1 && value <= 5)
      .sort((a, b) => a - b);
    if (!selected.length) {
      if (callbackId) await answerStudioCallback(env, callbackId, 'Bitte zuerst mindestens einen Trend auswählen.', true);
      return new Response('no trend selected', { status: 409 });
    }

    session.status = 'RELEASING';
    session.released_at = new Date().toISOString();
    session.dispatches = session.dispatches && typeof session.dispatches === 'object' ? session.dispatches : {};
    loaded = await saveStudioState(env, state, loaded.sha, `Lock Telegram trend release ${sessionId}`);

    const candidates = new Map(
      (Array.isArray(session.candidates) ? session.candidates : [])
        .filter(candidate => candidate && typeof candidate === 'object')
        .map(candidate => [Number(candidate.number || 0), candidate]),
    );
    const failures = [];
    for (const number of selected) {
      const candidate = candidates.get(number);
      if (!candidate || !String(candidate.topic || '').trim()) {
        failures.push(`${number}: Kandidat fehlt`);
        session.dispatches[String(number)] = {
          status: 'FAILED',
          error: 'candidate missing',
          failed_at: new Date().toISOString(),
        };
        continue;
      }
      try {
        await dispatchStudioTrend(env, candidate, session);
        session.dispatches[String(number)] = {
          status: 'DISPATCHED',
          topic: String(candidate.topic || '').trim(),
          dispatched_at: new Date().toISOString(),
        };
      } catch (error) {
        const detail = String(error).slice(0, 300);
        failures.push(`${number}: ${detail}`);
        session.dispatches[String(number)] = {
          status: 'FAILED',
          topic: String(candidate.topic || '').trim(),
          error: detail,
          failed_at: new Date().toISOString(),
        };
      }
    }

    session.status = failures.length ? 'PARTIAL_FAILURE' : 'DISPATCHED';
    session.completed_at = new Date().toISOString();
    await saveStudioState(env, state, loaded.sha, `Complete Telegram trend release ${sessionId}`);

    if (callbackId) {
      await answerStudioCallback(
        env,
        callbackId,
        failures.length ? 'Freigabe verarbeitet; mindestens ein Request ist fehlgeschlagen.' : 'Trend freigegeben. Request-Workflow gestartet.',
        Boolean(failures.length),
      );
    }
    if (messageId) await clearStudioKeyboard(env, chatId, messageId);

    const topics = selected
      .map(number => String(candidates.get(number)?.topic || '').trim())
      .filter(Boolean);
    let confirmation = [
      '✅ Trend freigegeben.',
      '',
      `Auswahl: ${selected.join(', ')}`,
      ...topics.map(topic => `• ${topic}`),
      '',
      'Der Request-Workflow wurde gestartet.',
    ].join('\n');
    if (failures.length) confirmation += `\n\n⚠️ Fehler:\n${failures.join('\n')}`;
    await sendStudioMessage(env, chatId, confirmation);
    return new Response(failures.length ? 'partial failure' : 'ok', { status: failures.length ? 207 : 200 });
  } catch (error) {
    console.error('studio trend callback failed', String(error));
    if (callbackId) await answerStudioCallback(env, callbackId, 'Trend-Aktion fehlgeschlagen.', true);
    await sendStudioMessage(env, chatId, `❌ Trend-Aktion fehlgeschlagen: ${String(error).slice(0, 500)}`);
    return new Response('studio trend callback failed', { status: 502 });
  }
}

async function handleStudioTypedSelection(env, chatId, numbers) {
  try {
    const loaded = await loadStudioState(env);
    const state = loaded.state;
    const session = state?.trend_selection;
    if (!session || String(session.status || '').toUpperCase() !== 'PENDING') return false;
    session.selected = [...new Set(numbers)].sort((a, b) => a - b);
    session.updated_at = new Date().toISOString();
    await saveStudioState(env, state, loaded.sha, `Set Telegram trend selection ${session.session_id || ''}`);
    await refreshStudioTrendMessage(env, chatId, session, Number(session.message_id || 0));
    await sendStudioMessage(
      env,
      chatId,
      `🟡 Auswahl ${session.selected.join(', ')} vorgemerkt. Noch kein Workflow gestartet – bitte jetzt „Trend freigeben“ klicken.`,
    );
    return true;
  } catch (error) {
    console.error('studio typed trend selection failed', String(error));
    return false;
  }
}

function parseStudioTrendNumbers(value) {
  const text = String(value || '').trim().toLowerCase();
  if (!text) return [];
  const normalized = text
    .replace(/\b(?:und|and)\b/g, ',')
    .replace(/[+&;/|]/g, ',')
    .replace(/\s+/g, ',');
  if (!/^,*[1-5](?:,*[1-5])*,*$/.test(normalized)) return [];
  return [...new Set((normalized.match(/[1-5]/g) || []).map(Number))].sort((a, b) => a - b);
}

function studioTrendText(session) {
  const selected = new Set((Array.isArray(session.selected) ? session.selected : []).map(Number));
  const lines = ['🔥 TAYVORIQ – Trendauswahl', ''];
  for (const candidate of Array.isArray(session.candidates) ? session.candidates : []) {
    const number = Number(candidate?.number || 0);
    const marker = selected.has(number) ? '✅' : `${number}️⃣`;
    lines.push(`${marker} ${String(candidate?.topic || '').trim()}`);
  }
  lines.push(
    '',
    `Ausgewählt: ${selected.size ? [...selected].sort((a, b) => a - b).join(', ') : 'noch nichts'}`,
    '',
    'Nummer(n) senden oder unten auswählen. Erst „Trend freigeben“ startet den Request-Workflow.',
  );
  return lines.join('\n');
}

function studioTrendKeyboard(session) {
  const sessionId = String(session.session_id || '').replace(/[^A-Za-z0-9_-]/g, '').slice(0, 32);
  const selected = new Set((Array.isArray(session.selected) ? session.selected : []).map(Number));
  const numberRow = [];
  for (let number = 1; number <= 5; number += 1) {
    numberRow.push({
      text: selected.has(number) ? `✅ ${number}` : String(number),
      callback_data: `tayvoriq:trend:toggle:${sessionId}:${number}`,
    });
  }
  return {
    inline_keyboard: [
      numberRow,
      [
        { text: '✅ Trend freigeben', callback_data: `tayvoriq:trend:approve:${sessionId}` },
        { text: '✏️ Auswahl ändern', callback_data: `tayvoriq:trend:reset:${sessionId}` },
      ],
    ],
  };
}

async function refreshStudioTrendMessage(env, chatId, session, messageId) {
  const target = Number(messageId || session.message_id || 0);
  const payload = {
    chat_id: chatId,
    text: studioTrendText(session),
    disable_web_page_preview: true,
    reply_markup: studioTrendKeyboard(session),
  };
  if (target) payload.message_id = target;
  const method = target ? 'editMessageText' : 'sendMessage';
  const response = await telegramMethod(env, method, payload);
  if (!response.ok) {
    const detail = await response.text();
    if (!detail.includes('message is not modified')) throw new Error(`Telegram ${method} ${response.status}: ${detail.slice(0, 250)}`);
  }
}

async function clearStudioKeyboard(env, chatId, messageId) {
  if (!messageId) return;
  await telegramMethod(env, 'editMessageReplyMarkup', {
    chat_id: chatId,
    message_id: messageId,
    reply_markup: { inline_keyboard: [] },
  });
}

async function answerStudioCallback(env, callbackId, text, alert = false) {
  if (!callbackId) return;
  await telegramMethod(env, 'answerCallbackQuery', {
    callback_query_id: callbackId,
    text: String(text || '').slice(0, 190),
    show_alert: Boolean(alert),
  });
}

async function sendStudioMessage(env, chatId, text) {
  const response = await telegramMethod(env, 'sendMessage', {
    chat_id: chatId,
    text: String(text || '').slice(0, 4000),
    disable_web_page_preview: true,
  });
  if (!response.ok) throw new Error(`Telegram sendMessage failed: ${response.status}`);
}

function studioGithubHeaders(env) {
  return {
    Authorization: `Bearer ${env.GITHUB_TOKEN}`,
    Accept: 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
    'User-Agent': 'tayvoriq-telegram-approval',
    'Content-Type': 'application/json',
  };
}

function decodeGithubContent(value) {
  const binary = atob(String(value || '').replace(/\n/g, ''));
  const bytes = Uint8Array.from(binary, character => character.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}

function encodeGithubContent(value) {
  const bytes = new TextEncoder().encode(String(value || ''));
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}

async function loadStudioState(env) {
  const url = `https://api.github.com/repos/${STUDIO_REPOSITORY}/contents/${STUDIO_STATE_PATH}?ref=main`;
  const response = await fetch(url, { headers: studioGithubHeaders(env) });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`Studio-State nicht erreichbar: GitHub ${response.status} ${detail.slice(0, 180)}`);
  }
  const payload = await response.json();
  let state;
  try {
    state = JSON.parse(decodeGithubContent(payload.content));
  } catch (error) {
    throw new Error(`Studio-State ungültig: ${String(error)}`);
  }
  return { state, sha: String(payload.sha || '') };
}

async function saveStudioState(env, state, sha, message) {
  state.last_checked_at = new Date().toISOString();
  const url = `https://api.github.com/repos/${STUDIO_REPOSITORY}/contents/${STUDIO_STATE_PATH}`;
  const response = await fetch(url, {
    method: 'PUT',
    headers: studioGithubHeaders(env),
    body: JSON.stringify({
      message,
      content: encodeGithubContent(`${JSON.stringify(state, null, 2)}\n`),
      sha,
      branch: 'main',
    }),
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`Studio-State konnte nicht gespeichert werden: GitHub ${response.status} ${detail.slice(0, 220)}`);
  }
  const payload = await response.json();
  return { state, sha: String(payload?.content?.sha || '') };
}

async function dispatchStudioTrend(env, candidate, session) {
  const url = `https://api.github.com/repos/${STUDIO_REPOSITORY}/actions/workflows/${STUDIO_TREND_WORKFLOW}/dispatches`;
  const response = await fetch(url, {
    method: 'POST',
    headers: studioGithubHeaders(env),
    body: JSON.stringify({
      ref: 'main',
      inputs: {
        trend_mode: 'manual_topic',
        trend_scope: String(candidate.scope || 'auto_scope'),
        topic: String(candidate.topic || '').trim(),
        language: String(session.language || 'Deutsch'),
        platform: String(session.platform || 'youtube_tiktok'),
        target_duration: String(Number(session.target_duration || 35)),
        llm_provider: String(session.llm_provider || 'auto'),
        telegram_notify: 'true',
      },
    }),
  });
  if (response.status !== 204) {
    const detail = await response.text();
    throw new Error(`Workflow-Dispatch GitHub ${response.status}: ${detail.slice(0, 220)}`);
  }
}

async function handleTrendPreview(env, callback, chatId, selectionId, trendId) {
  const snapshot = await selectionSnapshot(env, selectionId);
  if (!snapshot || snapshot.superseded === true) {
    if (callback?.id) {
      await telegramMethod(env, 'answerCallbackQuery', {
        callback_query_id: callback.id,
        text: 'Diese Auswahl wurde ersetzt. Nutze die neueste Rangliste.',
        show_alert: false,
      });
    }
    return new Response('stale trend selection', { status: 409 });
  }

  const trend = (Array.isArray(snapshot.trends) ? snapshot.trends : [])
    .find(item => String(item?.id || '') === String(trendId));
  if (!trend) return v2.fetch(new Request('https://fallback.invalid', { method: 'GET' }), env);

  if (callback?.id) {
    await telegramMethod(env, 'answerCallbackQuery', {
      callback_query_id: callback.id,
      text: `Trend ${trendId} ausgewählt.`,
      show_alert: false,
    });
  }

  const payload = {
    chat_id: chatId,
    text: selectedTrendBody(trend),
    disable_web_page_preview: true,
    reply_markup: trendConfirmationKeyboard(selectionId, trendId),
  };
  const messageId = callback?.message?.message_id;
  if (messageId) payload.message_id = messageId;
  const method = messageId ? 'editMessageText' : 'sendMessage';
  const response = await telegramMethod(env, method, payload);
  return response.ok ? new Response('ok') : new Response('telegram preview failed', { status: 502 });
}

function selectedTrendBody(trend) {
  const criteria = trend?.criteria || {};
  const labels = [
    ['Aktualität', criteria.aktualitaet],
    ['Viralität', criteria.viralitaet],
    ['TAYVORIQ', criteria.tayvoriq_passung],
    ['Quellen', criteria.quellenqualitaet],
    ['Visuals', criteria.visuell],
  ].filter(([, value]) => Number.isFinite(Number(value)));

  const lines = [
    '🟣 TAYVORIQ Trend ausgewählt',
    '',
    `Ausgewählt: ${trend?.id || ''}`,
    `Thema: ${trend?.title || ''}`,
    `Gesamtscore: ${trend?.score || 0} %`,
  ];
  if (labels.length) lines.push('', labels.map(([label, value]) => `${label} ${value}%`).join(' · '));

  const sources = Array.isArray(trend?.sources) ? trend.sources.slice(0, 3) : [];
  const sourceLines = sources.map(formatSource).filter(Boolean);
  if (sourceLines.length) lines.push('', 'Geprüfte Quellen:', ...sourceLines);

  lines.push('', 'Erst der folgende Button startet verbindlich die Produktion.');
  return lines.join('\n');
}

function formatSource(source, index) {
  if (typeof source === 'string') return source.trim();
  if (!source || typeof source !== 'object') return '';
  const publisher = String(source.publisher || source.name || `Quelle ${index + 1}`).trim();
  const url = String(source.url || source.uri || '').trim();
  if (publisher && url) return `• ${publisher}: ${url}`;
  if (url) return `• ${url}`;
  if (publisher) return `• ${publisher}`;
  return '';
}

function trendConfirmationKeyboard(selectionId, trendId) {
  return {
    inline_keyboard: [
      [{ text: '✅ Trend freigeben', callback_data: `approve_trend:${selectionId}:${trendId}` }],
      [
        { text: '↩️ Anderen Trend wählen', callback_data: `trend_list:${selectionId}` },
        { text: '❌ Ablehnen', callback_data: `reject_trend:${selectionId}:${trendId}` },
      ],
    ],
  };
}

function selectionFromCallback(callbackData) {
  const patterns = [
    /^select_trend:([A-Za-z0-9_-]{4,40}):[1-5]$/,
    /^trend_list:([A-Za-z0-9_-]{4,40})$/,
    /^trend_reason:(?:newtrend|newformat):([A-Za-z0-9_-]{4,40}):[1-5]$/i,
    /^approve_trend:([A-Za-z0-9_-]{4,40}):[1-5]$/i,
    /^reject_trend:([A-Za-z0-9_-]{4,40}):[1-5]$/i,
  ];
  for (const pattern of patterns) {
    const match = callbackData.match(pattern);
    if (match?.[1]) return match[1];
  }
  return '';
}

export async function selectionIsActive(env, selectionId) {
  const requested = await selectionSnapshot(env, selectionId);
  if (requested?.superseded === true) return false;

  if (await selectionIsManifested(env, selectionId)) return true;

  const current = await currentSelection(env);
  const currentId = String(current?.selection_id || '').trim();
  if (!currentId || currentId === selectionId) return true;

  if (!requested) return false;
  const requestedDate = String(requested.target_date || requested.date || '').trim();
  const currentDate = String(current.target_date || current.date || '').trim();
  const requestedSlot = String(requested.slot || '').trim();
  const currentSlot = String(current.slot || '').trim();
  return Boolean(
    requestedDate
    && currentDate
    && requestedDate === currentDate
    && ['morning', 'evening'].includes(requestedSlot)
    && ['morning', 'evening'].includes(currentSlot)
    && requestedSlot !== currentSlot
  );
}

async function selectionIsManifested(env, selectionId) {
  const repository = env.GITHUB_REPOSITORY || 'mojo72549-arch/tayvoriq-control-plane';
  try {
    const response = await fetch(
      `https://raw.githubusercontent.com/${repository}/main/state/tayvoriq-active-trend-selections.json`,
      { headers: { 'User-Agent': 'tayvoriq-telegram-approval' } },
    );
    if (!response.ok) return false;
    const manifest = await response.json();
    const activeIds = Array.isArray(manifest?.active_selection_ids)
      ? manifest.active_selection_ids.map(value => String(value || '').trim())
      : [];
    const expiresAt = Date.parse(String(manifest?.expires_at || ''));
    if (!activeIds.includes(selectionId) || !Number.isFinite(expiresAt) || expiresAt <= Date.now()) {
      return false;
    }
    const requested = await selectionSnapshot(env, selectionId);
    if (!requested || requested.superseded === true) return false;
    const manifestDate = String(manifest?.target_date || '').trim();
    const requestedDate = String(requested.target_date || requested.date || '').trim();
    return Boolean(manifestDate && manifestDate === requestedDate);
  } catch (error) {
    console.error('active selection manifest lookup failed', String(error));
    return false;
  }
}

async function currentSelection(env) {
  const repository = env.GITHUB_REPOSITORY || 'mojo72549-arch/tayvoriq-control-plane';
  try {
    const response = await fetch(
      `https://raw.githubusercontent.com/${repository}/main/.github/run-now/tayvoriq-trend-request.json`,
      { headers: { 'User-Agent': 'tayvoriq-telegram-approval' } },
    );
    if (!response.ok) return null;
    return await response.json();
  } catch (error) {
    console.error('current selection lookup failed', String(error));
    return null;
  }
}

async function selectionSnapshot(env, selectionId) {
  const repository = env.GITHUB_REPOSITORY || 'mojo72549-arch/tayvoriq-control-plane';
  try {
    const response = await fetch(
      `https://raw.githubusercontent.com/${repository}/main/.automation/tayvoriq-agent-v2/selections/${selectionId}.json`,
      { headers: { 'User-Agent': 'tayvoriq-telegram-approval' } },
    );
    if (!response.ok) return null;
    const data = await response.json();
    return String(data?.selection_id || '').trim() === selectionId ? data : null;
  } catch (error) {
    console.error('selection snapshot lookup failed', String(error));
    return null;
  }
}

async function telegramMethod(env, method, payload) {
  const response = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/${method}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    console.error(`Telegram ${method} failed`, response.status, await response.text());
  }
  return response;
}
