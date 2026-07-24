package com.projectlumen.publicpreview;

import android.content.Context;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;
import android.os.Bundle;
import android.provider.Settings;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.security.spec.X509EncodedKeySpec;
import java.util.Base64;

/** Pseudonymous, app-specific installation identifier; never exposes raw ANDROID_ID. */
final class DeviceIdentity {
    private static final String KEY_ALIAS = "project_lumen_device_identity_v1";
    private static final String FILE_NAME = "install-secret.lumen";
    private static final SecureRandom RANDOM = new SecureRandom();
    private DeviceIdentity() {}
    static String id(Context context) {
        try {
            byte[] secret = loadOrCreateSecret(context);
            String androidId = Settings.Secure.getString(context.getContentResolver(), Settings.Secure.ANDROID_ID);
            String material = context.getPackageName() + "|" + (androidId == null ? "" : androidId) + "|"
                    + Base64.getUrlEncoder().withoutPadding().encodeToString(secret);
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(material.getBytes(StandardCharsets.UTF_8));
            return Base64.getUrlEncoder().withoutPadding().encodeToString(digest);
        } catch (Exception failure) { return "unavailable"; }
    }
    static String shortCode(Context context) {
        String id = id(context);
        if (id.length() < 12) return "UNAVAILABLE";
        return id.substring(0, 4).toUpperCase() + "-" + id.substring(4, 8).toUpperCase()
                + "-" + id.substring(8, 12).toUpperCase();
    }
    private static byte[] loadOrCreateSecret(Context context) throws Exception {
        File file = new File(context.getFilesDir(), FILE_NAME);
        if (file.isFile()) {
            byte[] existing = SecureBlobStore.read(context, file, KEY_ALIAS, 4096);
            if (existing.length == 32) return existing;
        }
        byte[] secret = new byte[32]; RANDOM.nextBytes(secret);
        SecureBlobStore.write(context, file, KEY_ALIAS, secret); return secret;
    }
}

/** Verifies and stores short-lived signed software entitlements. */
final class EntitlementStore {
    static final String META_PUBLIC_KEY = "com.projectlumen.ENTITLEMENT_PUBLIC_KEY_B64";
    private static final String KEY_ALIAS = "project_lumen_entitlement_store_v1";
    private static final String FILE_NAME = "entitlement.lumen";
    private static final long CLOCK_SKEW_MS = 5L * 60L * 1000L;
    enum State { UNCONFIGURED, NONE, VALID, EXPIRED, DEVICE_MISMATCH, INVALID }
    static final class Status {
        final State state; final String plan; final long expiresAtMs, offlineUntilMs; final String supportCode;
        Status(State state, String plan, long expiresAtMs, long offlineUntilMs, String supportCode) {
            this.state = state; this.plan = plan; this.expiresAtMs = expiresAtMs;
            this.offlineUntilMs = offlineUntilMs; this.supportCode = supportCode;
        }
        boolean grantsPremium() {
            return state == State.VALID && offlineUntilMs + CLOCK_SKEW_MS >= System.currentTimeMillis();
        }
    }
    private final Context context;
    EntitlementStore(Context context) { this.context = context.getApplicationContext(); }
    synchronized Status status() {
        String key = configuredPublicKey();
        if (key.isBlank()) return new Status(State.UNCONFIGURED, "", 0, 0, "LIC-CONFIG");
        File file = new File(context.getFilesDir(), FILE_NAME);
        if (!file.isFile()) return new Status(State.NONE, "", 0, 0, "LIC-NONE");
        try {
            byte[] token = SecureBlobStore.read(context, file, KEY_ALIAS, 64 * 1024);
            return verify(new String(token, StandardCharsets.UTF_8), key);
        } catch (Exception failure) { return new Status(State.INVALID, "", 0, 0, "LIC-READ"); }
    }
    synchronized Status importToken(String token) {
        String key = configuredPublicKey();
        if (key.isBlank()) return new Status(State.UNCONFIGURED, "", 0, 0, "LIC-CONFIG");
        Status status = verify(token, key);
        if (status.state == State.VALID) {
            try {
                SecureBlobStore.write(context, new File(context.getFilesDir(), FILE_NAME), KEY_ALIAS,
                        token.getBytes(StandardCharsets.UTF_8));
            } catch (Exception failure) { return new Status(State.INVALID, "", 0, 0, "LIC-WRITE"); }
        }
        return status;
    }
    private Status verify(String token, String publicKeyB64) {
        try {
            String[] parts = token == null ? new String[0] : token.trim().split("\\.");
            if (parts.length != 2) return new Status(State.INVALID, "", 0, 0, "LIC-FORMAT");
            byte[] payload = Base64.getUrlDecoder().decode(parts[0]);
            byte[] signature = Base64.getUrlDecoder().decode(parts[1]);
            PublicKey key = KeyFactory.getInstance("RSA").generatePublic(
                    new X509EncodedKeySpec(Base64.getDecoder().decode(publicKeyB64)));
            Signature verifier = Signature.getInstance("SHA256withRSA");
            verifier.initVerify(key); verifier.update(payload);
            if (!verifier.verify(signature)) return new Status(State.INVALID, "", 0, 0, "LIC-SIGNATURE");
            String[] values = new String(payload, StandardCharsets.UTF_8).split("\\|", -1);
            if (values.length != 7 || !"v1".equals(values[0])) return new Status(State.INVALID, "", 0, 0, "LIC-PAYLOAD");
            String device = values[2]; long notBefore = Long.parseLong(values[3]);
            long expires = Long.parseLong(values[4]); long offline = Long.parseLong(values[5]); String plan = values[6];
            if (!DeviceIdentity.id(context).equals(device)) return new Status(State.DEVICE_MISMATCH, plan, expires, offline, "LIC-DEVICE");
            long now = System.currentTimeMillis();
            if (now + CLOCK_SKEW_MS < notBefore) return new Status(State.INVALID, plan, expires, offline, "LIC-NOT-BEFORE");
            if (now > expires + CLOCK_SKEW_MS || now > offline + CLOCK_SKEW_MS)
                return new Status(State.EXPIRED, plan, expires, offline, "LIC-EXPIRED");
            return new Status(State.VALID, plan, expires, offline, "LIC-OK");
        } catch (Exception failure) { return new Status(State.INVALID, "", 0, 0, "LIC-VERIFY"); }
    }
    private String configuredPublicKey() {
        try {
            ApplicationInfo info = context.getPackageManager().getApplicationInfo(context.getPackageName(), PackageManager.GET_META_DATA);
            Bundle data = info.metaData; String value = data == null ? null : data.getString(META_PUBLIC_KEY);
            return value == null ? "" : value.trim();
        } catch (Exception ignored) { return ""; }
    }
}

/** Store-neutral contract. Concrete Play/Amazon adapters belong to store build flavors. */
interface BillingGateway {
    interface Callback { void onResult(boolean success, String supportCode, String entitlementToken); }
    void restorePurchases(Callback callback);
    void startYearlyPurchase(Callback callback);
    static BillingGateway forPilot(Context context) {
        return new BillingGateway() {
            public void restorePurchases(Callback callback) { callback.onResult(false, "BILLING-NOT-CONFIGURED", ""); }
            public void startYearlyPurchase(Callback callback) { callback.onResult(false, "BILLING-NOT-CONFIGURED", ""); }
        };
    }
}
