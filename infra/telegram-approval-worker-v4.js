import v3 from './telegram-approval-worker-v3.js';

export default {
  async fetch(request, env) {
    const response = await v3.fetch(request, env);
    // Telegram retries webhook updates when the endpoint returns 5xx.
    // The v3 worker already reports the error to Telegram, so acknowledge the
    // update to prevent an endless duplicate-notification loop.
    if (response && response.status >= 500) {
      console.error('telegram worker upstream failure acknowledged to stop retry loop', response.status);
      return new Response('acknowledged upstream failure', { status: 200 });
    }
    return response;
  },
};
