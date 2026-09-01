import v3 from './telegram-approval-worker-v3.js';

export default {
  async fetch(request, env) {
    if (request.method !== 'POST') return v3.fetch(request, env);

    const suppliedSecret = request.headers.get('X-Telegram-Bot-Api-Secret-Token') || '';
    if (!env.TELEGRAM_WEBHOOK_SECRET || suppliedSecret !== env.TELEGRAM_WEBHOOK_SECRET) {
      return v3.fetch(request, env);
    }

    let update;
    try {
      update = await request.clone().json();
    } catch {
      return v3.fetch(request, env);
    }

    const callback = update.callback_query;
    const data = String(callback?.data || '').trim();
    const match = data.match(/^tayvoriq:(approve|reject):([A-Za-z0-9_-]{4,80}):(\d{6,20})$/i);
    if (!match) return v3.fetch(request, env);

    const chatId = String(callback?.message?.chat?.id || '');
    if (!chatId || chatId !== String(env.TELEGRAM_CHAT_ID)) {
      if (callback?.id) await telegramMethod(env, 'answerCallbackQuery', {
        callback_query_id: callback.id,
        text: 'Nicht autorisiert.',
        show_alert: false,
      });
      return new Response('ignored', { status: 403 });
    }

    const decision = match[1].toLowerCase();
    const requestId = match[2];
    const reviewRunId = match[3];
    const dispatch = await githubDispatch(env, 'tayvoriq_review_command', {
      action: decision === 'approve' ? 'approve_review' : 'reject_review',
      request_id: requestId,
      review_run_id: reviewRunId,
      source: 'telegram',
      telegram_chat_id: chatId,
      telegram_message_id: callback?.message?.message_id || null,
      commanded_at: new Date().toISOString(),
    });

    if (!dispatch.ok) {
      const detail = await dispatch.text();
      console.error('review command dispatch failed', dispatch.status, detail);
      if (callback?.id) await telegramMethod(env, 'answerCallbackQuery', {
        callback_query_id: callback.id,
        text: 'Aktion konnte nicht an das Control Center übergeben werden.',
        show_alert: true,
      });
      return new Response('dispatch failed', { status: 502 });
    }

    if (callback?.id) await telegramMethod(env, 'answerCallbackQuery', {
      callback_query_id: callback.id,
      text: decision === 'approve' ? 'Freigabe übernommen.' : 'Ablehnung übernommen.',
      show_alert: false,
    });
    if (callback?.message?.message_id) await telegramMethod(env, 'editMessageReplyMarkup', {
      chat_id: chatId,
      message_id: callback.message.message_id,
      reply_markup: { inline_keyboard: [] },
    });

    const text = decision === 'approve'
      ? `✅ TAYVORIQ · Review freigegeben\nRequest: ${requestId}\nReview-Run: ${reviewRunId}\nDer Publish-Befehl wurde an denselben Control-Plane-Auftrag übergeben.`
      : `❌ TAYVORIQ · Review abgelehnt\nRequest: ${requestId}\nReview-Run: ${reviewRunId}\nEs wird nichts veröffentlicht.`;
    await telegramMethod(env, 'sendMessage', {
      chat_id: chatId,
      text,
      disable_web_page_preview: true,
    });
    return new Response('ok');
  },
};

async function githubDispatch(env, eventType, clientPayload) {
  const repository = env.GITHUB_REPOSITORY || 'mojo72549-arch/tayvoriq-control-plane';
  return fetch(`https://api.github.com/repos/${repository}/dispatches`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
      'User-Agent': 'tayvoriq-telegram-control-v4',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ event_type: eventType, client_payload: clientPayload }),
  });
}

async function telegramMethod(env, method, payload) {
  const response = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/${method}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) console.error(`Telegram ${method} failed`, response.status, await response.text());
  return response;
}
