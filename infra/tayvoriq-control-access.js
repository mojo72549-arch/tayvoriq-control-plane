// The private Telegram conversation is the existing operator identity.
const host = 'tayvoriq-control-center.vercel.app';
const repo = 'mojo72549-arch/tayvoriq-control-plane';

export async function controlAccess(request, env) {
  if (request.method !== 'POST' || !env.TELEGRAM_WEBHOOK_SECRET ||
      request.headers.get('X-Telegram-Bot-Api-Secret-Token') !== env.TELEGRAM_WEBHOOK_SECRET) return null;
  let message;
  try { ({message} = await request.clone().json()); } catch { return null; }
  if (message?.text?.trim() !== '/control') return null;
  const owner = String(env.TELEGRAM_CHAT_ID || '');
  if (!owner || message.chat?.type !== 'private' || message.from?.is_bot !== false ||
      String(message.chat.id) !== owner || String(message.from.id) !== owner) return new Response('ignored');

  const bytes = crypto.getRandomValues(new Uint8Array(32));
  const access = btoa(String.fromCharCode(...bytes)).replaceAll('+','-').replaceAll('/','_').replaceAll('=','');
  const hash = new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(access)));
  const digest = Array.from(hash, n => n.toString(16).padStart(2,'0')).join('');
  const now = Date.now();
  const grant = {schema:'tayvoriq-operator-access-v1', role:'operator', owner:'mojo72549-arch', state:'ACTIVE',
    token_sha256:digest, allowed_hosts:[host], issued_at:new Date(now).toISOString(),
    link_expires_at:new Date(now + 10*60000).toISOString(), expires_at:new Date(now + 30*86400000).toISOString()};
  try {
    const saved = await fetch('https://api.github.com/repos/'+repo+'/contents/state/tayvoriq-operator-access/'+digest+'.json', {
      method:'PUT', headers:{Authorization:'Bearer '+env.GITHUB_TOKEN, 'Content-Type':'application/json',
        Accept:'application/vnd.github+json', 'User-Agent':'tayvoriq-operator-access'},
      body:JSON.stringify({branch:'main', message:'Register private Control Center launch', content:btoa(JSON.stringify(grant))})
    });
    if (!saved.ok) return new Response('grant unavailable',{status:503});
    const delivered = await fetch('https://api.telegram.org/bot'+env.TELEGRAM_BOT_TOKEN+'/sendMessage', {
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({chat_id:owner,protect_content:true,text:'Öffne deinen persönlichen Zugang innerhalb von zehn Minuten.',
        reply_markup:{inline_keyboard:[[{text:'Mein Control Center öffnen',url:'https://'+host+'/#access='+access}]]}})
    });
    if (!delivered.ok || (await delivered.json()).ok !== true) return new Response('delivery unavailable',{status:503});
    return new Response('ok');
  } catch { return new Response('temporarily unavailable',{status:503}); }
}
