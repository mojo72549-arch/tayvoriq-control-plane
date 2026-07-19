export default {
  async fetch(request, env) {
    if (request.method !== 'POST') return new Response('ok');
    const update = await request.json();
    const message = update.message || update.callback_query?.message;
    const text = (update.message?.text || update.callback_query?.data || '').trim();
    const chatId = String(message?.chat?.id || '');
    if (!chatId || chatId !== String(env.TELEGRAM_CHAT_ID)) return new Response('ignored');

    const match = text.match(/^freigeben\s+(\d+)$/i) || text.match(/^approve:(\d+)$/i);
    if (!match) {
      await telegram(env, chatId, 'Bitte antworte mit: Freigeben RUN_ID oder nutze den Freigeben-Button.');
      return new Response('ok');
    }

    const runId = match[1];
    const videoUrl = `https://mojo72549-arch.github.io/mind-reset-daily/tayvoriq/runs/${runId}/video.mp4`;
    const reviewUrl = `https://mojo72549-arch.github.io/mind-reset-daily/tayvoriq/runs/${runId}/`;
    const head = await fetch(videoUrl, { method: 'HEAD', redirect: 'follow' });
    if (!head.ok) {
      await telegram(env, chatId, `❌ Video für Run ${runId} ist nicht öffentlich erreichbar.`);
      return new Response('video unavailable', { status: 409 });
    }

    const dispatch = await fetch(`https://api.github.com/repos/${env.GITHUB_REPOSITORY}/dispatches`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${env.GITHUB_TOKEN}`,
        'Accept': 'application/vnd.github+json',
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
      await telegram(env, chatId, `❌ YouTube-Workflow konnte nicht gestartet werden: ${dispatch.status}`);
      return new Response('dispatch failed', { status: 502 });
    }

    await telegram(env, chatId, `✅ Freigabe für Run ${runId} angenommen. Der YouTube-Upload wurde gestartet.`);
    return new Response('ok');
  },
};

async function telegram(env, chatId, text) {
  await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chat_id: chatId, text, disable_web_page_preview: false }),
  });
}
