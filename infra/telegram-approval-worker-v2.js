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
        const pointer = (await reviewRepoFile(env, '.github/state/tayvoriq-active-production-request.json'))?.data;
        const review = await replacementTrendStatus(env, pointer);
        const status = (review?.pending ? review.text :
          (pointer?.state !== 'ACTIVE' ? await routineTrendStatus(env) : null) || review?.text)
          || operatorStatusText(await loadOpsHealth(env));
        await requireTelegramMessage(await telegram(env, chatId, status));
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
      const messageId=callback?.message?.message_id;
      if(!Number.isSafeInteger(messageId)||messageId<=0)return new Response('approval message missing',{status:422});
      try {
        const requestId=`telegram-${messageId}-trend-${trendId}`;
        const [pointer,existing]=await Promise.all([
          reviewRepoFile(env,'.github/state/tayvoriq-active-production-request.json'),
          reviewRepoFile(env,`requests/${requestId}.json`)
        ]);
        if(pointer?.data?.selection_id===currentSelectionId||existing?.data?.selection_id===currentSelectionId){
          const same=existing?.data?.request_id===requestId||pointer?.data?.request_id===requestId;
          if(callback?.id)await answerCallback(env,callback.id,same?'Dieser Auftrag ist bereits gespeichert.':'Für diese Auswahl wurde bereits ein anderes Thema freigegeben.',!same);
          await clearKeyboard(env,chatId,messageId);
          return new Response(same?'approval already recorded':'selection already consumed',{status:same?200:409});
        }
      } catch {
        if(callback?.id)await answerCallback(env,callback.id,'Der gemeinsame Auftragszustand ist gerade nicht verifizierbar. Bitte erneut prüfen.',true);
        return new Response('approval state unavailable',{status:503});
      }
      const dispatch = await githubDispatch(env, 'tayvoriq_trend_approved', {
        trend_id: trendId,
        topic,
        selection_id: currentSelectionId,
        telegram_chat_id: chatId,
        telegram_message_id: messageId,
        requested_via:'telegram_callback',
        approved_at: new Date().toISOString(),
      });
      if (!dispatch.ok) {
        const detail = await dispatch.text();
        await requireTelegramMessage(await telegram(env, chatId, `❌ Themenfreigabe konnte nicht beim Orchestrator eingereicht werden.\nGitHub-Fehler: ${dispatch.status}`));
        console.error('trend repository_dispatch failed', dispatch.status, detail);
        return new Response('dispatch failed', { status: 502 });
      }
      if (callback?.message?.message_id) await clearKeyboard(env, chatId, callback.message.message_id);
      await requireTelegramMessage(await telegram(env, chatId, `✅ Themenfreigabe beim Orchestrator eingegangen.\nThema: ${topic}\nDie Produktion ist angefordert. Der Start wird erst nach bestätigter Ausführung gemeldet.`));
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

    const artifactDecision = callbackData.match(/^tayvoriq:artifact:(approve|reject):(\d{1,20})$/);
    if (artifactDecision) {
      return decideArtifactReview(env, callback, chatId, artifactDecision[1], artifactDecision[2]);
    }

    const markedReason = callbackData.match(/^tayvoriq:reason:(\d{1,20}):(visuals|voice|content|other)$/);
    if (markedReason) {
      const result = await storeReviewRejection(env, markedReason[1], null, REVIEW_REASONS[markedReason[2]], 'auto', markedReason[2]);
      if (!result.ok) {
        await answerCallback(env, callback.id, 'Der Grund konnte gerade nicht gespeichert werden.', true);
        return new Response('reason not stored', { status: 409 });
      }
      await answerCallback(env, callback.id, 'Ablehnungsgrund gespeichert.');
      await requireTelegramMessage(await editMessageWithMarkup(env, chatId, callback.message?.message_id,
        'Ablehnungsgrund gespeichert. Der Orchestrator übernimmt den nächsten Schritt.', {inline_keyboard: []}));
      return new Response('ok');
    }

    const followup = callbackData.match(/^tayvoriq:followup:(\d{1,20}):(new_trends|repair)$/);
    if (followup) {
      const result = await storeReviewRejection(env, followup[1], null, undefined, followup[2]);
      if (!result.ok) {
        await answerCallback(env, callback.id, 'Der nächste Schritt konnte nicht gespeichert werden oder wurde bereits gewählt.', true);
        return new Response('followup not stored', {status: 409});
      }
      const text = 'Entscheidung gespeichert. Der Orchestrator übernimmt den nächsten Schritt.';
      await answerCallback(env, callback.id, 'Gespeichert.');
      await requireTelegramMessage(await editMessageWithMarkup(env, chatId, callback.message?.message_id, text, {inline_keyboard: []}));
      return new Response('ok');
    }

    const rejectMatch = callbackData.match(/^tayvoriq:reject:(\d+)$/i)
      || text.match(/^ablehnen\s+(\d+)$/i)
      || text.match(/^reject:(\d+)$/i);
    if (rejectMatch) {
      const runId = rejectMatch[1];
      const result = await storeReviewRejection(env, runId, callback?.message?.message_id ?? null);
      if (!result.ok) {
        if (callback?.id) await answerCallback(env, callback.id, 'Ablehnung konnte nicht gespeichert werden.', true);
        else await requireTelegramMessage(await telegram(env, chatId, 'Ablehnung konnte nicht gespeichert werden. Prüfe den aktuellen Review.'));
        return new Response('rejection not recorded', { status: 409 });
      }
      if (callback?.id) await answerCallback(env, callback.id, 'Ablehnung gespeichert.');
      if (callback?.message?.message_id) await clearKeyboard(env, chatId, callback.message.message_id);
      if (result.needsReason) await askForReviewReason(env, chatId, runId);
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
    try {
      const record = await reviewRepoFile(env, `.automation/tayvoriq-artifact-decisions/${runId}.json`);
      if (record?.data.state === 'REJECTED') {
        if (callback?.id) await answerCallback(env, callback.id, 'Dieses Video wurde bereits abgelehnt.', true);
        return new Response('review rejected', { status: 409 });
      }
    } catch {
      if (callback?.id) await answerCallback(env, callback.id, 'Review-Status gerade nicht verfügbar.', true);
      return new Response('review decision unavailable', { status: 503 });
    }
    const base = `https://mojo72549-arch.github.io/mind-reset-daily/tayvoriq/runs/${runId}`;
    const youtubeVideoUrl = `${base}/short_youtube.mp4`;
    const tiktokVideoUrl = `${base}/short_tiktok.mp4`;
    const reviewUrl = `${base}/`;

    const packageCheck = await verifyCommittedReviewPackage(env, runId);
    if (!packageCheck.ok) {
      const transient = packageCheck.transient === true;
      const missing = packageCheck.missing.length ? packageCheck.missing.join(', ') : '';
      const callbackText = transient
        ? 'Review-Paket konnte gerade nicht verifiziert werden. Bitte erneut versuchen.'
        : (missing ? `Review-Paket noch nicht vollständig: ${missing}` : 'Review-Paket noch nicht vollständig.');
      if (callback?.id) {
        // Button callbacks must never flood the chat with the same transient
        // repository error. Telegram's callback alert is the single response.
        await answerCallback(env, callback.id, callbackText, true);
      } else {
        const detail = transient ? `GitHub-Prüfung vorübergehend nicht verfügbar (HTTP ${packageCheck.status || 0})`
          : `Fehlend: ${missing || 'Review-Paket'}`;
        await requireTelegramMessage(await telegram(
          env,
          chatId,
          `❌ Review ${runId} kann noch nicht freigegeben werden. ${detail}. Keine Freigabe gespeichert.`,
        ));
      }
      return new Response(
        transient ? 'review package verification temporarily unavailable' : 'platform package unavailable',
        { status: transient ? 503 : 409 },
      );
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

const REVIEW_REASONS = {
  visuals: 'Bildmaterial oder Bildgestaltung entspricht nicht der Freigabe.',
  voice: 'Stimme, Aussprache oder Ton entspricht nicht der Freigabe.',
  content: 'Inhalt oder Aussage entspricht nicht der Freigabe.',
  other: 'Anderer Grund. Konkrete Korrektur muss noch eingegrenzt werden.',
};

async function askForReviewReason(env, chatId, runId) {
  const button = (text, reason) => ({ text, callback_data: `tayvoriq:reason:${runId}:${reason}` });
  try {
    await requireTelegramMessage(await telegramWithMarkup(env, chatId,
      `❌ Video ${runId} abgelehnt. Warum hast du es abgelehnt?`,
      { inline_keyboard: [[button('Bildmaterial', 'visuals'), button('Stimme / Ton', 'voice')],
        [button('Inhalt', 'content'), button('Anderes', 'other')]] }));
  } catch {
    console.warn('Review rejection saved; reason prompt could not be delivered', runId);
  }
}

async function reviewRepoFile(env, path, write) {
  const repository = env.GITHUB_REPOSITORY || 'mojo72549-arch/tayvoriq-control-plane';
  const headers = {
    Authorization: `Bearer ${env.GITHUB_TOKEN}`, Accept: 'application/vnd.github+json',
    'User-Agent': 'tayvoriq-telegram-approval', 'Content-Type': 'application/json',
  };
  const url = `https://api.github.com/repos/${repository}/contents/${path}`;
  if (write) {
    return fetch(url, { method: 'PUT', headers, body: JSON.stringify(write) });
  }
  const response = await fetch(url + '?ref=main', { headers, cache: 'no-store' });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error('review state unavailable');
  const file = await response.json();
  if (!file.sha || file.encoding !== 'base64') throw new Error('review state unreadable');
  const bytes = Uint8Array.from(atob(file.content.replace(/\s/g, '')), c => c.charCodeAt(0));
  return { sha: file.sha, data: JSON.parse(new TextDecoder().decode(bytes)) };
}

async function storeReviewRejection(env, runId, telegramMessageId, reason, action, reasonCode) {
  if (!/^\d{1,20}$/.test(runId)) return { ok: false };
  const path = `.automation/tayvoriq-artifact-decisions/${runId}.json`;
  try {
    const existing = await reviewRepoFile(env, path);
    const pointer = (await reviewRepoFile(env, '.github/state/tayvoriq-active-production-request.json'))?.data;
    if (pointer?.schema !== 'tayvoriq-active-production-request-v1' ||
        pointer.state !== 'COMPLETED' || String(pointer.golden_path_run_id) !== runId ||
        !/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(pointer.request_id||'')) return {ok: false};
    let record;
    if (existing) {
      record = existing.data;
      if (record.schema !== 'tayvoriq-artifact-approval' || String(record.review_id) !== runId ||
          record.state !== 'REJECTED' || record.request_id !== pointer.request_id ||
          !pointer.source_context_sha256 || record.source_context_sha256 !== pointer.source_context_sha256 ||
          (telegramMessageId !== null && telegramMessageId !== record.telegram_message_id)) {
        return { ok: false };
      }
      if (reason && record.rejection_reason && reasonCode !== record.rejection_reason_code) return {ok: false};
      if (action && ((!reason && !record.rejection_reason) ||
          (record.followup_action && record.followup_action !== action))) return {ok: false};
      if ((!reason || record.rejection_reason) && (!action || record.followup_action === action)) {
        return {ok: true, needsReason: !record.rejection_reason, followupAction: record.followup_action};
      }
      if (reason && !record.rejection_reason) {
        record = {...record, rejection_reason: reason, rejection_reason_code: reasonCode};
      }
      if (action) record = {...record, followup_action: action, followup_requested_at: new Date().toISOString()};
    } else {
      if (reason || action) return { ok: false };
      const request = (await reviewRepoFile(env, `requests/${pointer.request_id}.json`))?.data;
      const receipt = request?.production_completion;
      if (request?.request_id !== pointer.request_id || !pointer.source_context_sha256 ||
          request.source_context_sha256 !== pointer.source_context_sha256 ||
          receipt?.state !== 'REVIEW_READY' || String(receipt.golden_path_run_id) !== runId ||
          !Number.isSafeInteger(receipt.telegram_message_id) || receipt.telegram_message_id <= 0 ||
          (telegramMessageId !== null && receipt.telegram_message_id !== telegramMessageId)) return { ok: false };
      if (await reviewRepoFile(env, `.automation/tayvoriq-reviews/${runId}.json`)) return { ok: false };
      record = {
        schema: 'tayvoriq-artifact-approval', review_id: runId, state: 'REJECTED',
        request_id: pointer.request_id, source_context_sha256: pointer.source_context_sha256,
        telegram_message_id: receipt.telegram_message_id, decided_via: 'telegram_legacy_review_rejection',
        decision_id: `telegram-legacy-reject-${runId}`, decided_at: new Date().toISOString(),
      };
    }
    const bytes = new TextEncoder().encode(JSON.stringify(record, null, 2) + '\n');
    const response = await reviewRepoFile(env, path, {
      branch: 'main', message: `Record Telegram review rejection ${runId}`,
      content: btoa(Array.from(bytes, c => String.fromCharCode(c)).join('')),
      ...(existing ? { sha: existing.sha } : {}),
    });
    return { ok: response.ok, needsReason: !record.rejection_reason, followupAction: record.followup_action };
  } catch {
    return { ok: false };
  }
}

async function decideArtifactReview(env, callback, chatId, action, reviewId) {
  const github = `https://api.github.com/repos/${env.GITHUB_REPOSITORY}`;
  const githubHeaders = {
    Authorization: `Bearer ${env.GITHUB_TOKEN}`, Accept: 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'tayvoriq-telegram-approval',
    'Content-Type': 'application/json',
  };
  const path = `.automation/tayvoriq-artifact-decisions/${reviewId}.json`;
  const messageId = callback?.message?.message_id;
  try {
    if (!Number.isSafeInteger(messageId) || messageId <= 0) throw new Error('invalid message');
    const current = await fetch(`${github}/contents/${path}?ref=main`, { headers: githubHeaders, cache: 'no-store' });
    if (!current.ok) throw new Error('review binding unavailable');
    const file = await current.json();
    if (file.encoding !== 'base64' || !file.sha) throw new Error('binding unreadable');
    const binding = JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(file.content.replace(/\s/g, '')), c => c.charCodeAt(0))));
    if (binding.schema !== 'tayvoriq-artifact-approval' || String(binding.review_id) !== reviewId
        || binding.telegram_message_id !== messageId || binding.state !== 'PENDING') {
      await answerCallback(env, callback.id, 'Diese Entscheidung wurde bereits verarbeitet oder gehört zu einem anderen Review.', true);
      return new Response('review not pending', { status: 409 });
    }
    const decision = { ...binding, state: action === 'approve' ? 'APPROVED' : 'REJECTED',
      decision_id: String(callback.id), decided_at: new Date().toISOString(), decided_via: 'telegram_callback' };
    const bytes = new TextEncoder().encode(JSON.stringify(decision, null, 2) + '\n');
    const content = btoa(Array.from(bytes, b => String.fromCharCode(b)).join(''));
    const saved = await fetch(`${github}/contents/${path}`, { method: 'PUT', headers: githubHeaders,
      body: JSON.stringify({ message: `Record Telegram review decision ${reviewId}`, branch: 'main', sha: file.sha, content }) });
    if (!saved.ok) throw new Error('decision compare-and-swap failed');
    await answerCallback(env, callback.id, action === 'approve' ? 'Freigabe gespeichert.' : 'Video abgelehnt.');
    await clearKeyboard(env, chatId, messageId);
    if (action === 'reject') await askForReviewReason(env, chatId, reviewId);
    return new Response('ok');
  } catch {
    await answerCallback(env, callback.id, 'Entscheidung konnte gerade nicht bestätigt werden. Bitte erneut versuchen.', true);
    return new Response('review decision unavailable', { status: 503 });
  }
}

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

async function verifyCommittedReviewPackage(env, runId) {
  const safeRunId = String(runId || '').trim();
  if (!/^\d+$/.test(safeRunId)) {
    return { ok: false, missing: ['ungueltige Review-ID'], status: 400, transient: false };
  }

  const required = ['index.html', 'job.json', 'preapproval_ai_audit.json', 'short_youtube.mp4', 'short_tiktok.mp4'];
  const url = `https://api.github.com/repos/mojo72549-arch/mind-reset-daily/contents/tayvoriq/runs/${safeRunId}?ref=main`;
  const headers = {
    Authorization: `Bearer ${env.GITHUB_TOKEN}`,
    Accept: 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
    'User-Agent': 'tayvoriq-telegram-approval',
    'Cache-Control': 'no-cache',
  };

  let lastStatus = 0;
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    let response;
    try {
      response = await fetch(url, { headers, cache: 'no-store' });
    } catch {
      lastStatus = 0;
      if (attempt < 3) {
        await new Promise(resolve => setTimeout(resolve, attempt * 250));
        continue;
      }
      return { ok: false, missing: [], status: 0, transient: true };
    }

    lastStatus = response.status;
    if (response.ok) {
      const items = await response.json();
      if (!Array.isArray(items)) {
        return { ok: false, missing: [], status: response.status, transient: true };
      }
      const names = new Set(items.map(item => String(item?.name || '')));
      const missing = required.filter(name => !names.has(name));
      return { ok: missing.length === 0, missing, status: response.status, transient: false };
    }

    const retryable = [403, 404, 429].includes(response.status) || response.status >= 500;
    if (!retryable) {
      return { ok: false, missing: [], status: response.status, transient: true };
    }
    if (attempt < 3) {
      await new Promise(resolve => setTimeout(resolve, attempt * 250));
    }
  }

  // A persistent 404 means the review commit is genuinely not visible on main.
  // Rate limits and 5xx failures are repository availability problems, not
  // evidence that every review artifact is missing.
  if (lastStatus === 404) {
    return { ok: false, missing: required, status: lastStatus, transient: false };
  }
  return { ok: false, missing: [], status: lastStatus, transient: true };
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

async function replacementTrendStatus(env, pointer) {
  const runId = pointer?.golden_path_run_id;
  const slot = String(pointer?.selection_id || '').match(/(?:^|-)(morning|evening)(?:-|$)/)?.[1];
  if (pointer?.state !== 'COMPLETED' || !Number.isSafeInteger(runId) || runId <= 0 || !slot) return null;
  const id = `review-${slot}-${runId}`;
  const stateRoot = '.automation/tayvoriq-agent-v2';
  const [decision, plan, status, delivery] = await Promise.all([
    reviewRepoFile(env, `.automation/tayvoriq-artifact-decisions/${runId}.json`),
    reviewRepoFile(env, `.github/state/rejected-review-followups/${runId}.json`),
    reviewRepoFile(env, `${stateRoot}/review-trend-status/${id}.json`),
    reviewRepoFile(env, `${stateRoot}/deliveries/${id}.json`),
  ]).then(files => files.map(file => file?.data));
  if (decision?.state !== 'REJECTED' || decision.request_id !== pointer.request_id ||
      decision.source_context_sha256 !== pointer.source_context_sha256) return null;
  const planBound = plan?.selection_id === id && plan.rejected_run_id === runId &&
    plan.request_id === pointer.request_id && plan.source_context_sha256 === pointer.source_context_sha256;
  if (decision.followup_action !== 'new_trends' && !(planBound && plan.new_trends_requested === true)) return null;
  if (delivery?.selection_id === id && delivery.telegram_delivery_verified === true &&
      Number.isSafeInteger(delivery.telegram_message_id) && delivery.telegram_message_id > 0) {
    return {text:`TAYVORIQ · Neue Trendauswahl in Telegram bereit. Nachricht ${delivery.telegram_message_id}.`};
  }
  const boundStatus = status?.schema === 'tayvoriq-review-trend-status-v1' && status.selection_id === id ? status : {};
  if (boundStatus.state === 'BLOCKED') return {text:`TAYVORIQ · Die Ersatzrecherche ist beendet. ${boundStatus.detail || ''}`.trim()};
  const requested = Date.parse((planBound && plan.research_requested_at) || decision.followup_requested_at || '');
  const started = Date.parse(boundStatus.updated_at || '');
  const date = Date.parse(boundStatus.deadline_at || '');
  const deadline = Number.isFinite(date) ? date : (Number.isFinite(requested) ? requested : started) + 600000;
  if (Date.now() >= deadline) return {text:'TAYVORIQ · Die Frist ist abgelaufen. Eine Trendauswahl oder Abschlussmeldung ist noch unbestätigt.'};
  const text = boundStatus.state === 'SEARCHING' || boundStatus.state === 'WAITING'
    ? 'TAYVORIQ · Die Ersatzrecherche läuft.' : 'TAYVORIQ · Die Ersatzrecherche wurde angefordert.';
  return {text, pending:true};
}

async function routineTrendStatus(env) {
  const stateRoot = '.automation/tayvoriq-agent-v2';
  const queue = (await reviewRepoFile(env, `${stateRoot}/research-retry.json`))?.data;
  const now = new Date();
  const today = berlinDateSlot(now).date;
  if (queue?.schema !== 'tayvoriq-research-retry-v1' || queue.berlin_date !== today ||
      !['morning', 'evening'].includes(queue.slot)) return null;
  const title = `TAYVORIQ · ${queue.slot === 'morning' ? 'Morgenrecherche' : 'Abendrecherche'}`;
  if (queue.state === 'DELIVERED') {
    const id = `${today.replaceAll('-', '')}-${queue.slot}-agentv2`;
    const receipt = (await reviewRepoFile(env, `${stateRoot}/deliveries/${id}.json`))?.data;
    return receipt?.selection_id === id && receipt.telegram_delivery_verified === true &&
      Number.isSafeInteger(receipt.telegram_message_id) && receipt.telegram_message_id > 0
      ? `${title}\nTrendauswahl in Telegram bestätigt · Nachricht ${receipt.telegram_message_id}.` : null;
  }
  const detail = queue.status_detail || 'Die letzte Recherche ergab noch keine bestätigte Trendauswahl.';
  if (queue.state === 'WAITING' && Number(queue.valid_until_epoch) * 1000 > now.getTime()) {
    const retry = Number(queue.retry_at_epoch) * 1000;
    const next = retry > now.getTime() ? `Nächster Versuch frühestens um ${new Intl.DateTimeFormat('de-DE', {
      timeZone:'Europe/Berlin', hour:'2-digit', minute:'2-digit',
    }).format(retry)} Uhr.` : 'Der nächste automatische Versuch ist fällig.';
    return `${title}\n${detail}\n${next}`;
  }
  if (!['WAITING','EXHAUSTED','EXTERNAL_BLOCKER'].includes(queue.state)) return null;
  return `${title}\n${queue.state === 'EXTERNAL_BLOCKER' ? 'Die Recherche ist durch einen Anbieter blockiert.' : 'Das Recherchefenster ist beendet.'}\n${detail}`;
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

async function answerCallback(env, callbackQueryId, text, alert = false) {
  return telegramMethod(env, 'answerCallbackQuery', {
    callback_query_id: callbackQueryId,
    text,
    show_alert: Boolean(alert),
  });
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
