import v6 from './telegram-approval-worker-v6.js';

const REPOSITORY = 'mojo72549-arch/tayvoriq-control-plane';
const MODES = new Set(['STANDARD', 'CINEMATIC', 'MIXED']);
const LEGACY_APPROVE_RE = /^approve_trend:([A-Za-z0-9_-]{4,40}):([1-5])$/;
const LEGACY_MODE_RE = /^tvq:l:m:([A-Za-z0-9_-]{4,40}):([1-5]):(STANDARD|CINEMATIC|MIXED)$/;
const LEGACY_RELEASE_RE = /^tvq:l:r:([A-Za-z0-9_-]{4,40}):([1-5]):(STANDARD|CINEMATIC|MIXED)$/;

export default {
  async fetch(request, env) {
    if (request.method !== 'POST') return v6.fetch(request, env);
    const secret = request.headers.get('X-Telegram-Bot-Api-Secret-Token') || '';
    if (!env.TELEGRAM_WEBHOOK_SECRET || secret !== env.TELEGRAM_WEBHOOK_SECRET) return v6.fetch(request, env);

    let update;
    try { update = await request.clone().json(); }
    catch { return v6.fetch(request, env); }

    const callback = update?.callback_query;
    const data = String(callback?.data || '').trim();
    const chatId = String(callback?.message?.chat?.id || '');
    if (!callback || !data) return v6.fetch(request, env);
    if (!chatId || chatId !== String(env.TELEGRAM_CHAT_ID)) return v6.fetch(request, env);

    let match = data.match(LEGACY_APPROVE_RE);
    if (match) return showModeChooser(env, callback, chatId, match[1], match[2]);

    match = data.match(LEGACY_MODE_RE);
    if (match) return selectMode(env, callback, chatId, match[1], match[2], match[3]);

    match = data.match(LEGACY_RELEASE_RE);
    if (match) return releaseLegacyTrend(env, callback, chatId, match[1], match[2], match[3]);

    return v6.fetch(request, env);
  },
};

async function showModeChooser(env, callback, chatId, selectionId, trendId) {
  const requestData = await loadTrendRequest(selectionId);
  validateSelection(requestData, selectionId);
  const trend = findTrend(requestData, trendId);
  if (callback?.id) await answerCallback(env, callback.id, 'Jetzt Visual Mode wählen. Noch keine Produktion gestartet.');
  await editMessage(env, chatId, callback?.message?.message_id, modePrompt(trend, ''), modeKeyboard(selectionId, trendId, ''));
  return new Response('ok', { status: 200 });
}

async function selectMode(env, callback, chatId, selectionId, trendId, mode) {
  if (!MODES.has(mode)) return new Response('unsupported mode', { status: 400 });
  const requestData = await loadTrendRequest(selectionId);
  validateSelection(requestData, selectionId);
  const trend = findTrend(requestData, trendId);
  if (callback?.id) await answerCallback(env, callback.id, `${modeLabel(mode)} gewählt. Noch nicht gestartet.`);
  await editMessage(env, chatId, callback?.message?.message_id, modePrompt(trend, mode), releaseKeyboard(selectionId, trendId, mode));
  return new Response('ok', { status: 200 });
}

async function releaseLegacyTrend(env, callback, chatId, selectionId, trendId, mode) {
  if (!MODES.has(mode)) return new Response('unsupported mode', { status: 400 });
  const requestData = await loadTrendRequest(selectionId);
  validateSelection(requestData, selectionId);
  const trend = findTrend(requestData, trendId);
  const result = await enqueueRelay(env, requestData, trend, selectionId, trendId, mode);

  if (callback?.id) {
    await answerCallback(env, callback.id, result.existed ? 'Dieser Auftrag ist bereits eingereiht.' : 'Trend freigegeben und sicher eingereiht.');
  }
  if (callback?.message?.message_id) await clearKeyboard(env, chatId, callback.message.message_id);

  const text = [
    '✅ TAYVORIQ · Trend verbindlich freigegeben',
    '',
    `Thema: ${String(trend.title || '').trim()}`,
    `Modus: ${modeLabel(mode)}`,
    `Zieldauer: ${targetDuration(mode)} Sekunden`,
    '',
    result.existed
      ? 'Der identische Auftrag war bereits in der Produktions-Queue. Es wurde kein Doppel-Run angelegt.'
      : 'Der Auftrag liegt jetzt in derselben sicheren Produktions-Queue wie die neue Trendauswahl.',
    '',
    mode === 'STANDARD'
      ? 'Nächster Schritt: bewährte normale Trendstrecke.'
      : 'Nächster Schritt: Fakten/Skript/Voice → Full Cinematic → Vision-QA → Review-Master.',
  ].join('\n');
  await sendMessage(env, chatId, text);
  return new Response('ok', { status: 200 });
}

function modePrompt(trend, selectedMode) {
  const mode = selectedMode ? modeLabel(selectedMode) : 'noch nicht gewählt';
  return [
    '🎛 TAYVORIQ · Produktionsmodus',
    '',
    `Trend ${trend.id}: ${String(trend.title || '').trim()}`,
    `Score: ${trend.score ?? '—'} %`,
    '',
    `Visual Mode: ${mode}`,
    '',
    '⚡ Standard · bewährte normale Trendstrecke',
    '🎬 Cinematic · 6–8 zusammenhängende Premium-Shots, ≥2 Hero-Shots',
    '🔥 Mixed · echte/relevante Assets + Premium-Hero-Shots',
    '',
    selectedMode
      ? 'Erst „✅ Trend freigeben“ startet verbindlich die Produktion.'
      : 'Wähle zuerst den Modus. Es wurde noch nichts gestartet.',
  ].join('\n');
}

function modeKeyboard(selectionId, trendId, selected) {
  const button = (label, mode) => ({
    text: `${selected === mode ? '✅ ' : ''}${label}`,
    callback_data: `tvq:l:m:${selectionId}:${trendId}:${mode}`,
  });
  return {
    inline_keyboard: [
      [button('⚡ Standard', 'STANDARD')],
      [button('🎬 Cinematic', 'CINEMATIC')],
      [button('🔥 Mixed', 'MIXED')],
      [{ text: '↩️ Anderen Trend wählen', callback_data: `trend_list:${selectionId}` }],
    ],
  };
}

function releaseKeyboard(selectionId, trendId, mode) {
  const keyboard = modeKeyboard(selectionId, trendId, mode).inline_keyboard;
  return {
    inline_keyboard: [
      [{ text: '✅ Trend freigeben', callback_data: `tvq:l:r:${selectionId}:${trendId}:${mode}` }],
      ...keyboard,
    ],
  };
}

function validateSelection(requestData, selectionId) {
  if (String(requestData?.selection_id || '') !== selectionId) throw new Error('stale trend selection');
  const deadline = requestData?.decision_deadline || requestData?.expires_at || requestData?.valid_until;
  if (deadline) {
    const ts = Date.parse(String(deadline));
    if (Number.isFinite(ts) && Date.now() > ts) throw new Error('trend selection expired');
  }
}

function findTrend(requestData, trendId) {
  const trend = (Array.isArray(requestData?.trends) ? requestData.trends : []).find(item => String(item?.id) === String(trendId));
  if (!trend || !String(trend.title || '').trim()) throw new Error(`trend ${trendId} not found`);
  return trend;
}

async function loadTrendRequest(selectionId) {
  const paths = [
    `.automation/tayvoriq-agent-v2/selections/${selectionId}.json`,
    '.github/run-now/tayvoriq-trend-request.json',
  ];
  let last = 404;
  for (const path of paths) {
    const response = await fetch(`https://raw.githubusercontent.com/${REPOSITORY}/main/${path}`, {
      headers: { 'User-Agent': 'tayvoriq-telegram-legacy-mode-bridge' },
    });
    last = response.status;
    if (!response.ok) continue;
    const data = await response.json();
    if (String(data?.selection_id || '') === selectionId) return data;
  }
  throw new Error(`trend request HTTP ${last} for ${selectionId}`);
}

async function enqueueRelay(env, requestData, trend, selectionId, trendId, mode) {
  const path = `queue/trend-relay/legacy-${selectionId}-${trendId}-${mode.toLowerCase()}.json`;
  const api = `https://api.github.com/repos/${REPOSITORY}/contents/${path}`;
  const headers = ghHeaders(env);
  const existing = await fetch(`${api}?ref=main`, { headers });
  if (existing.ok) return { path, existed: true };
  if (existing.status !== 404) throw new Error(`queue preflight GitHub ${existing.status}`);

  const payload = {
    session_id: `legacy-${selectionId}`,
    candidate_number: Number(trendId),
    trend_mode: 'manual_topic',
    trend_scope: String(trend.scope || requestData?.trend_scope || requestData?.scope || 'auto_scope'),
    topic: String(trend.title || '').trim(),
    language: String(requestData?.language || 'Deutsch'),
    platform: String(requestData?.platform || 'youtube_tiktok'),
    target_duration: String(targetDuration(mode)),
    llm_provider: String(requestData?.llm_provider || 'auto'),
    telegram_notify: 'true',
    visual_mode: mode,
    production_policy: productionPolicy(mode),
    queued_at: new Date().toISOString(),
    source: 'telegram-agent-v2-visual-mode-bridge-v7',
    source_selection_id: selectionId,
    source_trend_id: String(trendId),
  };

  const body = {
    message: `Queue legacy Telegram trend ${selectionId} #${trendId} ${mode}`,
    content: encodeContent(`${JSON.stringify(payload, null, 2)}\n`),
    branch: 'main',
  };
  const response = await fetch(api, { method: 'PUT', headers, body: JSON.stringify(body) });
  if (response.status === 201 || response.status === 200) return { path, existed: false };
  const detail = (await response.text()).slice(0, 260);
  throw new Error(`relay queue GitHub ${response.status}: ${detail}`);
}

function productionPolicy(mode) {
  const common = { allow_real_footage:true, allow_stock:true, allow_generated_video:true, cohesion_min:80, audio_min:82 };
  if (mode === 'CINEMATIC') return { ...common, min_shots:6, max_shots:8, min_hero_shots:2, final_quality_min:85 };
  if (mode === 'MIXED') return { ...common, min_shots:6, max_shots:8, min_hero_shots:1, final_quality_min:82 };
  return { ...common, min_shots:4, max_shots:8, min_hero_shots:0, final_quality_min:78 };
}

function targetDuration(mode) {
  if (mode === 'CINEMATIC') return 22;
  if (mode === 'MIXED') return 25;
  return 35;
}

function modeLabel(mode) {
  return ({ STANDARD:'⚡ Standard', CINEMATIC:'🎬 Cinematic', MIXED:'🔥 Mixed' })[mode] || mode;
}

function ghHeaders(env) {
  return {
    Authorization: `Bearer ${env.GITHUB_TOKEN}`,
    Accept: 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
    'User-Agent': 'tayvoriq-telegram-legacy-mode-bridge',
    'Content-Type': 'application/json',
  };
}

function encodeContent(value) {
  const bytes = new TextEncoder().encode(String(value || ''));
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}

async function editMessage(env, chatId, messageId, text, replyMarkup) {
  if (!messageId) return sendMessage(env, chatId, text, replyMarkup);
  const response = await telegramMethod(env, 'editMessageText', {
    chat_id: chatId,
    message_id: messageId,
    text,
    disable_web_page_preview: true,
    reply_markup: replyMarkup,
  });
  if (!response.ok) throw new Error(`Telegram editMessageText ${response.status}`);
  return response;
}

async function sendMessage(env, chatId, text, replyMarkup = undefined) {
  const payload = { chat_id: chatId, text, disable_web_page_preview: true };
  if (replyMarkup) payload.reply_markup = replyMarkup;
  const response = await telegramMethod(env, 'sendMessage', payload);
  if (!response.ok) throw new Error(`Telegram sendMessage ${response.status}`);
  return response;
}

async function clearKeyboard(env, chatId, messageId) {
  await telegramMethod(env, 'editMessageReplyMarkup', {
    chat_id: chatId,
    message_id: messageId,
    reply_markup: { inline_keyboard: [] },
  });
}

async function answerCallback(env, callbackId, text) {
  await telegramMethod(env, 'answerCallbackQuery', {
    callback_query_id: callbackId,
    text: String(text || '').slice(0, 190),
    show_alert: false,
  });
}

function telegramMethod(env, method, payload) {
  return fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/${method}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}
