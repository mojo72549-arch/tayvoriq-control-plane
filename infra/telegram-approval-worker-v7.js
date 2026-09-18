import v6 from './telegram-approval-worker-v6.js';

/*
 * ZERO-COST TELEGRAM GOLDEN PATH
 *
 * Deliberately do not intercept approve_trend:<selection>:<trend> here.
 * Those callbacks must fall through the legacy chain to worker v2, which
 * dispatches tayvoriq_trend_approved inside the public control-plane repo.
 *
 * This keeps the user path simple:
 * trend list -> select -> approve -> public Golden Path -> Telegram review.
 *
 * The former V7 visual-mode/private-queue bridge is preserved in Git history
 * and in backup/pre-zero-cost-telegram-rollback-20260918.
 */
export default {
  async fetch(request, env) {
    return v6.fetch(request, env);
  },
};
