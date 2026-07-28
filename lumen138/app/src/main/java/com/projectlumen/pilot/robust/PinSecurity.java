package com.projectlumen.pilot.robust;

import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;

import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

final class PinSecurity {
    static final int ITERATIONS = 120_000;
    private static final int KEY_BITS = 256;
    private static final int SALT_BYTES = 16;

    static final class Record {
        final String salt;
        final String hash;

        Record(String salt, String hash) {
            this.salt = salt;
            this.hash = hash;
        }
    }

    private PinSecurity() { }

    static boolean validPin(String pin) {
        if (pin == null || pin.length() < 4 || pin.length() > 8) return false;
        for (int i = 0; i < pin.length(); i++) {
            if (!Character.isDigit(pin.charAt(i))) return false;
        }
        return true;
    }

    static Record create(String pin) throws Exception {
        if (!validPin(pin)) {
            throw new IllegalArgumentException("Die Eltern-PIN muss aus 4 bis 8 Ziffern bestehen.");
        }
        byte[] salt = new byte[SALT_BYTES];
        new SecureRandom().nextBytes(salt);
        byte[] hash = derive(pin, salt);
        return new Record(Base64.getEncoder().withoutPadding().encodeToString(salt),
                Base64.getEncoder().withoutPadding().encodeToString(hash));
    }

    static boolean verify(String pin, String saltValue, String hashValue) throws Exception {
        if (!validPin(pin) || saltValue == null || hashValue == null) return false;
        byte[] salt = Base64.getDecoder().decode(saltValue);
        byte[] expected = Base64.getDecoder().decode(hashValue);
        byte[] actual = derive(pin, salt);
        return MessageDigest.isEqual(expected, actual);
    }

    private static byte[] derive(String pin, byte[] salt) throws Exception {
        PBEKeySpec spec = new PBEKeySpec(pin.toCharArray(), salt, ITERATIONS, KEY_BITS);
        try {
            return SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")
                    .generateSecret(spec).getEncoded();
        } finally {
            spec.clearPassword();
        }
    }
}
