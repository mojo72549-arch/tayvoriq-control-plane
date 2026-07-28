package com.projectlumen.pilot.robust;

import android.content.Context;
import android.content.SharedPreferences;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;

import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import java.security.MessageDigest;
import java.util.concurrent.atomic.AtomicLong;

import javax.crypto.KeyGenerator;
import javax.crypto.Mac;
import javax.crypto.SecretKey;

/** Keystore-backed six-digit parent PIN and short-lived unlock session. */
final class ParentalControl {
    interface Listener { void onStateChanged(boolean unlocked, String reason); }

    static final long UNLOCK_MS = 10L * 60L * 1000L;
    private static final String KEY_ALIAS = "lumen_parent_pin_hmac_v1";
    private static final String PREFS = "lumen_parental_control_v1";
    private static final String SIGNATURE = "pin_signature";
    private static final String PIN_SET = "pin_set";
    private static final String FAILED = "failed_attempts";
    private static final String LOCKED_UNTIL = "locked_until_epoch";
    private static final AtomicLong GENERATION = new AtomicLong(1);
    private static final Handler MAIN = new Handler(Looper.getMainLooper());

    private static volatile Context app;
    private static volatile long unlockedUntilElapsed;
    private static volatile Listener listener;
    private static final Runnable EXPIRY = () -> lock("timeout");

    private ParentalControl() { }

    static void initialize(Context context) {
        app = context.getApplicationContext();
        unlockedUntilElapsed = 0L;
        GENERATION.incrementAndGet();
    }

    static void setListener(Listener value) { listener = value; }

    static long generation() {
        isUnlocked();
        return GENERATION.get();
    }

    static boolean hasPin() {
        SharedPreferences prefs = prefs();
        return prefs != null && prefs.getBoolean(PIN_SET, false)
                && !prefs.getString(SIGNATURE, "").isBlank();
    }

    static void setInitialPin(String pin) throws Exception {
        requirePin(pin);
        if (hasPin()) throw new IllegalStateException("Eine Eltern-PIN ist bereits eingerichtet.");
        storeSignature(pin);
        unlockWithoutVerification("pin-created");
    }

    static void changePin(String currentPin, String newPin) throws Exception {
        requirePin(newPin);
        if (!verify(currentPin)) throw new SecurityException("Die aktuelle Eltern-PIN ist falsch.");
        storeSignature(newPin);
        unlockWithoutVerification("pin-changed");
    }

    static boolean unlock(String pin) throws Exception {
        requireInitialized();
        long remaining = lockoutRemainingMs();
        if (remaining > 0) {
            throw new SecurityException("Zu viele Fehlversuche. Bitte noch "
                    + Math.max(1, (remaining + 999) / 1000) + " Sekunden warten.");
        }
        if (!hasPin()) throw new IllegalStateException("Zuerst muss eine Eltern-PIN eingerichtet werden.");
        if (!verify(pin)) {
            registerFailure();
            return false;
        }
        prefs().edit().putInt(FAILED, 0).remove(LOCKED_UNTIL).apply();
        unlockWithoutVerification("pin-verified");
        return true;
    }

    static boolean isUnlocked() {
        long until = unlockedUntilElapsed;
        if (until <= 0L) return false;
        if (SystemClock.elapsedRealtime() >= until) {
            lock("timeout");
            return false;
        }
        return true;
    }

    static long unlockRemainingMs() {
        return isUnlocked() ? Math.max(0L, unlockedUntilElapsed - SystemClock.elapsedRealtime()) : 0L;
    }

    static long lockoutRemainingMs() {
        SharedPreferences prefs = prefs();
        if (prefs == null) return 0L;
        return Math.max(0L, prefs.getLong(LOCKED_UNTIL, 0L) - System.currentTimeMillis());
    }

    static void lock(String reason) {
        boolean changed = unlockedUntilElapsed > 0L;
        unlockedUntilElapsed = 0L;
        MAIN.removeCallbacks(EXPIRY);
        if (changed) {
            GENERATION.incrementAndGet();
            notifyListener(false, reason == null ? "locked" : reason);
        }
    }

    private static void unlockWithoutVerification(String reason) {
        unlockedUntilElapsed = SystemClock.elapsedRealtime() + UNLOCK_MS;
        GENERATION.incrementAndGet();
        MAIN.removeCallbacks(EXPIRY);
        MAIN.postDelayed(EXPIRY, UNLOCK_MS);
        notifyListener(true, reason);
    }

    private static void notifyListener(boolean unlocked, String reason) {
        Listener value = listener;
        if (value != null) MAIN.post(() -> value.onStateChanged(unlocked, reason));
    }

    private static void registerFailure() {
        SharedPreferences prefs = prefs();
        int attempts = prefs.getInt(FAILED, 0) + 1;
        SharedPreferences.Editor edit = prefs.edit().putInt(FAILED, attempts);
        if (attempts >= 5) {
            int level = Math.min(4, attempts - 5);
            long wait = Math.min(5L * 60L * 1000L, 30_000L << level);
            edit.putLong(LOCKED_UNTIL, System.currentTimeMillis() + wait);
        }
        edit.apply();
    }

    private static boolean verify(String pin) throws Exception {
        requirePin(pin);
        String stored = prefs().getString(SIGNATURE, "");
        if (stored.isBlank()) return false;
        byte[] expected = Base64.decode(stored, Base64.NO_WRAP);
        byte[] actual = sign(pin);
        return MessageDigest.isEqual(expected, actual);
    }

    private static void storeSignature(String pin) throws Exception {
        byte[] signature = sign(pin);
        prefs().edit()
                .putBoolean(PIN_SET, true)
                .putString(SIGNATURE, Base64.encodeToString(signature, Base64.NO_WRAP))
                .putInt(FAILED, 0)
                .remove(LOCKED_UNTIL)
                .apply();
    }

    private static byte[] sign(String pin) throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(getOrCreateKey());
        return mac.doFinal(("PROJECT-LUMEN-PARENT-PIN-V1:" + pin)
                .getBytes(StandardCharsets.UTF_8));
    }

    private static SecretKey getOrCreateKey() throws Exception {
        KeyStore store = KeyStore.getInstance("AndroidKeyStore");
        store.load(null);
        KeyStore.Entry existing = store.getEntry(KEY_ALIAS, null);
        if (existing instanceof KeyStore.SecretKeyEntry) {
            return ((KeyStore.SecretKeyEntry) existing).getSecretKey();
        }
        KeyGenerator generator = KeyGenerator.getInstance(
                KeyProperties.KEY_ALGORITHM_HMAC_SHA256, "AndroidKeyStore");
        generator.init(new KeyGenParameterSpec.Builder(KEY_ALIAS,
                KeyProperties.PURPOSE_SIGN | KeyProperties.PURPOSE_VERIFY)
                .setDigests(KeyProperties.DIGEST_SHA256)
                .build());
        return generator.generateKey();
    }

    private static SharedPreferences prefs() {
        Context context = app;
        return context == null ? null : context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    private static void requireInitialized() {
        if (app == null) throw new IllegalStateException("Jugendschutz ist noch nicht initialisiert.");
    }

    private static void requirePin(String pin) {
        if (pin == null || !pin.matches("\\d{6}")) {
            throw new IllegalArgumentException("Die Eltern-PIN muss genau 6 Ziffern haben.");
        }
    }
}
