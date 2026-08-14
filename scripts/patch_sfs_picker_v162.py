from pathlib import Path

java = Path('android-test-app/app/src/main/java/com/tayvoriq/addonmanager/FileImportActivity.java')
text = java.read_text()
old = '''    private void openSpaceflightFolderPicker() {
        Intent picker = new Intent(Intent.ACTION_OPEN_DOCUMENT_TREE);
        picker.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION
                | Intent.FLAG_GRANT_WRITE_URI_PERMISSION
                | Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION
                | Intent.FLAG_GRANT_PREFIX_URI_PERMISSION);
        startActivityForResult(picker, PICK_SPACEFLIGHT_TARGET_FOLDER);
    }
'''
new = '''    private void openSpaceflightFolderPicker() {
        Intent picker = new Intent(Intent.ACTION_OPEN_DOCUMENT_TREE);
        picker.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION
                | Intent.FLAG_GRANT_WRITE_URI_PERMISSION
                | Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION
                | Intent.FLAG_GRANT_PREFIX_URI_PERMISSION);

        String documentId = pendingSpaceflight != null
                ? "primary:Android/media/com.StefMorojna.SpaceflightSimulator/files/Saving/Blueprints"
                : "primary:Android/media/com.StefMorojna.SpaceflightSimulator";
        try {
            Uri initialUri = android.provider.DocumentsContract.buildDocumentUri(
                    "com.android.externalstorage.documents", documentId);
            picker.putExtra("android.provider.extra.INITIAL_URI", initialUri);
        } catch (RuntimeException ignored) {
            // Some vendor file pickers may ignore the initial location.
        }
        startActivityForResult(picker, PICK_SPACEFLIGHT_TARGET_FOLDER);
    }
'''
if old not in text:
    raise SystemExit('openSpaceflightFolderPicker block not found')
java.write_text(text.replace(old, new))

gradle = Path('android-test-app/app/build.gradle.kts')
g = gradle.read_text()
g = g.replace('versionCode = 9', 'versionCode = 10')
g = g.replace('versionName = "1.6.1-universal-import"', 'versionName = "1.6.2-universal-import"')
gradle.write_text(g)
