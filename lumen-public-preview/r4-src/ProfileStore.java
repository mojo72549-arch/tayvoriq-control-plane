package com.projectlumen.publicpreview;

import android.content.Context;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;

import java.io.*;
import java.security.*;
import java.security.cert.CertificateException;
import java.util.*;
import javax.crypto.*;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.PBEKeySpec;

/** Local-only encrypted profile and parental-control state. */
public final class ProfileStore {
    private static final String KEY_ALIAS = "project_lumen_profile_store_v1";
    private static final String FILE_NAME = "profiles-v1.bin";
    private static final int VERSION = 1;
    private static final int MAX_PROFILES = 8;
    private static final int MAX_NAME = 40;
    private static final int PBKDF2_ROUNDS = 120_000;
    private static final SecureRandom RANDOM = new SecureRandom();

    public enum Kind { ADULT, CHILD }

    public static final class Profile {
        public final String id;
        public final String name;
        public final Kind kind;
        private final byte[] pinSalt;
        private final byte[] pinHash;

        Profile(String id, String name, Kind kind, byte[] pinSalt, byte[] pinHash) {
            this.id = id;
            this.name = name;
            this.kind = kind;
            this.pinSalt = pinSalt == null ? new byte[0] : pinSalt.clone();
            this.pinHash = pinHash == null ? new byte[0] : pinHash.clone();
        }
        public boolean hasPin() { return pinSalt.length > 0 && pinHash.length > 0; }
        public boolean isChild() { return kind == Kind.CHILD; }
    }

    public static final class Snapshot {
        public final String activeId;
        public final List<Profile> profiles;
        Snapshot(String activeId, List<Profile> profiles) {
            this.activeId = activeId;
            this.profiles = Collections.unmodifiableList(new ArrayList<>(profiles));
        }
        public Profile active() {
            for (Profile p : profiles) if (p.id.equals(activeId)) return p;
            return profiles.isEmpty() ? null : profiles.get(0);
        }
    }

    private final Context context;
    public ProfileStore(Context context) { this.context = context.getApplicationContext(); }

    public synchronized Snapshot load() {
        try {
            File f = new File(context.getFilesDir(), FILE_NAME);
            if (!f.exists()) return initialSnapshot();
            byte[] all = readLimited(f, 128 * 1024);
            if (all.length < 13) return initialSnapshot();
            DataInputStream in = new DataInputStream(new ByteArrayInputStream(all));
            int ivLen = in.readUnsignedByte();
            if (ivLen < 12 || ivLen > 32 || all.length < 1 + ivLen + 16) return initialSnapshot();
            byte[] iv = new byte[ivLen]; in.readFully(iv);
            byte[] cipherText = new byte[all.length - 1 - ivLen]; in.readFully(cipherText);
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE, key(), new GCMParameterSpec(128, iv));
            return decode(cipher.doFinal(cipherText));
        } catch (Exception ignored) {
            return initialSnapshot();
        }
    }

    public synchronized Snapshot create(String rawName, Kind kind) throws IOException {
        Snapshot s = load();
        if (s.profiles.size() >= MAX_PROFILES) throw new IOException("Maximal acht Profile möglich.");
        String name = sanitizeName(rawName);
        List<Profile> list = new ArrayList<>(s.profiles);
        String id = UUID.randomUUID().toString();
        list.add(new Profile(id, name, kind == null ? Kind.ADULT : kind, null, null));
        Snapshot out = new Snapshot(id, list);
        save(out); return out;
    }

    public synchronized Snapshot setActive(String id) throws IOException {
        Snapshot s = load();
        Profile found = find(s, id);
        if (found == null) throw new IOException("Profil nicht gefunden.");
        Snapshot out = new Snapshot(found.id, s.profiles);
        save(out); return out;
    }

    public synchronized Snapshot delete(String id) throws IOException {
        Snapshot s = load();
        if (s.profiles.size() <= 1) throw new IOException("Mindestens ein Profil muss bestehen bleiben.");
        List<Profile> list = new ArrayList<>();
        for (Profile p : s.profiles) if (!p.id.equals(id)) list.add(p);
        if (list.size() == s.profiles.size()) throw new IOException("Profil nicht gefunden.");
        String active = s.activeId.equals(id) ? list.get(0).id : s.activeId;
        Snapshot out = new Snapshot(active, list);
        save(out); return out;
    }

    public synchronized Snapshot setPin(String profileId, char[] pin) throws IOException {
        Snapshot s = load();
        validatePin(pin);
        byte[] salt = new byte[16]; RANDOM.nextBytes(salt);
        byte[] hash;
        try { hash = hashPin(pin, salt); }
        catch (GeneralSecurityException e) { throw new IOException("PIN konnte nicht geschützt werden.", e); }
        finally { Arrays.fill(pin, '\0'); }
        List<Profile> list = new ArrayList<>();
        boolean found = false;
        for (Profile p : s.profiles) {
            if (p.id.equals(profileId)) {
                if (p.kind != Kind.ADULT) throw new IOException("PIN kann nur für Erwachsenenprofile gesetzt werden.");
                list.add(new Profile(p.id, p.name, p.kind, salt, hash)); found = true;
            } else list.add(p);
        }
        if (!found) throw new IOException("Profil nicht gefunden.");
        Snapshot out = new Snapshot(s.activeId, list); save(out); return out;
    }

    public synchronized boolean verifyPin(String profileId, char[] pin) {
        try {
            Profile p = find(load(), profileId);
            if (p == null || !p.hasPin()) return false;
            byte[] candidate = hashPin(pin, p.pinSalt);
            Arrays.fill(pin, '\0');
            boolean ok = MessageDigest.isEqual(candidate, p.pinHash);
            Arrays.fill(candidate, (byte) 0);
            return ok;
        } catch (Exception ignored) { return false; }
    }

    public static Profile active(Context context) { return new ProfileStore(context).load().active(); }
    public static boolean isChildMode(Context context) {
        Profile p = active(context); return p != null && p.isChild();
    }
    public static String activeId(Context context) {
        Profile p = active(context); return p == null ? "default" : p.id;
    }
    public static String activeName(Context context) {
        Profile p = active(context); return p == null ? "Standard" : p.name;
    }
    public static String favoriteNamespace(Context context) { return "favorites_" + activeId(context); }
    public static String historyNamespace(Context context) { return "history_" + activeId(context); }

    private Snapshot initialSnapshot() {
        Profile p = new Profile("default-adult", "Erwachsene", Kind.ADULT, null, null);
        Snapshot s = new Snapshot(p.id, Collections.singletonList(p));
        try { save(s); } catch (Exception ignored) {}
        return s;
    }

    private void save(Snapshot s) throws IOException {
        try {
            byte[] plain = encode(s);
            byte[] iv = new byte[12]; RANDOM.nextBytes(iv);
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.ENCRYPT_MODE, key(), new GCMParameterSpec(128, iv));
            byte[] encrypted = cipher.doFinal(plain);
            File tmp = new File(context.getFilesDir(), FILE_NAME + ".tmp");
            File target = new File(context.getFilesDir(), FILE_NAME);
            try (FileOutputStream out = new FileOutputStream(tmp)) {
                out.write(iv.length); out.write(iv); out.write(encrypted); out.getFD().sync();
            }
            if (target.exists() && !target.delete()) throw new IOException("Profilstatus konnte nicht ersetzt werden.");
            if (!tmp.renameTo(target)) throw new IOException("Profilstatus konnte nicht gespeichert werden.");
        } catch (GeneralSecurityException e) { throw new IOException("Profilverschlüsselung fehlgeschlagen.", e); }
    }

    private byte[] encode(Snapshot s) throws IOException {
        ByteArrayOutputStream bos = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(bos);
        out.writeInt(VERSION); out.writeUTF(s.activeId == null ? "" : s.activeId);
        out.writeInt(Math.min(MAX_PROFILES, s.profiles.size()));
        for (int i = 0; i < s.profiles.size() && i < MAX_PROFILES; i++) {
            Profile p = s.profiles.get(i);
            out.writeUTF(p.id); out.writeUTF(sanitizeName(p.name)); out.writeByte(p.kind.ordinal());
            out.writeInt(p.pinSalt.length); out.write(p.pinSalt);
            out.writeInt(p.pinHash.length); out.write(p.pinHash);
        }
        out.flush(); return bos.toByteArray();
    }

    private Snapshot decode(byte[] plain) throws IOException {
        DataInputStream in = new DataInputStream(new ByteArrayInputStream(plain));
        int version = in.readInt(); if (version != VERSION) return initialSnapshot();
        String active = in.readUTF(); int count = in.readInt();
        if (count < 1 || count > MAX_PROFILES) return initialSnapshot();
        List<Profile> list = new ArrayList<>();
        for (int i = 0; i < count; i++) {
            String id = in.readUTF(); String name = sanitizeName(in.readUTF());
            int kind = in.readUnsignedByte();
            int sl = in.readInt(); if (sl < 0 || sl > 64) throw new IOException("Ungültige PIN-Daten");
            byte[] salt = new byte[sl]; in.readFully(salt);
            int hl = in.readInt(); if (hl < 0 || hl > 128) throw new IOException("Ungültige PIN-Daten");
            byte[] hash = new byte[hl]; in.readFully(hash);
            list.add(new Profile(id, name, kind == Kind.CHILD.ordinal() ? Kind.CHILD : Kind.ADULT, salt, hash));
        }
        if (find(new Snapshot(active, list), active) == null) active = list.get(0).id;
        return new Snapshot(active, list);
    }

    private SecretKey key() throws GeneralSecurityException, IOException {
        KeyStore ks;
        try { ks = KeyStore.getInstance("AndroidKeyStore"); ks.load(null); }
        catch (CertificateException e) { throw new GeneralSecurityException(e); }
        Key k = ks.getKey(KEY_ALIAS, null);
        if (k instanceof SecretKey) return (SecretKey) k;
        KeyGenerator gen = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
        gen.init(new KeyGenParameterSpec.Builder(KEY_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256).build());
        return gen.generateKey();
    }

    private static byte[] hashPin(char[] pin, byte[] salt) throws GeneralSecurityException {
        PBEKeySpec spec = new PBEKeySpec(pin, salt, PBKDF2_ROUNDS, 256);
        try { return SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256").generateSecret(spec).getEncoded(); }
        finally { spec.clearPassword(); }
    }
    private static void validatePin(char[] pin) throws IOException {
        if (pin == null || pin.length < 4 || pin.length > 8) throw new IOException("PIN muss 4 bis 8 Ziffern haben.");
        for (char c : pin) if (!Character.isDigit(c)) throw new IOException("PIN darf nur Ziffern enthalten.");
    }
    private static Profile find(Snapshot s, String id) {
        if (id == null) return null; for (Profile p : s.profiles) if (id.equals(p.id)) return p; return null;
    }
    private static String sanitizeName(String value) throws IOException {
        String name = value == null ? "" : value.replaceAll("[\\p{Cntrl}]", "").trim();
        if (name.isEmpty()) throw new IOException("Profilname fehlt.");
        return name.length() > MAX_NAME ? name.substring(0, MAX_NAME) : name;
    }
    private static byte[] readLimited(File f, int limit) throws IOException {
        if (f.length() > limit) throw new IOException("Profildatei ist zu groß.");
        try (InputStream in = new FileInputStream(f); ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buf = new byte[4096]; int total = 0, n;
            while ((n = in.read(buf)) >= 0) {
                total += n; if (total > limit) throw new IOException("Profildatei ist zu groß.");
                out.write(buf, 0, n);
            }
            return out.toByteArray();
        }
    }
}
