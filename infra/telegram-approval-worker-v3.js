import v2 from './telegram-approval-worker-v2.js';

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
