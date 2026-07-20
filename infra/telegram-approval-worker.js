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
    const text = (update.message?.text || callback?.data || '').trim();
    const chatId = String(message?.chat?.id || '');

    if (!chatId || chatId !== String(env.TELEGRAM_CHAT_ID)) {
      if (callback?.id) await answerCallback(env, callback.id, 'Nicht autorisiert.');
      return new Response('ignored');
    }

    const rejectMatch = text.match(/^ablehnen\s+(\d+)$/i) || text.match(/^reject:(\d+)$/i);
    if (rejectMatch) {
      const runId = rejectMatch[1];
      if (callback?.id) await answerCallback(env, callback.id, `Run ${runId} wurde abgelehnt.`);
      if (callback?.message?.message_id) {
        await clearKeyboard(env, chatId, callback.message.message_id);
      }
      await telegram(env, chatId, `❌ Run ${runId} wurde abgelehnt. Es erfolgt kein YouTube-Upload.`);
      return new Response('ok');
    }

    const approveMatch = text.match(/^freigeben\s+(\d+)$/i) || text.match(/^approve:(\d+)$/i);
    if (!approveMatch) {
      if (callback?.id) await answerCallback(env, callback.id, 'Unbekannte Aktion.');
      await telegram(env, chatId, 'Bitte nutze den Freigeben-Button oder schreibe: Freigeben RUN_ID.');
      return new Response('ok');
    }

    const runId = approveMatch[1];
    const videoUrl = `https://mojo72549-arch.github.io/mind-reset-daily/tayvoriq/runs/${runId}/video.mp4`;
    const reviewUrl = `https://mojo72549-arch.github.io/mind-reset-daily/tayvoriq/runs/${runId}/`;

    const head = await fetch(videoUrl, { method: 'HEAD', redirect: 'follow' });
    if (!head.ok) {
      if (callback?.id) await answerCallback(env, callback.id, 'Video ist noch nicht erreichbar.');
      await telegram(env, chatId, `❌ Video für Run ${runId} ist nicht öffentlich erreichbar.`);
      return new Response('video unavailable', { status: 409 });
    }

    const dispatch = await fetch(`https://api.github.com/repos/${env.GITHUB_REPOSITORY}/dispatches`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${env.GITHUB_TOKEN}`,
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'tayvoriq-telegram-approval',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        event_type: 'telegram_approve_youtube',
        client_payload: {
          run_id: runId,
          video_url: videoUrl,
          review_url: reviewUrl,
          title: 'KI verändert deinen Alltag – aber anders als du denkst #Shorts',
          description: 'KI kann dir Zeit zurückgeben, wenn du sie bewusst einsetzt. Prüfe Ergebnisse, schütze deine Daten und behalte wichtige Entscheidungen selbst in der Hand.\n\n#KI #Technologie #TAYVORIQ #Shorts',
          tags: 'KI,Technologie,TAYVORIQ,Shorts,Künstliche Intelligenz',
          privacy: env.YOUTUBE_PRIVACY || 'private',
        },
      }),
    });

    if (!dispatch.ok) {
      const detail = await dispatch.text();
      if (callback?.id) await answerCallback(env, callback.id, 'YouTube-Workflow konnte nicht gestartet werden.');
      await telegram(env, chatId, `❌ YouTube-Workflow konnte nicht gestartet werden: ${dispatch.status}`);
      console.error('repository_dispatch failed', dispatch.status, detail);
      return new Response('dispatch failed', { status: 502 });
    }

    if (callback?.id) await answerCallback(env, callback.id, `Run ${runId} freigegeben.`);
    if (callback?.message?.message_id) {
      await clearKeyboard(env, chatId, callback.message.message_id);
    }
    await telegram(env, chatId, `✅ Freigabe für Run ${runId} angenommen. Der YouTube-Upload wurde gestartet.`);
    return new Response('ok');
  },
};

async function telegram(env, chatId, text) {
  return telegramMethod(env, 'sendMessage', {
    chat_id: chatId,
    text,
    disable_web_page_preview: false,
  });
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
