from pathlib import Path

SOURCE = Path("app/src/main/java/com/projectlumen/pilot/robust/MainActivity.java")
MARKER = "swipeCategories=true"

text = SOURCE.read_text(encoding="utf-8")
if MARKER in text:
    print("Project Lumen 13.1.48 category rails already applied")
    raise SystemExit(0)


def replace_once(old: str, new: str, label: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    text = text.replace(old, new, 1)


replace_once(
    "    private final Map<String, Button> languageButtons = new LinkedHashMap<>();\n",
    "    private final Map<String, Button> languageButtons = new LinkedHashMap<>();\n"
    "    private final Map<String, Button> groupButtons = new LinkedHashMap<>();\n",
    "group button map",
)

replace_once(
    "    private Button groupButton;\n"
    "    private HorizontalScrollView languageScroll;\n"
    "    private LinearLayout languageRow;\n",
    "    private Button groupButton;\n"
    "    private HorizontalScrollView languageScroll;\n"
    "    private LinearLayout languageRow;\n"
    "    private HorizontalScrollView groupScroll;\n"
    "    private LinearLayout groupRow;\n",
    "category rail fields",
)

replace_once(
    '                "uiReady=true premiumShell=true providerLanguages=true swipeLanguages=true");',
    '                "uiReady=true premiumShell=true providerLanguages=true swipeLanguages=true swipeCategories=true");',
    "application diagnostics marker",
)

replace_once(
    "        groupButton = baseChoiceButton(\"Alle Gruppen\");\n"
    "        groupButton.setTextSize(tv() ? 14 : 12);\n"
    "        groupButton.setGravity(Gravity.CENTER_VERTICAL);\n"
    "        groupButton.setPadding(dp(13), 0, dp(13), 0);\n"
    "        groupButton.setEllipsize(TextUtils.TruncateAt.END);\n"
    "        groupButton.setOnClickListener(v -> showGroupChooser());\n"
    "        LinearLayout.LayoutParams groupParams = new LinearLayout.LayoutParams(\n"
    "                -1, dp(tv() ? 47 : 41));\n"
    "        groupParams.setMargins(0, 0, 0, dp(8));\n"
    "        root.addView(groupButton, groupParams);\n",
    "        groupScroll = new HorizontalScrollView(this);\n"
    "        groupScroll.setHorizontalScrollBarEnabled(false);\n"
    "        groupScroll.setFillViewport(false);\n"
    "        groupScroll.setOverScrollMode(View.OVER_SCROLL_NEVER);\n"
    "        groupRow = new LinearLayout(this);\n"
    "        groupRow.setOrientation(LinearLayout.HORIZONTAL);\n"
    "        groupRow.setGravity(Gravity.CENTER_VERTICAL);\n"
    "        groupScroll.addView(groupRow, new HorizontalScrollView.LayoutParams(-2, -1));\n"
    "        LinearLayout.LayoutParams groupParams = new LinearLayout.LayoutParams(\n"
    "                -1, dp(tv() ? 48 : 41));\n"
    "        groupParams.setMargins(0, 0, 0, dp(8));\n"
    "        root.addView(groupScroll, groupParams);\n"
    "        renderGroupButtons(availableGroups);\n",
    "replace group chooser button with swipe rail",
)

replace_once(
    "        renderLanguageButtons(availableLanguages);\n"
    "        updateSelectionStyles();\n",
    "        renderLanguageButtons(availableLanguages);\n"
    "        renderGroupButtons(availableGroups);\n"
    "        updateSelectionStyles();\n",
    "render empty category rail after import",
)

replace_once(
    "            selectedGroup = ProviderCatalog.ALL_GROUPS;\n"
    "            availableGroups = Collections.emptyList();\n"
    "            search.setText(\"\");\n"
    "            saveViewState();\n",
    "            selectedGroup = ProviderCatalog.ALL_GROUPS;\n"
    "            availableGroups = Collections.emptyList();\n"
    "            renderGroupButtons(availableGroups);\n"
    "            search.setText(\"\");\n"
    "            saveViewState();\n",
    "clear category rail when changing media type",
)

replace_once(
    "        selectedGroup = ProviderCatalog.ALL_GROUPS;\n"
    "        availableGroups = Collections.emptyList();\n"
    "        search.setText(\"\");\n"
    "        saveViewState();\n",
    "        selectedGroup = ProviderCatalog.ALL_GROUPS;\n"
    "        availableGroups = Collections.emptyList();\n"
    "        renderGroupButtons(availableGroups);\n"
    "        search.setText(\"\");\n"
    "        saveViewState();\n",
    "clear category rail when changing language",
)

insert_before_group_chooser = '''    private void renderGroupButtons(List<String> groups) {
        if (groupRow == null) return;
        groupRow.removeAllViews();
        groupButtons.clear();
        List<String> safe = groups == null ? Collections.emptyList() : groups;

        groupButton = categoryButton(allCategoryLabel(), ProviderCatalog.ALL_GROUPS, 0);
        int index = 1;
        for (String group : safe) {
            if (group == null || group.isBlank()) continue;
            categoryButton(group, group, index++);
        }

        if (safe.size() > 8) {
            Button searchButton = baseChoiceButton("Kategorien suchen");
            searchButton.setTextSize(tv() ? 13 : 11);
            searchButton.setMinWidth(dp(tv() ? 154 : 112));
            searchButton.setPadding(dp(tv() ? 14 : 11), 0, dp(tv() ? 14 : 11), 0);
            searchButton.setContentDescription("Kategorien durchsuchen");
            searchButton.setOnClickListener(v -> showGroupChooser());
            LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                    -2, dp(tv() ? 46 : 39));
            params.setMargins(dp(6), 0, 0, 0);
            groupRow.addView(searchButton, params);
        }
        updateGroupStyles();
    }

    private Button categoryButton(String label, String value, int index) {
        Button button = baseChoiceButton(label);
        button.setTextSize(tv() ? 13 : 11);
        button.setMinWidth(dp(tv() ? 126 : 88));
        button.setMaxWidth(dp(tv() ? 300 : 220));
        button.setPadding(dp(tv() ? 14 : 11), 0, dp(tv() ? 14 : 11), 0);
        button.setEllipsize(TextUtils.TruncateAt.END);
        button.setContentDescription("Kategorie " + label);
        button.setOnClickListener(v -> selectGroup(value));
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                -2, dp(tv() ? 46 : 39));
        if (index > 0) params.setMargins(dp(6), 0, 0, 0);
        groupRow.addView(button, params);
        groupButtons.put(value == null ? ProviderCatalog.ALL_GROUPS : value, button);
        return button;
    }

    private void selectGroup(String group) {
        selectedGroup = group == null ? ProviderCatalog.ALL_GROUPS : group;
        if (search != null) search.setText("");
        saveViewState();
        updateSelectionStyles();
        filterNow();
        Button selected = groupButtons.get(selectedGroup);
        if (selected != null && groupScroll != null) {
            groupScroll.post(() -> groupScroll.smoothScrollTo(
                    Math.max(0, selected.getLeft() - dp(12)), 0));
        }
    }

    private String allCategoryLabel() {
        if (mode == Mode.MOVIES) return "Alle Filmkategorien";
        if (mode == Mode.SERIES) return "Alle Serienkategorien";
        return "Alle Sendergruppen";
    }

'''
replace_once(
    "    private void showGroupChooser() {\n",
    insert_before_group_chooser + "    private void showGroupChooser() {\n",
    "insert category rail behavior",
)

replace_once(
    '            Toast.makeText(this, "In diesem Bereich wurden keine Gruppen gefunden.",',
    '            Toast.makeText(this, "In diesem Bereich wurden keine Kategorien gefunden.",',
    "empty category message",
)
replace_once('        choices.add("Alle Gruppen");', '        choices.add(allCategoryLabel());', "all category chooser label")
replace_once('        EditText groupSearch = input("Gruppen durchsuchen", false);', '        EditText groupSearch = input("Kategorien durchsuchen", false);', "category chooser search")
replace_once('                .setTitle("Gruppe auswählen · " + groups.size())', '                .setTitle("Kategorie auswählen · " + groups.size())', "category chooser title")

replace_once(
    "        groupList.setOnItemClickListener((parent, view, position, id) -> {\n"
    "            String selected = groupAdapter.getItem(position);\n"
    "            selectedGroup = selected == null || selected.equals(\"Alle Gruppen\")\n"
    "                    ? ProviderCatalog.ALL_GROUPS : selected;\n"
    "            search.setText(\"\");\n"
    "            saveViewState();\n"
    "            updateSelectionStyles();\n"
    "            filterNow();\n"
    "            dialog.dismiss();\n"
    "        });\n",
    "        groupList.setOnItemClickListener((parent, view, position, id) -> {\n"
    "            String selected = groupAdapter.getItem(position);\n"
    "            selectGroup(selected == null || selected.equals(allCategoryLabel())\n"
    "                    ? ProviderCatalog.ALL_GROUPS : selected);\n"
    "            dialog.dismiss();\n"
    "        });\n",
    "category chooser selection",
)

replace_once(
    "        updateLanguageStyles();\n"
    "        styleChoice(groupButton, !selectedGroup.isEmpty(), ACCENT_BLUE);\n"
    "        updateGroupButton();\n",
    "        updateLanguageStyles();\n"
    "        updateGroupStyles();\n",
    "category rail selection styles",
)

replace_once(
    "    private void updateGroupButton() {\n"
    "        if (groupButton == null) return;\n"
    "        String title = selectedGroup.isEmpty() ? \"Alle Gruppen\" : selectedGroup;\n"
    "        groupButton.setText(title + \"  ·  \" + availableGroups.size() + \"  ▾\");\n"
    "        groupButton.setEnabled(!busy && !availableGroups.isEmpty());\n"
    "        groupButton.setAlpha(groupButton.isEnabled() ? 1f : 0.6f);\n"
    "    }\n",
    "    private void updateGroupStyles() {\n"
    "        Button allButton = groupButtons.get(ProviderCatalog.ALL_GROUPS);\n"
    "        if (allButton != null) {\n"
    "            allButton.setText(allCategoryLabel() + \" · \" + availableGroups.size());\n"
    "        }\n"
    "        for (Map.Entry<String, Button> entry : groupButtons.entrySet()) {\n"
    "            styleChoice(entry.getValue(), entry.getKey().equals(selectedGroup), ACCENT);\n"
    "            entry.getValue().setEnabled(!busy);\n"
    "            entry.getValue().setAlpha(busy ? 0.65f : 1f);\n"
    "        }\n"
    "    }\n",
    "replace dropdown updater with category rail updater",
)

replace_once(
    "                availableLanguages = snapshot.languages;\n"
    "                availableGroups = snapshot.groups;\n"
    "                renderLanguageButtons(snapshot.languages);\n"
    "                adapter.submit(snapshot.rows);\n",
    "                availableLanguages = snapshot.languages;\n"
    "                availableGroups = snapshot.groups;\n"
    "                renderLanguageButtons(snapshot.languages);\n"
    "                renderGroupButtons(snapshot.groups);\n"
    "                adapter.submit(snapshot.rows);\n",
    "render mode-specific category rail from snapshot",
)

replace_once(
    '                    String groupLabel = selectedGroup.isEmpty() ? "Alle Gruppen" : selectedGroup;',
    '                    String groupLabel = selectedGroup.isEmpty() ? allCategoryLabel() : selectedGroup;',
    "footer category label",
)

replace_once(
    "        updateLanguageStyles();\n"
    "        updateGroupButton();\n",
    "        updateLanguageStyles();\n"
    "        updateGroupStyles();\n",
    "busy category rail state",
)

replace_once(
    '        search.setHint("Sender, Film, Serie oder Gruppe suchen");',
    '        search.setHint("Sender, Film, Serie oder Kategorie suchen");',
    "search hint",
)

SOURCE.write_text(text, encoding="utf-8")
print("Applied Project Lumen 13.1.48 dynamic media category rails")
