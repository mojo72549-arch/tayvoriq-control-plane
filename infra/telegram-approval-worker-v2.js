export default {
  async fetch(request, env) {
    if (request.method !== 'POST') return new Response('ok');

    const suppliedSecret = request.headers.get('X-Telegram-Bot-Api-Secret-Token') || '';
    if (!env.TELEGRAM_WEBHOOK_SECRET || suppliedSecret !== env.TELEGRAM_WEBHOOK_SECRET) {
      return new Response('unauthorized', { status: 401 });
    }

    let update;
    try {
      update = await request.json();
    } catch {
      return new Response('invalid json', { status: 400 });
    }

    const callback = update.callback_query;
    const message = update.message || callback?.message;
    const callbackData = String(callback?.data || '').trim();
    const text = String(update.message?.text || callbackData || '').trim();
    const messageText = String(message?.text || message?.caption || '');
    const chatId = String(message?.chat?.id || '');

    if (!chatId || chatId !== String(env.TELEGRAM_CHAT_ID)) {
      if (callback?.id) await answerCallback(env, callback.id, 'Nicht autorisiert.');
      return new Response('ignored');
    }

    const selectTrend = callbackData.match(/^select_trend:([A-Za-z0-9_-]{4,40}):([1-5])$/);
    if (selectTrend) {
      const selectionId = selectTrend[1];
      const trendId = selectTrend[2];
      if (callback?.id) await answerCallback(env, callback.id, `Trend ${trendId} ausgewählt.`);

      let requestData;
      try {
        requestData = await loadTrendRequest(env);
      } catch (error) {
        await requireTelegramMessage(await telegram(env, chatId, `❌ Trendauswahl konnte nicht geladen werden.\nGrund: ${String(error).slice(0, 350)}`));
        return new Response('trend request unavailable', { status: 502 });
      }
      if (String(requestData?.selection_id || '') !== selectionId) {
        await requireTelegramMessage(await telegram(env, chatId, '⚠️ Diese Trendauswahl ist nicht mehr aktuell. Bitte nutze die neueste Abend-Rangliste.'));
        return new Response('stale trend selection', { status: 409 });
      }
      const trend = (requestData.trends || []).find(item => String(item.id) === trendId);
      if (!trend) {
        await requireTelegramMessage(await telegram(env, chatId, `❌ Trend ${trendId} ist in der aktuellen Rangliste nicht vorhanden.`));
        return new Response('trend not found', { status: 404 });
      }

      await requireTelegramMessage(await editMessageWithMarkup(
        env,
        chatId,
        callback?.message?.message_id,
        selectedTrendBody(trend),
        trendConfirmationKeyboard(selectionId, trendId),
      ));
      return new Response('ok');
    }

    const showTrendList = callbackData.match(/^trend_list:([A-Za-z0-9_-]{4,40})$/);
    if (showTrendList) {
      const selectionId = showTrendList[1];
      if (callback?.id) await answerCallback(env, callback.id, 'Rangliste geöffnet.');
      let requestData;
      try {
        requestData = await loadTrendRequest(env);
      } catch (error) {
        await requireTelegramMessage(await telegram(env, chatId, `❌ Trendauswahl konnte nicht geladen werden.\nGrund: ${String(error).slice(0, 350)}`));
        return new Response('trend request unavailable', { status: 502 });
      }
      if (String(requestData?.selection_id || '') !== selectionId) {
        await requireTelegramMessage(await telegram(env, chatId, '⚠️ Diese Trendauswahl ist nicht mehr aktuell. Bitte nutze die neueste Abend-Rangliste.'));
        return new Response('stale trend selection', { status: 409 });
      }
      await requireTelegramMessage(await editMessageWithMarkup(
        env,
        chatId,
        callback?.message?.message_id,
        trendListBody(requestData),
        trendSelectionKeyboard(selectionId),
      ));
      return new Response('ok');
    }

    const reasonMatch = callbackData.match(/^trend_reason:(newtrend|newformat):(\d+)$/i);
    if (reasonMatch) {
      const action = reasonMatch[1].toLowerCase();
      const trendId = reasonMatch[2];
      if (callback?.id) await answerCallback(env, callback.id, action === 'newtrend' ? 'Neuer Trend wird vorgeschlagen.' : 'Neues Format wird vorgeschlagen.');
      if (callback?.message?.message_id) await clearKeyboard(env, chatId, callback.message.message_id);

      let requestData;
      try {
        requestData = await loadTrendRequest(env);
      } catch (error) {
        await requireTelegramMessage(await telegram(env, chatId, `❌ Trend-Neuvorschlag fehlgeschlagen.\nGrund: ${String(error).slice(0, 350)}`));
        return new Response('trend request unavailable', { status: 502 });
      }

      const trends = Array.isArray(requestData?.trends) ? requestData.trends : [];
      const currentIndex = trends.findIndex(t => String(t.id) === trendId);
      if (currentIndex < 0 || trends.length === 0) {
        await requireTelegramMessage(await telegram(env, chatId, `❌ Trend ${trendId} ist in der aktuellen Rangliste nicht mehr vorhanden.`));
        return new Response('trend not found', { status: 404 });
      }

      if (action === 'newtrend') {
        const next = trends[(currentIndex + 1) % trends.length];
        const body = [
          '🔄 TAYVORIQ Alternativ-Trend', '',
          `Ausgewählt: ${next.id}`, `Thema: ${next.title}`, `Score: ${next.score} %`, '',
          'Grund berücksichtigt: bisheriges Thema abgelehnt.',
          'Erst mit „Trend freigeben“ startet die Produktion.'
        ].join('\n');
        await requireTelegramMessage(await telegramWithMarkup(env, chatId, body, trendKeyboard(String(next.id))));
        return new Response('ok');
      }

      const current = trends[currentIndex];
      const formatTopic = `${current.title} — als kompakter Erklär-Short mit Kontrast-Hook, 3 klaren Fakten und visueller Vorher/Nachher-Dramaturgie`;
      const body = [
        '🎬 TAYVORIQ Format-Alternative', '',
        `Ausgewählt: ${current.id}`, `Thema: ${formatTopic}`, '',
        'Grund berücksichtigt: Thema bleibt, Format wird neu aufgesetzt.',
        'Erst mit „Trend freigeben“ startet die Produktion.'
      ].join('\n');
      await requireTelegramMessage(await telegramWithMarkup(env, chatId, body, trendKeyboard(String(current.id))));
      return new Response('ok');
    }

    const trendApproval = parseTrendApproval(callbackData, text, messageText);
    if (trendApproval) {
      const { trendId, selectionId } = trendApproval;
      if (callback?.id) await answerCallback(env, callback.id, `Trend ${trendId} wird geprüft.`);

      let requestData;
      try {
        requestData = await loadTrendRequest(env);
      } catch (error) {
        await requireTelegramMessage(await telegram(env, chatId, `❌ Trendfreigabe konnte die aktuelle Rangliste nicht laden.\nGrund: ${String(error).slice(0, 350)}`));
        return new Response('trend request unavailable', { status: 502 });
      }
      const currentSelectionId = String(requestData?.selection_id || '');
      if ((currentSelectionId && selectionId !== currentSelectionId) || (!currentSelectionId && selectionId)) {
        await requireTelegramMessage(await telegram(env, chatId, '⚠️ Diese Trendfreigabe ist nicht mehr aktuell. Es wurde keine Produktion gestartet.'));
        return new Response('stale trend approval', { status: 409 });
      }
      const trend = (requestData.trends || []).find(item => String(item.id) === trendId);
      if (!trend || !String(trend.title || '').trim()) {
        await requireTelegramMessage(await telegram(env, chatId, `❌ Trend ${trendId} ist in der aktuellen Rangliste nicht vorhanden. Es wurde nichts gestartet.`));
        return new Response('trend not found', { status: 404 });
      }
      const topic = String(trend.title).trim();
      const dispatch = await githubDispatch(env, 'tayvoriq_trend_approved', {
        trend_id: trendId,
        topic,
        selection_id: currentSelectionId,
        telegram_chat_id: chatId,
        telegram_message_id: callback?.message?.message_id || null,
        approved_at: new Date().toISOString(),
      });
      if (!dispatch.ok) {
        const detail = await dispatch.text();
        await requireTelegramMessage(await telegram(env, chatId, `❌ TAYVORIQ 0 %\nTrendfreigabe konnte den X-Workflow nicht starten.\nGitHub-Fehler: ${dispatch.status}`));
        console.error('trend repository_dispatch failed', dispatch.status, detail);
        return new Response('dispatch failed', { status: 502 });
      }
      if (callback?.message?.message_id) await clearKeyboard(env, chatId, callback.message.message_id);
      await requireTelegramMessage(await telegram(env, chatId, `✅ TAYVORIQ 5 %\nTrend ${trendId} freigegeben.\nThema: ${topic || 'wird aus Trenddaten geladen'}\nX-Workflow wurde angefordert.\nNächster Schritt: Startbestätigung bei 10 %`));
      return new Response('ok');
    }

    const rejectTrend = callbackData.match(/^(?:reject_trend|trend_reject|reject:trend)[:_](\d+)$/i);
    if (rejectTrend) {
      const trendId = rejectTrend[1];
      if (callback?.id) await answerCallback(env, callback.id, `Trend ${trendId} abgelehnt.`);
      if (callback?.message?.message_id) await clearKeyboard(env, chatId, callback.message.message_id);
      await requireTelegramMessage(await telegramWithMarkup(env, chatId, `❌ Trend ${trendId} abgelehnt.\n\nWas ist der Hauptgrund?`, {
        inline_keyboard: [
          [{ text: '📰 Thema/Trend passt nicht', callback_data: `trend_reason:newtrend:${trendId}` }],
          [{ text: '🎬 Format passt nicht', callback_data: `trend_reason:newformat:${trendId}` }]
        ]
      }));
      return new Response('ok');
    }

    const rejectMatch = callbackData.match(/^tayvoriq:reject:(\d+)$/i)
      || text.match(/^ablehnen\s+(\d+)$/i)
      || text.match(/^reject:(\d+)$/i);
    if (rejectMatch) {
      const runId = rejectMatch[1];
      if (callback?.id) await answerCallback(env, callback.id, `Run ${runId} wurde abgelehnt.`);
      if (callback?.message?.message_id) await clearKeyboard(env, chatId, callback.message.message_id);
      await requireTelegramMessage(await telegram(env, chatId, `❌ Run ${runId} wurde abgelehnt. Es erfolgt kein YouTube-Upload.`));
      return new Response('ok');
    }

    const approveMatch = callbackData.match(/^tayvoriq:approve:(\d+)$/i)
      || text.match(/^freigeben\s+(\d+)$/i)
      || text.match(/^approve:(\d+)$/i);
    if (!approveMatch) {
      if (callback?.id) await answerCallback(env, callback.id, 'Unbekannte Aktion.');
      await requireTelegramMessage(await telegram(env, chatId, 'Aktion konnte nicht zugeordnet werden. Bitte nutze den aktuellen Freigeben-Button.'));
      return new Response('ok');
    }

    const runId = approveMatch[1];
    const base = `https://mojo72549-arch.github.io/mind-reset-daily/tayvoriq/runs/${runId}`;
    const youtubeVideoUrl = `${base}/short_youtube.mp4`;
    const tiktokVideoUrl = `${base}/short_tiktok.mp4`;
    const reviewUrl = `${base}/`;

    const [youtubeHead, tiktokHead] = await Promise.all([
      fetch(youtubeVideoUrl, { method: 'HEAD', redirect: 'follow' }),
      fetch(tiktokVideoUrl, { method: 'HEAD', redirect: 'follow' }),
    ]);
    if (!youtubeHead.ok || !tiktokHead.ok) {
      if (callback?.id) await answerCallback(env, callback.id, 'Plattform-Paket ist noch nicht vollständig erreichbar.');
      await requireTelegramMessage(await telegram(env, chatId, `❌ Review ${runId} ist noch nicht vollständig erreichbar. YouTube=${youtubeHead.status}, TikTok=${tiktokHead.status}. Keine Freigabe gespeichert.`));
      return new Response('platform package unavailable', { status: 409 });
    }

    const approval = await upsertApprovalRecord(env, {
      runId,
      youtubeVideoUrl,
      tiktokVideoUrl,
      reviewUrl,
      telegramMessageId: callback?.message?.message_id || null,
    });
    if (!approval.ok) {
      const detail = await approval.text();
      if (callback?.id) await answerCallback(env, callback.id, 'Freigabe konnte nicht gespeichert werden.');
      await requireTelegramMessage(await telegram(env, chatId, `❌ Freigabe für Run ${runId} konnte nicht gespeichert werden: ${approval.status}`));
      console.error('approval record write failed', approval.status, detail);
      return new Response('approval write failed', { status: 502 });
    }

    if (callback?.id) await answerCallback(env, callback.id, `Run ${runId} freigegeben.`);
    if (callback?.message?.message_id) await clearKeyboard(env, chatId, callback.message.message_id);
    await requireTelegramMessage(await telegram(env, chatId, `✅ Freigabe für Run ${runId} gespeichert. Der automatische YouTube-Upload startet jetzt. TikTok bleibt manuell; MP4 und Caption stehen im Review bereit.`));
    return new Response('ok');
  },
};

function trendKeyboard(trendId) {
  return { inline_keyboard: [[
    { text: '✅ Trend freigeben', callback_data: `approve_trend:${trendId}` },
    { text: '❌ Ablehnen', callback_data: `reject_trend:${trendId}` }
  ]] };
}

function trendSelectionKeyboard(selectionId) {
  return {
    inline_keyboard: [
      [
        { text: '1️⃣ Trend 1', callback_data: `select_trend:${selectionId}:1` },
        { text: '2️⃣ Trend 2', callback_data: `select_trend:${selectionId}:2` },
      ],
      [
        { text: '3️⃣ Trend 3', callback_data: `select_trend:${selectionId}:3` },
        { text: '4️⃣ Trend 4', callback_data: `select_trend:${selectionId}:4` },
      ],
      [{ text: '5️⃣ Trend 5', callback_data: `select_trend:${selectionId}:5` }],
    ],
  };
}

function trendConfirmationKeyboard(selectionId, trendId) {
  return {
    inline_keyboard: [
      [{ text: '✅ Trend freigeben', callback_data: `approve_trend:${selectionId}:${trendId}` }],
      [{ text: '↩️ Anderen Trend wählen', callback_data: `trend_list:${selectionId}` }],
    ],
  };
}

function trendListBody(requestData) {
  const lines = ['🌙 TAYVORIQ Abend-Trends', '', 'Rangliste:'];
  for (const trend of requestData.trends || []) {
    lines.push(`${trend.id}. ${trend.title} — ${trend.score} %`);
  }
  lines.push(
    '',
    'Schritt 1: Tippe auf eine Nummer.',
    'Schritt 2: Prüfe den Trend und tippe separat auf „Trend freigeben“.',
    '',
    'Vor dem zweiten Klick startet keine Produktion.',
  );
  return lines.join('\n');
}

function selectedTrendBody(trend) {
  const criteria = trend.criteria || {};
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
    `Ausgewählt: ${trend.id}`,
    `Thema: ${trend.title}`,
    `Gesamtscore: ${trend.score} %`,
  ];
  if (labels.length) lines.push('', labels.map(([label, value]) => `${label} ${value}%`).join(' · '));
  const sources = Array.isArray(trend.sources) ? trend.sources.slice(0, 3) : [];
  if (sources.length) lines.push('', 'Geprüfte Quellen:', ...sources);
  lines.push('', 'Erst der folgende Button startet verbindlich die Produktion.');
  return lines.join('\n');
}

function parseTrendApproval(callbackData, text, messageText) {
  const current = callbackData.match(/^approve_trend:([A-Za-z0-9_-]{4,40}):([1-5])$/);
  const explicit = callbackData.match(/^(?:approve_trend|trend_approve|trend:approve|approve:trend)[:_](\d+)$/i)
    || text.match(/^trend\s+freigeben\s+(\d+)$/i);
  let trendId = current?.[2] || explicit?.[1] || '';
  const selectionId = current?.[1] || '';
  if (!trendId && /^(?:approve|trend_approve|approve_trend)$/i.test(callbackData)) {
    const selected = messageText.match(/(?:ausgew[aä]hlt|selected|trend)\s*[:#-]?\s*([1-5])\b/i);
    trendId = selected?.[1] || '';
  }
  if (!trendId) return null;
  const topicPatterns = [
    new RegExp(`(?:^|\\n)\\s*${trendId}[.)-]\\s*([^\\n]+)`, 'i'),
    /(?:thema|topic)\s*:\s*([^\n]+)/i,
  ];
  let topic = '';
  for (const pattern of topicPatterns) {
    const match = messageText.match(pattern);
    if (match?.[1]) { topic = match[1].replace(/^[*\s]+|[*\s]+$/g, '').trim(); break; }
  }
  return { trendId, selectionId, topic };
}

async function loadTrendRequest(env) {
  const repository = env.GITHUB_REPOSITORY || 'mojo72549-arch/tayvoriq-control-plane';
  const response = await fetch(`https://raw.githubusercontent.com/${repository}/main/.github/run-now/tayvoriq-trend-request.json`, { headers: { 'User-Agent': 'tayvoriq-telegram-approval' } });
  if (!response.ok) throw new Error(`Trend request HTTP ${response.status}`);
  return response.json();
}

async function upsertApprovalRecord(env, { runId, youtubeVideoUrl, tiktokVideoUrl, reviewUrl, telegramMessageId }) {
  const repository = env.GITHUB_REPOSITORY || 'mojo72549-arch/tayvoriq-control-plane';
  const path = `.automation/tayvoriq-reviews/${runId}.json`;
  const apiUrl = `https://api.github.com/repos/${repository}/contents/${path}`;
  const headers = {
    Authorization: `Bearer ${env.GITHUB_TOKEN}`,
    Accept: 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
    'User-Agent': 'tayvoriq-telegram-approval',
    'Content-Type': 'application/json',
  };

  let existing = {};
  let sha = '';
  const current = await fetch(`${apiUrl}?ref=main`, { headers });
  if (current.ok) {
    const data = await current.json();
    sha = String(data?.sha || '');
    try {
      const raw = atob(String(data?.content || '').replace(/\n/g, ''));
      const bytes = Uint8Array.from(raw, c => c.charCodeAt(0));
      existing = JSON.parse(new TextDecoder().decode(bytes));
    } catch { existing = {}; }
  } else if (current.status !== 404) {
    return current;
  }

  const record = {
    ...existing,
    review_id: String(runId),
    status: 'APPROVED',
    platform_upload_performed: Boolean(existing.platform_upload_performed),
    publication_pending: true,
    approved_at: new Date().toISOString(),
    approved_via: 'telegram_callback',
    telegram_message_id: telegramMessageId,
    video_url: youtubeVideoUrl,
    youtube_video_url: youtubeVideoUrl,
    tiktok_video_url: tiktokVideoUrl,
    review_url: reviewUrl,
    tiktok_status: 'MANUAL_UPLOAD_REQUIRED',
  };
  const text = JSON.stringify(record, null, 2) + '\n';
  const bytes = new TextEncoder().encode(text);
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  const payload = { message: `Approve TAYVORIQ review ${runId} from Telegram`, content: btoa(binary), branch: 'main' };
  if (sha) payload.sha = sha;
  return fetch(apiUrl, { method: 'PUT', headers, body: JSON.stringify(payload) });
}

async function githubDispatch(env, eventType, clientPayload) {
  return fetch(`https://api.github.com/repos/${env.GITHUB_REPOSITORY}/dispatches`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
      'User-Agent': 'tayvoriq-telegram-approval',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ event_type: eventType, client_payload: clientPayload }),
  });
}

async function telegram(env, chatId, text) {
  return telegramMethod(env, 'sendMessage', { chat_id: chatId, text, disable_web_page_preview: false });
}

async function telegramWithMarkup(env, chatId, text, replyMarkup) {
  return telegramMethod(env, 'sendMessage', { chat_id: chatId, text, disable_web_page_preview: false, reply_markup: replyMarkup });
}

async function editMessageWithMarkup(env, chatId, messageId, text, replyMarkup) {
  if (!messageId) return telegramWithMarkup(env, chatId, text, replyMarkup);
  return telegramMethod(env, 'editMessageText', {
    chat_id: chatId,
    message_id: messageId,
    text,
    disable_web_page_preview: true,
    reply_markup: replyMarkup,
  });
}

async function requireTelegramMessage(response) {
  const data = await response.clone().json();
  if (!response.ok || data?.ok !== true || !data?.result?.message_id) {
    throw new Error(`Telegram delivery not verified: ${response.status} ${JSON.stringify(data)}`);
  }
  return data.result.message_id;
}

async function answerCallback(env, callbackQueryId, text) {
  return telegramMethod(env, 'answerCallbackQuery', { callback_query_id: callbackQueryId, text, show_alert: false });
}

async function clearKeyboard(env, chatId, messageId) {
  return telegramMethod(env, 'editMessageReplyMarkup', { chat_id: chatId, message_id: messageId, reply_markup: { inline_keyboard: [] } });
}

async function telegramMethod(env, method, payload) {
  const response = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/${method}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  });
  if (!response.ok) console.error(`Telegram ${method} failed`, response.status, await response.text());
  return response;
}
