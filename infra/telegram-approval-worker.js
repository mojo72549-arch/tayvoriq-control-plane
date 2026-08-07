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
          '🔄 TAYVORIQ Alternativ-Trend',
          '',
          `Ausgewählt: ${next.id}`,
          `Thema: ${next.title}`,
          `Score: ${next.score} %`,
          '',
          'Grund berücksichtigt: bisheriges Thema abgelehnt.',
          'Erst mit „Trend freigeben“ startet die Produktion.'
        ].join('\n');
        const sent = await telegramWithMarkup(env, chatId, body, trendKeyboard(String(next.id)));
        await requireTelegramMessage(sent);
        return new Response('ok');
      }

      const current = trends[currentIndex];
      const formatTopic = `${current.title} — als kompakter Erklär-Short mit Kontrast-Hook, 3 klaren Fakten und visueller Vorher/Nachher-Dramaturgie`;
      const body = [
        '🎬 TAYVORIQ Format-Alternative',
        '',
        `Ausgewählt: ${current.id}`,
        `Thema: ${formatTopic}`,
        '',
        'Grund berücksichtigt: Thema bleibt, Format wird neu aufgesetzt.',
        'Erst mit „Trend freigeben“ startet die Produktion.'
      ].join('\n');
      const sent = await telegramWithMarkup(env, chatId, body, trendKeyboard(String(current.id)));
      await requireTelegramMessage(sent);
      return new Response('ok');
    }

    const trendApproval = parseTrendApproval(callbackData, text, messageText);
    if (trendApproval) {
      const { trendId, topic } = trendApproval;
      if (callback?.id) await answerCallback(env, callback.id, `Trend ${trendId} wird gestartet.`);

      const dispatch = await githubDispatch(env, 'tayvoriq_trend_approved', {
        trend_id: trendId,
        topic,
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
      const sent = await telegram(env, chatId, `✅ TAYVORIQ 5 %\nTrend ${trendId} freigegeben.\nThema: ${topic || 'wird aus Trenddaten geladen'}\nX-Workflow wurde angefordert.\nNächster Schritt: Startbestätigung bei 10 %`);
      await requireTelegramMessage(sent);
      return new Response('ok');
    }

    const rejectTrend = callbackData.match(/^(?:reject_trend|trend_reject|reject:trend)[:_](\d+)$/i);
    if (rejectTrend) {
      const trendId = rejectTrend[1];
      if (callback?.id) await answerCallback(env, callback.id, `Trend ${trendId} abgelehnt.`);
      if (callback?.message?.message_id) await clearKeyboard(env, chatId, callback.message.message_id);
      const sent = await telegramWithMarkup(
        env,
        chatId,
        `❌ Trend ${trendId} abgelehnt.\n\nWas ist der Hauptgrund?`,
        {
          inline_keyboard: [
            [{ text: '📰 Thema/Trend passt nicht', callback_data: `trend_reason:newtrend:${trendId}` }],
            [{ text: '🎬 Format passt nicht', callback_data: `trend_reason:newformat:${trendId}` }]
          ]
        }
      );
      await requireTelegramMessage(sent);
      return new Response('ok');
    }

    const rejectMatch = text.match(/^ablehnen\s+(\d+)$/i) || text.match(/^reject:(\d+)$/i);
    if (rejectMatch) {
      const runId = rejectMatch[1];
      if (callback?.id) await answerCallback(env, callback.id, `Run ${runId} wurde abgelehnt.`);
      if (callback?.message?.message_id) await clearKeyboard(env, chatId, callback.message.message_id);
      await requireTelegramMessage(await telegram(env, chatId, `❌ Run ${runId} wurde abgelehnt. Es erfolgt kein YouTube-Upload.`));
      return new Response('ok');
    }

    const approveMatch = text.match(/^freigeben\s+(\d+)$/i) || text.match(/^approve:(\d+)$/i);
    if (!approveMatch) {
      if (callback?.id) await answerCallback(env, callback.id, 'Unbekannte Aktion.');
      await requireTelegramMessage(await telegram(env, chatId, 'Aktion konnte nicht zugeordnet werden. Bitte nutze den aktuellen Trend-freigeben-Button.'));
      return new Response('ok');
    }

    const runId = approveMatch[1];
    const videoUrl = `https://mojo72549-arch.github.io/mind-reset-daily/tayvoriq/runs/${runId}/video.mp4`;
    const reviewUrl = `https://mojo72549-arch.github.io/mind-reset-daily/tayvoriq/runs/${runId}/`;
    const head = await fetch(videoUrl, { method: 'HEAD', redirect: 'follow' });
    if (!head.ok) {
      if (callback?.id) await answerCallback(env, callback.id, 'Video ist noch nicht erreichbar.');
      await requireTelegramMessage(await telegram(env, chatId, `❌ Video für Run ${runId} ist nicht öffentlich erreichbar.`));
      return new Response('video unavailable', { status: 409 });
    }

    const dispatch = await githubDispatch(env, 'telegram_approve_youtube', {
      run_id: runId,
      video_url: videoUrl,
      review_url: reviewUrl,
      privacy: env.YOUTUBE_PRIVACY || 'public',
    });

    if (!dispatch.ok) {
      const detail = await dispatch.text();
      if (callback?.id) await answerCallback(env, callback.id, 'YouTube-Workflow konnte nicht gestartet werden.');
      await requireTelegramMessage(await telegram(env, chatId, `❌ YouTube-Workflow konnte nicht gestartet werden: ${dispatch.status}`));
      console.error('youtube repository_dispatch failed', dispatch.status, detail);
      return new Response('dispatch failed', { status: 502 });
    }

    if (callback?.id) await answerCallback(env, callback.id, `Run ${runId} freigegeben.`);
    if (callback?.message?.message_id) await clearKeyboard(env, chatId, callback.message.message_id);
    await requireTelegramMessage(await telegram(env, chatId, `✅ Freigabe für Run ${runId} angenommen. Der YouTube-Upload wurde gestartet.`));
    return new Response('ok');
  },
};

function trendKeyboard(trendId) {
  return {
    inline_keyboard: [[
      { text: '✅ Trend freigeben', callback_data: `approve_trend:${trendId}` },
      { text: '❌ Ablehnen', callback_data: `reject_trend:${trendId}` }
    ]]
  };
}

function parseTrendApproval(callbackData, text, messageText) {
  const explicit = callbackData.match(/^(?:approve_trend|trend_approve|trend:approve|approve:trend)[:_](\d+)$/i)
    || text.match(/^trend\s+freigeben\s+(\d+)$/i);
  let trendId = explicit?.[1] || '';

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
    if (match?.[1]) {
      topic = match[1].replace(/^[*\s]+|[*\s]+$/g, '').trim();
      break;
    }
  }
  return { trendId, topic };
}

async function loadTrendRequest(env) {
  const repository = env.GITHUB_REPOSITORY || 'mojo72549-arch/tayvoriq-control-plane';
  const response = await fetch(`https://raw.githubusercontent.com/${repository}/main/.github/run-now/tayvoriq-trend-request.json`, {
    headers: { 'User-Agent': 'tayvoriq-telegram-approval' }
  });
  if (!response.ok) throw new Error(`Trend request HTTP ${response.status}`);
  return response.json();
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
  return telegramMethod(env, 'sendMessage', {
    chat_id: chatId,
    text,
    disable_web_page_preview: false,
  });
}

async function telegramWithMarkup(env, chatId, text, replyMarkup) {
  return telegramMethod(env, 'sendMessage', {
    chat_id: chatId,
    text,
    disable_web_page_preview: false,
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
  return telegramMethod(env, 'answerCallbackQuery', {
    callback_query_id: callbackQueryId,
    text,
    show_alert: false,
  });
}

async function clearKeyboard(env, chatId, messageId) {
  return telegramMethod(env, 'editMessageReplyMarkup', {
    chat_id: chatId,
    message_id: messageId,
    reply_markup: { inline_keyboard: [] },
  });
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
