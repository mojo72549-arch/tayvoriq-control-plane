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


    const normalizedText = text.toLocaleLowerCase('de-DE').trim();
    if (!callbackData && /^\/(?:trends|trend)(?:@\w+)?$/.test(normalizedText)) {
      const now = berlinDateSlot();
      const refresh = `r${(Math.floor(Date.now() / 1000) % 99) + 1}`;
      const dispatch = await githubDispatch(env, 'tayvoriq_telegram_trends_now', {
        slot: now.slot,
        target_date: now.date,
        refresh,
        telegram_chat_id: chatId,
        requested_at: new Date().toISOString(),
        requested_via: 'telegram_command',
      });
      if (!dispatch.ok) {
        const detail = await dispatch.text();
        console.error('telegram trends dispatch failed', dispatch.status, detail);
        await requireTelegramMessage(await telegram(
          env,
          chatId,
          `❌ Trend-Suche konnte nicht gestartet werden. GitHub-Fehler: ${dispatch.status}`,
        ));
        return new Response('trend command dispatch failed', { status: 502 });
      }
      await requireTelegramMessage(await telegram(
        env,
        chatId,
        [
          '🔎 TAYVORIQ · V5 Trend-Suche gestartet',
          '',
          `Slot: ${now.slot === 'morning' ? 'Morgen' : 'Abend'}`,
          `Datum: ${now.date}`,
          '➡️ Ich melde mich hier mit exakt 5 geprüften Kandidaten.',
          '✅ Vor deiner Trendfreigabe startet keine Produktion.',
        ].join('\n'),
      ));
      return new Response('ok');
    }

    if (!callbackData && /^\/status(?:@\w+)?$/.test(normalizedText)) {
      try {
        const health = await loadOpsHealth(env);
        await requireTelegramMessage(await telegram(env, chatId, operatorStatusText(health)));
        return new Response('ok');
      } catch (error) {
        await requireTelegramMessage(await telegram(
          env,
          chatId,
          `❌ Status konnte nicht geladen werden. Grund: ${String(error).slice(0, 300)}`,
        ));
        return new Response('status unavailable', { status: 502 });
      }
    }

    if (!callbackData && /^\/(?:hilfe|help)(?:@\w+)?$/.test(normalizedText)) {
      await requireTelegramMessage(await telegram(env, chatId, [
        '🟣 TAYVORIQ · Telegram-Steuerung',
        '',
        '/trends – jetzt eine frische V5-Trendliste mit 5 Kandidaten anfordern',
        '/status – aktuellen Auftrag, Fortschritt und Recovery-Status anzeigen',
        '/hilfe – diese Übersicht anzeigen',
        '',
        'Danach steuerst du per Buttons:',
        '1️⃣ Trend auswählen',
        '✅ Trend freigeben',
        '🔄 Liste/Format neu anfordern',
        '✅ Video freigeben oder ❌ ablehnen',
        '',
        'Das Control Center ist nur Beobachtung. Veröffentlichung bleibt bis zu deiner Review-Freigabe gesperrt.',
      ].join('\n')));
      return new Response('ok');
    }

    const selectTrend = callbackData.match(/^select_trend:([A-Za-z0-9_-]{4,40}):([1-5])$/);
    if (selectTrend) {
      const selectionId = selectTrend[1];
      const trendId = selectTrend[2];
      if (callback?.id) await answerCallback(env, callback.id, `Trend ${trendId} ausgewählt.`);

      let requestData;
      try {
        requestData = await loadTrendRequest(env, selectionId);
      } catch (error) {
        await requireTelegramMessage(await telegram(env, chatId, `❌ Trendauswahl konnte nicht geladen werden.\nGrund: ${String(error).slice(0, 350)}`));
        return new Response('trend request unavailable', { status: 502 });
      }
      if (String(requestData?.selection_id || '') !== selectionId) {
        await requireTelegramMessage(await telegram(env, chatId, '⚠️ Diese Trendauswahl ist nicht mehr aktuell. Bitte nutze die zugehörige aktuelle Rangliste.'));
        return new Response('stale trend selection', { status: 409 });
      }
      if (selectionIsRejected(requestData)) {
        return rejectStaleSelectionUi(env, callback, chatId, selectionId);
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
        requestData = await loadTrendRequest(env, selectionId);
      } catch (error) {
        await requireTelegramMessage(await telegram(env, chatId, `❌ Trendauswahl konnte nicht geladen werden.\nGrund: ${String(error).slice(0, 350)}`));
        return new Response('trend request unavailable', { status: 502 });
      }
      if (String(requestData?.selection_id || '') !== selectionId) {
        await requireTelegramMessage(await telegram(env, chatId, '⚠️ Diese Trendauswahl ist nicht mehr aktuell. Bitte nutze die zugehörige aktuelle Rangliste.'));
        return new Response('stale trend selection', { status: 409 });
      }
      if (selectionIsRejected(requestData)) {
        return rejectStaleSelectionUi(env, callback, chatId, selectionId);
      }
      await requireTelegramMessage(await editMessageWithMarkup(
        env,
        chatId,
        callback?.message?.message_id,
        trendListBody(requestData),
        trendSelectionKeyboard(selectionId, (requestData.trends || []).length),
      ));
      return new Response('ok');
    }

    const currentReason = callbackData.match(/^trend_reason:(newtrend|newformat):([A-Za-z0-9_-]{4,40}):([1-5])$/i);
    const legacyReason = callbackData.match(/^trend_reason:(newtrend|newformat):(\d+)$/i);
    const reasonMatch = currentReason || legacyReason;
    if (reasonMatch) {
      const action = reasonMatch[1].toLowerCase();
      const selectionId = currentReason?.[2] || '';
      const trendId = currentReason?.[3] || legacyReason?.[2] || '';
      if (callback?.id) await answerCallback(env, callback.id, action === 'newtrend' ? 'Neuer Trend wird vorgeschlagen.' : 'Neues Format wird vorgeschlagen.');
      if (callback?.message?.message_id) await clearKeyboard(env, chatId, callback.message.message_id);

      let requestData;
      try {
        requestData = await loadTrendRequest(env, selectionId);
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
          `Ausgewählt: ${next.id}`, `Thema: ${next.title}`, `V5-Auswahlscore: ${v5Score(next)}/100`, '',
          'Grund berücksichtigt: bisheriges Thema abgelehnt.',
          'Erst mit „Trend freigeben“ startet die Produktion.'
        ].join('\n');
        await requireTelegramMessage(await telegramWithMarkup(env, chatId, body, trendKeyboard(String(next.id), selectionId)));
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
      await requireTelegramMessage(await telegramWithMarkup(env, chatId, body, trendKeyboard(String(current.id), selectionId)));
      return new Response('ok');
    }

    const trendApproval = parseTrendApproval(callbackData, text, messageText);
    if (trendApproval) {
      const { trendId, selectionId } = trendApproval;
      if (callback?.id) await answerCallback(env, callback.id, `Trend ${trendId} wird geprüft.`);

      let requestData;
      try {
        requestData = await loadTrendRequest(env, selectionId);
      } catch (error) {
        await requireTelegramMessage(await telegram(env, chatId, `❌ Trendfreigabe konnte die aktuelle Rangliste nicht laden.\nGrund: ${String(error).slice(0, 350)}`));
        return new Response('trend request unavailable', { status: 502 });
      }
      const currentSelectionId = String(requestData?.selection_id || '');
      if ((currentSelectionId && selectionId !== currentSelectionId) || (!currentSelectionId && selectionId)) {
        await requireTelegramMessage(await telegram(env, chatId, '⚠️ Diese Trendfreigabe ist nicht mehr aktuell. Es wurde keine Produktion gestartet.'));
        return new Response('stale trend approval', { status: 409 });
      }
      if (selectionIsRejected(requestData)) {
        return rejectStaleSelectionUi(env, callback, chatId, currentSelectionId || selectionId);
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

    const currentReject = callbackData.match(/^reject_trend:([A-Za-z0-9_-]{4,40}):([1-5])$/i);
    if (currentReject) {
      const selectionId = currentReject[1];
      const trendId = currentReject[2];
      if (callback?.id) await answerCallback(env, callback.id, 'Komplette Liste verworfen. Neue Trends werden gesucht.');

      let requestData;
      try {
        requestData = await loadTrendRequest(env, selectionId);
      } catch (error) {
        await requireTelegramMessage(await telegram(env, chatId, `❌ Ablehnung konnte die aktuelle Auswahl nicht laden.\nGrund: ${String(error).slice(0, 300)}`));
        return new Response('trend request unavailable', { status: 502 });
      }
      if (String(requestData?.selection_id || '') !== selectionId) {
        await requireTelegramMessage(await telegram(env, chatId, '⚠️ Diese Trendauswahl ist bereits veraltet. Es wurde nichts gestartet.'));
        return new Response('stale trend rejection', { status: 409 });
      }

      const dispatch = await githubDispatch(env, 'tayvoriq_trends_rejected', {
        selection_id: selectionId,
        rejected_trend_id: trendId,
        telegram_chat_id: chatId,
        telegram_message_id: callback?.message?.message_id || null,
        rejected_at: new Date().toISOString(),
        reason: 'USER_REJECTED_WHOLE_SELECTION',
      });
      if (!dispatch.ok) {
        const detail = await dispatch.text();
        console.error('trend rejection dispatch failed', dispatch.status, detail);
        await requireTelegramMessage(await telegram(env, chatId, `❌ Neue Trends konnten nicht angefordert werden. GitHub-Fehler: ${dispatch.status}`));
        return new Response('trend rejection dispatch failed', { status: 502 });
      }

      if (callback?.message?.message_id) await clearKeyboard(env, chatId, callback.message.message_id);
      await requireTelegramMessage(await telegram(env, chatId, [
        '🔄 TAYVORIQ · Komplette Trendliste verworfen',
        '',
        `Selection: ${selectionId}`,
        '✅ Keine Produktion gestartet.',
        '✅ Die fünf bisherigen Themen werden als abgelehnt markiert.',
        '➡️ Neue Reach-First-Trends werden jetzt frisch recherchiert.',
      ].join('\n')));
      return new Response('ok');
    }

    const legacyReject = callbackData.match(/^(?:reject_trend|trend_reject|reject:trend)[:_](\d+)$/i);
    if (legacyReject) {
      const trendId = legacyReject[1];
      if (callback?.id) await answerCallback(env, callback.id, `Trend ${trendId} abgelehnt.`);
      if (callback?.message?.message_id) await clearKeyboard(env, chatId, callback.message.message_id);
      await requireTelegramMessage(await telegram(env, chatId, `❌ Trend ${trendId} abgelehnt. Bitte nutze für neue Listen die aktuelle Zwei-Schritt-Auswahl.`));
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

    const packageCheck = await verifyCommittedReviewPackage(runId);
    if (!packageCheck.ok) {
      if (callback?.id) await answerCallback(env, callback.id, 'Review-Paket ist im Quell-Repository noch nicht vollständig.', true);
      const missing = packageCheck.missing.length ? packageCheck.missing.join(', ') : 'Verzeichnis nicht erreichbar';
      await requireTelegramMessage(await telegram(env, chatId, `❌ Review ${runId} ist noch nicht vollständig committed. Fehlend: ${missing}. Keine Freigabe gespeichert.`));
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

function trendKeyboard(trendId, selectionId = '') {
  if (selectionId) return trendConfirmationKeyboard(selectionId, trendId);
  return { inline_keyboard: [[
    { text: '✅ Trend freigeben', callback_data: `approve_trend:${trendId}` },
    { text: '❌ Ablehnen', callback_data: `reject_trend:${trendId}` }
  ]] };
}

function trendSelectionKeyboard(selectionId, trendCount = 5) {
  const count = Math.max(1, Math.min(5, Number(trendCount) || 1));
  const emoji = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣'];
  const label = count === 1 ? 'Folge' : 'Trend';
  const buttons = Array.from({ length: count }, (_, index) => ({
    text: `${emoji[index]} ${label} ${index + 1}`,
    callback_data: `select_trend:${selectionId}:${index + 1}`,
  }));
  const rows = [];
  for (let index = 0; index < buttons.length; index += 2) rows.push(buttons.slice(index, index + 2));
  return { inline_keyboard: rows };
}

function trendConfirmationKeyboard(selectionId, trendId) {
  return {
    inline_keyboard: [
      [{ text: '✅ Trend freigeben', callback_data: `approve_trend:${selectionId}:${trendId}` }],
      [{ text: '🔄 Alle ablehnen & neue Trends suchen', callback_data: `reject_trend:${selectionId}:${trendId}` }],
      [{ text: '↩️ Anderen Trend aus dieser Liste wählen', callback_data: `trend_list:${selectionId}` }],
    ],
  };
}

function v5Score(trend) {
  const value = Number(trend?.trend_selection_score);
  return Number.isFinite(value) ? Math.round(value) : Math.round(Number(trend?.score || 0));
}

function trendListBody(requestData) {
  const heading = requestData?.slot === 'morning' ? '🌅 TAYVORIQ Morgen-Trends' : '🌙 TAYVORIQ Abend-Trends';
  const lines = [heading, '', 'V5-Rangliste:'];
  for (const trend of requestData.trends || []) {
    const series = String(trend?.proposed_series_name || '').trim() || 'NONE';
    const next = String(trend?.next_episode_candidate || '').trim() || '—';
    lines.push(
      `${trend.id}. ${trend.title} — Auswahl ${v5Score(trend)}/100`,
      `   Viralität: ${Number(trend?.viral_potential || 0)}/100 · TAYVORIQ-Fit: ${Number(trend?.tayvoriq_fit || 0)}/100`,
      `   Serie: ${series} · Serienpotenzial: ${Number(trend?.series_fit_score || 0)}/100`,
      `   Return-Viewer: ${Number(trend?.return_viewer_score || 0)}/100 · Follow: ${Number(trend?.follow_conversion_potential || 0)}/100`,
      `   Möglicher nächster Teil: ${next}`,
      '',
    );
  }
  lines.push(
    'Evidence/Quellenqualität bleibt Mindestbedingung und kann durch den V5-Score nicht kompensiert werden.',
    '',
    'Schritt 1: Tippe auf eine Nummer.',
    'Schritt 2: Prüfe den Trend und tippe separat auf „Trend freigeben“.',
    '',
    'Vor dem zweiten Klick startet keine Produktion.',
  );
  return lines.join('\n');
}

function selectedTrendBody(trend) {
  const series = String(trend?.proposed_series_name || '').trim() || 'NONE';
  const next = String(trend?.next_episode_candidate || '').trim() || '—';
  const followReason = String(trend?.follow_reason || '').trim() || '–';
  const lines = [
    '🟣 TAYVORIQ Trend ausgewählt',
    '',
    `Ausgewählt: ${trend.id}`,
    `Thema: ${trend.title}`,
    `V5-Auswahlscore: ${v5Score(trend)}/100`,
    '',
    `Viralität: ${Number(trend?.viral_potential || 0)}/100 · TAYVORIQ-Fit: ${Number(trend?.tayvoriq_fit || 0)}/100`,
    `Serienpotenzial: ${Number(trend?.series_fit_score || 0)}/100 · Return-Viewer: ${Number(trend?.return_viewer_score || 0)}/100`,
    `Follow-Potenzial: ${Number(trend?.follow_conversion_potential || 0)}/100`,
    `Serie: ${series}`,
    `Möglicher nächster Teil: ${next}`,
    `CTA-Typ: ${String(trend?.cta_type || trend?.recommended_cta_type || '–')}`,
    `Open Loop: ${String(trend?.open_loop_status || 'NONE')}`,
    `Follow-Grund: ${followReason}`,
  ];
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

function selectionIsRejected(requestData) {
  return requestData?.superseded === true
    || requestData?.rejected_whole_selection === true
    || String(requestData?.status || '').toUpperCase() === 'REJECTED';
}

async function rejectStaleSelectionUi(env, callback, chatId, selectionId) {
  if (callback?.id) {
    await answerCallback(env, callback.id, 'Diese Trendliste wurde verworfen. Nutze die neueste Auswahl.');
  }
  if (callback?.message?.message_id) {
    await clearKeyboard(env, chatId, callback.message.message_id);
  }
  await requireTelegramMessage(await telegram(
    env,
    chatId,
    `⚠️ Trendliste ${selectionId} wurde bereits verworfen. Keine Produktion gestartet. Nutze nur die neueste Rangliste.`,
  ));
  return new Response('rejected trend selection', { status: 409 });
}

async function loadTrendRequest(env, selectionId = '') {
  const repository = env.GITHUB_REPOSITORY || 'mojo72549-arch/tayvoriq-control-plane';
  const safeSelection = /^[A-Za-z0-9_-]{4,40}$/.test(selectionId) ? selectionId : '';
  const paths = safeSelection
    ? [`.automation/tayvoriq-agent-v2/selections/${safeSelection}.json`, '.github/run-now/tayvoriq-trend-request.json']
    : ['.github/run-now/tayvoriq-trend-request.json'];
  let lastStatus = 404;
  for (const path of paths) {
    const response = await fetch(`https://raw.githubusercontent.com/${repository}/main/${path}`, {
      headers: { 'User-Agent': 'tayvoriq-telegram-approval' },
    });
    lastStatus = response.status;
    if (!response.ok) continue;
    const data = await response.json();
    if (!safeSelection || String(data?.selection_id || '') === safeSelection) return data;
  }
  throw new Error(`Trend request HTTP ${lastStatus} for selection ${safeSelection || 'current'}`);
}

async function verifyCommittedReviewPackage(runId) {
  const safeRunId = String(runId || '').trim();
  if (!/^\d+$/.test(safeRunId)) {
    return { ok: false, missing: ['ungueltige Review-ID'], status: 400 };
  }

  const required = ['index.html', 'job.json', 'preapproval_ai_audit.json', 'short_youtube.mp4', 'short_tiktok.mp4'];
  const url = `https://api.github.com/repos/mojo72549-arch/mind-reset-daily/contents/tayvoriq/runs/${safeRunId}?ref=main`;
  const response = await fetch(url, {
    headers: {
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
      'User-Agent': 'tayvoriq-telegram-approval',
    },
  });
  if (!response.ok) {
    return { ok: false, missing: required, status: response.status };
  }

  const items = await response.json();
  const names = new Set(Array.isArray(items) ? items.map(item => String(item?.name || '')) : []);
  const missing = required.filter(name => !names.has(name));
  return { ok: missing.length === 0, missing, status: response.status };
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
    publication_pending: existing.platform_upload_performed ? false : true,
    approved_at: existing.approved_at || new Date().toISOString(),
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


function berlinDateSlot(date = new Date()) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Europe/Berlin',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(date);
  const read = type => parts.find(part => part.type === type)?.value || '';
  const year = read('year');
  const month = read('month');
  const day = read('day');
  const hour = Number(read('hour') || 0);
  return {
    date: `${year}-${month}-${day}`,
    slot: hour < 12 ? 'morning' : 'evening',
  };
}

async function loadOpsHealth(env) {
  const response = await fetch(
    `https://api.github.com/repos/${env.GITHUB_REPOSITORY}/contents/run-status/ops-health.json?ref=main`,
    {
      headers: {
        Authorization: `Bearer ${env.GITHUB_TOKEN}`,
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'tayvoriq-telegram-approval',
      },
    },
  );
  if (!response.ok) {
    throw new Error(`GitHub ${response.status}`);
  }
  const payload = await response.json();
  const encoded = String(payload?.content || '').replace(/\s+/g, '');
  if (!encoded) throw new Error('ops-health content missing');
  const decoded = decodeURIComponent(
    Array.from(atob(encoded), ch => '%' + ch.charCodeAt(0).toString(16).padStart(2, '0')).join(''),
  );
  return JSON.parse(decoded);
}

function operatorStatusText(health) {
  const request = health?.request && typeof health.request === 'object' ? health.request : {};
  const run = health?.run && typeof health.run === 'object' ? health.run : {};
  const recovery = health?.recovery && typeof health.recovery === 'object' ? health.recovery : {};
  const overall = String(health?.overall || 'unknown').toUpperCase();
  const topic = String(request?.topic || 'Kein aktiver Auftrag');
  const state = String(request?.state || '–');
  const progress = Number.isFinite(Number(run?.progress)) ? `${Number(run.progress)} %` : '–';
  const step = String(run?.current_step || run?.last_successful_step || '–');
  const recoveryStatus = String(recovery?.status || '–');
  const action = health?.user_action_required === true ? '⚠️ Aktion erforderlich' : '✅ Keine Aktion nötig';
  return [
    `🟣 TAYVORIQ · Status ${overall}`,
    '',
    `Thema: ${topic}`,
    `Request: ${String(request?.request_id || '–')}`,
    `Status: ${state}`,
    `Fortschritt: ${progress}`,
    `Aktueller Schritt: ${step}`,
    `Recovery: ${recoveryStatus}`,
    '',
    action,
  ].join('\n');
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
