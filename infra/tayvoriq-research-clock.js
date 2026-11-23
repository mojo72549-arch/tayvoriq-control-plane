const ROOT = '.automation/tayvoriq-agent-v2';
const ZONE = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Europe/Berlin', year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
});

function clockParts(timestamp) {
  const parts = Object.fromEntries(ZONE.formatToParts(timestamp).map(({type,value}) => [type,value]));
  return { day: `${parts.year}-${parts.month}-${parts.day}`, minute: Number(parts.hour) * 60 + Number(parts.minute) };
}

function deliveryConfirmed(receipt, selection) {
  return receipt?.selection_id === selection && receipt.telegram_delivery_verified === true
    && Number.isSafeInteger(receipt.telegram_message_id) && receipt.telegram_message_id > 0;
}

export async function requestResearchTick(scheduledTime, env, timestamp = Date.now(), fetcher = fetch) {
  if (!Number.isFinite(scheduledTime) || scheduledTime > timestamp || timestamp - scheduledTime >= 20 * 60_000) return false;
  const {day, minute} = clockParts(timestamp);
  const api = `https://api.github.com/repos/${env.GITHUB_REPOSITORY}`;
  const headers = {
    Authorization: `Bearer ${env.GITHUB_TOKEN}`, Accept: 'application/vnd.github+json',
    'User-Agent': 'tayvoriq-research-clock', 'X-GitHub-Api-Version': '2022-11-28',
  };
  async function read(path) {
    const response = await fetcher(`${api}/contents/${path}?ref=main`, {headers, cache:'no-store'});
    if (response.status === 404) return null;
    if (!response.ok) throw Error(`TAYVORIQ research state unreadable (${response.status})`);
    const file = await response.json();
    if (file.encoding !== 'base64') throw Error('TAYVORIQ research state unreadable');
    return JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(file.content), char => char.charCodeAt(0))));
  }

  const retry = await read(`${ROOT}/research-retry.json`);
  const epoch = timestamp / 1000;
  const sameDay = retry?.berlin_date === day;
  const retryDue = sameDay && retry.state === 'WAITING' && ['morning','evening'].includes(retry.slot)
    && Number.isFinite(retry.retry_at_epoch) && retry.retry_at_epoch <= epoch && epoch < retry.valid_until_epoch;
  const catchup = minute >= 335 && minute < 365 ? 'morning'
    : minute >= 1145 && minute < 1175 ? 'evening' : '';
  const slot = retryDue ? retry.slot : catchup;
  if (!slot || (!retryDue && sameDay && retry.slot === slot)) return false;
  const selection = `${day.replaceAll('-', '')}-${slot}-agentv2`;
  const receipt = await read(`${ROOT}/deliveries/${selection}.json`);
  if (deliveryConfirmed(receipt, selection)) return false;
  const response = await fetcher(`${api}/dispatches`, {
    method:'POST', headers:{...headers,'Content-Type':'application/json'},
    body:JSON.stringify({event_type:'tayvoriq_research_tick',client_payload:{
      berlin_date:day, slot, mode:retryDue?'retry':'catchup', scheduled_epoch:Math.floor(scheduledTime / 1000),
    }}),
  });
  if (!response.ok) throw Error(`TAYVORIQ research tick dispatch failed (${response.status})`);
  return true;
}
