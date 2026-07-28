package com.projectlumen.pilot.robust;

import android.content.Context;
import android.content.SharedPreferences;
import android.os.SystemClock;

import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

final class ParentalControl {
    enum VerifyResult { OK, WRONG, LOCKED, NOT_CONFIGURED, ERROR }

    private static final String PREFS = "lumen_parental_control_v1";
    private static final String KEY_SALT = "pin_salt";
    private static final String KEY_HASH = "pin_hash";
    private static final String KEY_FAILURES = "failures";
    private static final String KEY_LOCKOUT_UNTIL = "lockout_until_wall";
    private static final long SESSION_MS = 5L * 60L * 1000L;
    private static final long GRANT_MS = 30_000L;

    private static volatile long unlockedUntilElapsed;
    private static final Map<String, Grant> GRANTS = new ConcurrentHashMap<>();

    private final SharedPreferences prefs;

    ParentalControl(Context context) {
        prefs = context.getApplicationContext()
                .getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    boolean hasPin() {
        return !prefs.getString(KEY_SALT, "").isBlank()
                && !prefs.getString(KEY_HASH, "").isBlank();
    }

    boolean isUnlocked() {
        return hasPin() && SystemClock.elapsedRealtime() < unlockedUntilElapsed;
    }

    long remainingSessionMs() {
        return isUnlocked() ? Math.max(0L,
                unlockedUntilElapsed - SystemClock.elapsedRealtime()) : 0L;
    }

    long remainingLockoutMs() {
        return Math.max(0L, prefs.getLong(KEY_LOCKOUT_UNTIL, 0L)
                - System.currentTimeMillis());
    }

    void configure(String pin, String confirmation) throws Exception {
        if (!PinSecurity.validPin(pin)) {
            throw new IllegalArgumentException(
                    "Die Eltern-PIN muss aus 4 bis 8 Ziffern bestehen.");
        }
        if (!pin.equals(confirmation)) {
            throw new IllegalArgumentException("Die beiden PIN-Eingaben stimmen nicht überein.");
        }
        PinSecurity.Record record = PinSecurity.create(pin);
        prefs.edit()
                .putString(KEY_SALT, record.salt)
                .putString(KEY_HASH, record.hash)
                .putInt(KEY_FAILURES, 0)
                .remove(KEY_LOCKOUT_UNTIL)
                .apply();
        unlockedUntilElapsed = SystemClock.elapsedRealtime() + SESSION_MS;
    }

    VerifyResult verifyAndUnlock(String pin) {
        if (!hasPin()) return VerifyResult.NOT_CONFIGURED;
        if (remainingLockoutMs() > 0L) return VerifyResult.LOCKED;
        try {
            boolean valid = PinSecurity.verify(pin,
                    prefs.getString(KEY_SALT, ""),
                    prefs.getString(KEY_HASH, ""));
            if (valid) {
                prefs.edit().putInt(KEY_FAILURES, 0)
                        .remove(KEY_LOCKOUT_UNTIL).apply();
                unlockedUntilElapsed = SystemClock.elapsedRealtime() + SESSION_MS;
                return VerifyResult.OK;
            }
            registerFailure();
            return remainingLockoutMs() > 0L ? VerifyResult.LOCKED : VerifyResult.WRONG;
        } catch (Exception failure) {
            return VerifyResult.ERROR;
        }
    }

    VerifyResult changePin(String oldPin, String newPin, String confirmation) {
        VerifyResult verified = verifyAndUnlock(oldPin);
        if (verified != VerifyResult.OK) return verified;
        try {
            configure(newPin, confirmation);
            return VerifyResult.OK;
        } catch (Exception failure) {
            return VerifyResult.ERROR;
        }
    }

    void lock() {
        unlockedUntilElapsed = 0L;
    }

    String issuePlaybackGrant(String channelId) {
        if (!isUnlocked() || channelId == null || channelId.isBlank()) return "";
        purgeExpiredGrants();
        String token = UUID.randomUUID().toString();
        GRANTS.put(token, new Grant(channelId,
                SystemClock.elapsedRealtime() + GRANT_MS));
        return token;
    }

    static boolean consumePlaybackGrant(String channelId, String token) {
        if (channelId == null || token == null || token.isBlank()) return false;
        Grant grant = GRANTS.remove(token);
        return grant != null
                && SystemClock.elapsedRealtime() <= grant.expiresAt
                && channelId.equals(grant.channelId);
    }

    private void registerFailure() {
        int failures = prefs.getInt(KEY_FAILURES, 0) + 1;
        SharedPreferences.Editor editor = prefs.edit().putInt(KEY_FAILURES, failures);
        if (failures >= 5) {
            int exponent = Math.min(4, failures - 5);
            long seconds = Math.min(300L, 30L * (1L << exponent));
            editor.putLong(KEY_LOCKOUT_UNTIL,
                    System.currentTimeMillis() + seconds * 1000L);
        }
        editor.apply();
    }

    private static void purgeExpiredGrants() {
        long now = SystemClock.elapsedRealtime();
        GRANTS.entrySet().removeIf(entry -> entry.getValue().expiresAt < now);
    }

    private static final class Grant {
        final String channelId;
        final long expiresAt;

        Grant(String channelId, long expiresAt) {
            this.channelId = channelId;
            this.expiresAt = expiresAt;
        }
    }
}
