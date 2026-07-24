package com.projectlumen.publicpreview;

import android.content.Context;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.security.GeneralSecurityException;
import java.security.Key;
import java.security.KeyStore;
import java.security.SecureRandom;

import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

/** Small AES-GCM file helper backed by Android Keystore. */
final class SecureBlobStore {
    private static final int MAGIC = 0x4C534246;
    private static final SecureRandom RANDOM = new SecureRandom();

    private SecureBlobStore() {}

    static byte[] read(Context context, File file, String keyAlias, int maxBytes) throws IOException {
        if (!file.isFile()) return new byte[0];
        if (file.length() > maxBytes) throw new IOException("Sicherer Speicher ist zu groß.");
        try (FileInputStream input = new FileInputStream(file);
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[8192];
            int total = 0;
            int read;
            while ((read = input.read(buffer)) >= 0) {
                total += read;
                if (total > maxBytes) throw new IOException("Sicherer Speicher ist zu groß.");
                output.write(buffer, 0, read);
            }
            DataInputStream encoded = new DataInputStream(new ByteArrayInputStream(output.toByteArray()));
            if (encoded.readInt() != MAGIC) throw new IOException("Ungültiger sicherer Speicher.");
            int ivLength = encoded.readUnsignedByte();
            if (ivLength < 12 || ivLength > 32) throw new IOException("Ungültiger Verschlüsselungsheader.");
            byte[] iv = new byte[ivLength];
            encoded.readFully(iv);
            byte[] cipherText = new byte[encoded.available()];
            encoded.readFully(cipherText);
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE, key(keyAlias), new GCMParameterSpec(128, iv));
            return cipher.doFinal(cipherText);
        } catch (GeneralSecurityException failure) {
            throw new IOException("Sicherer Speicher konnte nicht entschlüsselt werden.", failure);
        }
    }

    static void write(Context context, File file, String keyAlias, byte[] plain) throws IOException {
        try {
            byte[] iv = new byte[12];
            RANDOM.nextBytes(iv);
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.ENCRYPT_MODE, key(keyAlias), new GCMParameterSpec(128, iv));
            byte[] cipherText = cipher.doFinal(plain == null ? new byte[0] : plain);
            File parent = file.getParentFile();
            if (parent != null && !parent.exists() && !parent.mkdirs()) {
                throw new IOException("Speicherordner konnte nicht erstellt werden.");
            }
            File temp = new File(parent, file.getName() + ".tmp");
            try (FileOutputStream output = new FileOutputStream(temp);
                 DataOutputStream encoded = new DataOutputStream(output)) {
                encoded.writeInt(MAGIC);
                encoded.writeByte(iv.length);
                encoded.write(iv);
                encoded.write(cipherText);
                encoded.flush();
                output.getFD().sync();
            }
            if (file.exists() && !file.delete()) throw new IOException("Alter sicherer Speicher konnte nicht ersetzt werden.");
            if (!temp.renameTo(file)) throw new IOException("Sicherer Speicher konnte nicht übernommen werden.");
        } catch (GeneralSecurityException failure) {
            throw new IOException("Sicherer Speicher konnte nicht verschlüsselt werden.", failure);
        }
    }

    private static SecretKey key(String alias) throws GeneralSecurityException, IOException {
        KeyStore store = KeyStore.getInstance("AndroidKeyStore");
        try { store.load(null); }
        catch (Exception failure) { throw new GeneralSecurityException("Android Keystore nicht verfügbar", failure); }
        Key existing = store.getKey(alias, null);
        if (existing instanceof SecretKey) return (SecretKey) existing;
        KeyGenerator generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
        generator.init(new KeyGenParameterSpec.Builder(alias,
                KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setRandomizedEncryptionRequired(true)
                .setKeySize(256)
                .build());
        return generator.generateKey();
    }
}
