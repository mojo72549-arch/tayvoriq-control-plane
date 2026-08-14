from pathlib import Path
import hashlib

p = Path('android-test-app/app/src/main/java/com/tayvoriq/addonmanager/FileImportActivity.java')
text = p.read_text()


def minecraft_block(value: str) -> str:
    start = value.index('    private void openMinecraft(String currentFileName) {')
    end = value.index('    private Intent legacyViewIntent() {', start)
    return value[start:end]


minecraft_before = hashlib.sha256(minecraft_block(text).encode()).hexdigest()

direct_needle = '''        if (lower.endsWith(".zip")) {
            status.setText(fileName + "\\n\\nZIP wird lokal geprüft …");'''
direct_replacement = '''        if (lower.endsWith(".pack")) {
            status.setText("🚀 Spaceflight Simulator Mod erkannt\\n\\n" + fileName + " wird vorbereitet …");
            Intent sfsPack = new Intent(this, SfsPackImportActivity.class);
            sfsPack.setAction(Intent.ACTION_VIEW);
            sfsPack.setData(uri);
            sfsPack.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
            startActivity(sfsPack);
            finish();
            return;
        }

        if (lower.endsWith(".zip")) {
            status.setText(fileName + "\\n\\nZIP wird lokal geprüft …");'''
if direct_needle not in text:
    raise SystemExit('direct .pack insertion point not found')
text = text.replace(direct_needle, direct_replacement, 1)

decl_needle = '''        String blueprintParent = null;
        byte[] buffer = new byte[32 * 1024];'''
decl_replacement = '''        String blueprintParent = null;
        int sfsPackCount = 0;
        byte[] buffer = new byte[32 * 1024];'''
if decl_needle not in text:
    raise SystemExit('SFS pack counter declaration point not found')
text = text.replace(decl_needle, decl_replacement, 1)

scan_needle = '''                if (isMinecraftExtension(lower) && nestedMinecraft == null) {
                    nestedMinecraft = name;
                }
                if (lower.equals("manifest.json") || lower.endsWith("/manifest.json")) manifests++;'''
scan_replacement = '''                if (isMinecraftExtension(lower) && nestedMinecraft == null) {
                    nestedMinecraft = name;
                }
                if (lower.endsWith(".pack")) sfsPackCount++;
                if (lower.equals("manifest.json") || lower.endsWith("/manifest.json")) manifests++;'''
if scan_needle not in text:
    raise SystemExit('ZIP scan insertion point not found')
text = text.replace(scan_needle, scan_replacement, 1)

route_needle = '''            if (inspection.spaceflightBlueprintEntry != null) {
                SpaceflightPayload payload = extractSpaceflightPayload(source, inspection, originalName);
                runOnUiThread(() -> prepareSpaceflightBlueprintImport(payload));
                return;
            }

            runOnUiThread(() -> showUnknownZipOptions(source, originalName, inspection.entries, inspection.unpackedBytes));'''
route_replacement = '''            if (inspection.sfsPackCount > 0) {
                runOnUiThread(() -> {
                    status.setTextColor(TEXT);
                    status.setText("Spaceflight Custom Parts erkannt\\n\\n" + inspection.sfsPackCount + " .pack-Datei(en) werden vorbereitet …");
                    Intent sfsPack = new Intent(this, SfsPackImportActivity.class);
                    sfsPack.setAction(Intent.ACTION_VIEW);
                    sfsPack.setData(source);
                    sfsPack.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                    startActivity(sfsPack);
                    finish();
                });
                return;
            }

            if (inspection.spaceflightBlueprintEntry != null) {
                SpaceflightPayload payload = extractSpaceflightPayload(source, inspection, originalName);
                runOnUiThread(() -> prepareSpaceflightBlueprintImport(payload));
                return;
            }

            runOnUiThread(() -> showUnknownZipOptions(source, originalName, inspection.entries, inspection.unpackedBytes));'''
if route_needle not in text:
    raise SystemExit('ZIP SFS routing insertion point not found')
text = text.replace(route_needle, route_replacement, 1)

return_needle = 'return new ZipInspection(nestedMinecraft, manifests, levelDat, blueprint, version, entries, unpacked);'
if return_needle not in text:
    raise SystemExit('ZipInspection constructor not found')
text = text.replace(return_needle,
                    'return new ZipInspection(nestedMinecraft, manifests, levelDat, blueprint, version, sfsPackCount, entries, unpacked);', 1)

record_needle = '''            String spaceflightBlueprintEntry,
            String spaceflightVersionEntry,
            int entries,'''
record_replacement = '''            String spaceflightBlueprintEntry,
            String spaceflightVersionEntry,
            int sfsPackCount,
            int entries,'''
if record_needle not in text:
    raise SystemExit('ZipInspection record point not found')
text = text.replace(record_needle, record_replacement, 1)

minecraft_after = hashlib.sha256(minecraft_block(text).encode()).hexdigest()
if minecraft_before != minecraft_after:
    raise SystemExit('Minecraft openMinecraft block changed unexpectedly')

p.write_text(text)
print('Minecraft openMinecraft SHA-256 unchanged:', minecraft_after)
