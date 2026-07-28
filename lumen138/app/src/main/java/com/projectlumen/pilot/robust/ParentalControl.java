package com.projectlumen.pilot.robust;

import android.content.Context;
import android.content.SharedPreferences;
import android.os.SystemClock;

import java.security.MessageDigest;
import java.security.SecureRandom;
import java.text.Normalizer;
import java.util.Base64;
import java.util.Locale;
import java.util.concurrent.ConcurrentHashMap;

import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

final class ParentalControl {
    static final String EXTRA_ADULT_CONTENT = "lumenAdultContent";
    static final long SESSION_TIMEOUT_MS = 5 * 60 * 1000L;

    enum VerifyResult { OK, WRONG, LOCKED }

    private static final String PREFS = "lumen_parental_control_v1";
    private static final String KEY_SALT = "pin_salt";
    private static final String KEY_HASH = "pin_hash";
    private static final String KEY_FAILURES = "pin_failures";
    private static final String KEY_LOCK_UNTIL = "pin_lock_until";
    private static final int PIN_ITERATIONS = 120_000;
    private static final int PIN_BITS = 256;
    private static final int MAX_FAILURES = 5;
    private static final long FAILURE_LOCK_MS = 60_000L;

    private static volatile long unlockedUntilElapsed;
    private static final ConcurrentHashMap<String, Boolean> CLASSIFICATION_CACHE =
            new ConcurrentHashMap<>();

    private ParentalControl() { }

    static boolean hasPin(Context context) {
        SharedPreferences prefs = prefs(context);
        return !prefs.getString(KEY_SALT, "").isBlank()
                && !prefs.getString(KEY_HASH, "").isBlank();
    }

    static void setPin(Context context, char[] pin) throws Exception {
        validatePin(pin);
        byte[] salt = new byte[16];
        new SecureRandom().nextBytes(salt);
        byte[] hash = derive(pin, salt);
        prefs(context).edit()
                .putString(KEY_SALT, Base64.getEncoder().withoutPadding().encodeToString(salt))
                .putString(KEY_HASH, Base64.getEncoder().withoutPadding().encodeToString(hash))
                .remove(KEY_FAILURES)
                .remove(KEY_LOCK_UNTIL)
                .commit();
        clear(pin);
        lockSession();
    }

    static VerifyResult verifyPin(Context context, char[] pin) {
        long now = System.currentTimeMillis();
        SharedPreferences prefs = prefs(context);
        long lockUntil = prefs.getLong(KEY_LOCK_UNTIL, 0L);
        if (lockUntil > now) {
            clear(pin);
            return VerifyResult.LOCKED;
        }
        try {
            String saltText = prefs.getString(KEY_SALT, "");
            String hashText = prefs.getString(KEY_HASH, "");
            if (saltText.isBlank() || hashText.isBlank()) {
                clear(pin);
                return VerifyResult.WRONG;
            }
            byte[] salt = Base64.getDecoder().decode(saltText);
            byte[] expected = Base64.getDecoder().decode(hashText);
            byte[] actual = derive(pin, salt);
            clear(pin);
            if (MessageDigest.isEqual(expected, actual)) {
                prefs.edit().remove(KEY_FAILURES).remove(KEY_LOCK_UNTIL).apply();
                unlockSession();
                return VerifyResult.OK;
            }
        } catch (Throwable ignored) {
            clear(pin);
        }

        int failures = prefs.getInt(KEY_FAILURES, 0) + 1;
        SharedPreferences.Editor editor = prefs.edit();
        if (failures >= MAX_FAILURES) {
            editor.putInt(KEY_FAILURES, 0)
                    .putLong(KEY_LOCK_UNTIL, now + FAILURE_LOCK_MS);
        } else {
            editor.putInt(KEY_FAILURES, failures);
        }
        editor.apply();
        return VerifyResult.WRONG;
    }

    static long lockRemainingMs(Context context) {
        return Math.max(0L, prefs(context).getLong(KEY_LOCK_UNTIL, 0L)
                - System.currentTimeMillis());
    }

    static void unlockSession() {
        unlockedUntilElapsed = SystemClock.elapsedRealtime() + SESSION_TIMEOUT_MS;
    }

    static void touchSession() {
        if (isSessionUnlocked()) unlockSession();
    }

    static void lockSession() {
        unlockedUntilElapsed = 0L;
    }

    static boolean isSessionUnlocked() {
        long until = unlockedUntilElapsed;
        if (until <= 0L) return false;
        if (SystemClock.elapsedRealtime() >= until) {
            unlockedUntilElapsed = 0L;
            return false;
        }
        return true;
    }

    static long sessionRemainingMs() {
        return isSessionUnlocked()
                ? Math.max(0L, unlockedUntilElapsed - SystemClock.elapsedRealtime()) : 0L;
    }

    static boolean isAdult(Channel channel) {
        if (channel == null) return false;
        String key = channel.id + '|' + channel.name.hashCode() + '|' + channel.group.hashCode();
        Boolean cached = CLASSIFICATION_CACHE.get(key);
        if (cached != null) return cached;
        boolean result = isAdultText(channel.name, channel.group, channel.url);
        if (CLASSIFICATION_CACHE.size() >= 120_000) CLASSIFICATION_CACHE.clear();
        CLASSIFICATION_CACHE.put(key, result);
        return result;
    }

    static void clearClassificationCache() {
        CLASSIFICATION_CACHE.clear();
    }

    static boolean isAdultText(String name, String group, String url) {
        String rawName = lower(name);
        String rawGroup = lower(group);
        String normalizedName = padded(normalize(name));
        String normalizedGroup = padded(normalize(group));
        String combined = normalizedName + normalizedGroup;

        if (ageMarker(rawName) || ageMarker(rawGroup)) return true;
        if (containsAnyPhrase(normalizedGroup,
                "xxx", "adult", "adults", "adult only", "adults only",
                "erotik", "erotic", "erotica", "porno", "porn", "pornography",
                "yetiskin", "sadece yetiskin", "mature only", "red light")) return true;
        if (containsAnyPhrase(combined,
                "pornhub", "brazzers", "playboy", "hustler", "penthouse",
                "dorcel", "private tv", "redlight", "blue hustler",
                "vivid", "hot club", "adult channel")) return true;

        String lowerUrl = lower(url);
        return lowerUrl.contains("/adult/") || lowerUrl.contains("/xxx/")
                || lowerUrl.contains("/porn/") || lowerUrl.contains("/porno/")
                || lowerUrl.contains("/erotic/") || lowerUrl.contains("/erotik/")
                || lowerUrl.contains("/18plus/");
    }

    private static boolean ageMarker(String value) {
        if (value == null || value.isBlank()) return false;
        return value.contains("18+") || value.contains("+18")
                || value.contains("18 plus") || value.contains("ab 18")
                || value.contains("18 only") || value.contains("18plus");
    }

    private static boolean containsAnyPhrase(String paddedText, String... phrases) {
        for (String phrase : phrases) {
            String token = " " + normalize(phrase).trim() + " ";
            if (paddedText.contains(token)) return true;
        }
        return false;
    }

    private static String padded(String value) {
        return " " + value.trim() + " ";
    }

    private static String normalize(String value) {
        String source = Normalizer.normalize(value == null ? "" : value,
                Normalizer.Form.NFD).toLowerCase(Locale.ROOT);
        StringBuilder result = new StringBuilder(source.length());
        boolean previousSpace = true;
        for (int index = 0; index < source.length(); index++) {
            char current = source.charAt(index);
            int type = Character.getType(current);
            if (type == Character.NON_SPACING_MARK
                    || type == Character.COMBINING_SPACING_MARK
                    || type == Character.ENCLOSING_MARK) continue;
            if (Character.isLetterOrDigit(current)) {
                result.append(current);
                previousSpace = false;
            } else if (!previousSpace) {
                result.append(' ');
                previousSpace = true;
            }
        }
        int length = result.length();
        if (length > 0 && result.charAt(length - 1) == ' ') result.setLength(length - 1);
        return result.toString();
    }

    private static String lower(String value) {
        return value == null ? "" : value.toLowerCase(Locale.ROOT);
    }

    private static byte[] derive(char[] pin, byte[] salt) throws Exception {
        PBEKeySpec spec = new PBEKeySpec(pin, salt, PIN_ITERATIONS, PIN_BITS);
        try {
            return SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")
                    .generateSecret(spec).getEncoded();
        } finally {
            spec.clearPassword();
        }
    }

    private static void validatePin(char[] pin) {
        if (pin == null || pin.length < 4 || pin.length > 8) {
            throw new IllegalArgumentException("Die Eltern-PIN muss aus 4 bis 8 Ziffern bestehen.");
        }
        for (char value : pin) {
            if (!Character.isDigit(value)) {
                throw new IllegalArgumentException("Die Eltern-PIN darf nur Ziffern enthalten.");
            }
        }
    }

    private static void clear(char[] value) {
        if (value == null) return;
        for (int i = 0; i < value.length; i++) value[i] = '\0';
    }

    private static SharedPreferences prefs(Context context) {
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }
}
