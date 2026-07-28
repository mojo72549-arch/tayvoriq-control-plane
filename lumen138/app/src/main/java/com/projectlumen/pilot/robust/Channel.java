package com.projectlumen.pilot.robust;

/** Immutable catalog entry with precomputed language and safety metadata. */
final class Channel {
    enum Type { LIVE, MOVIE, SERIES }

    final String id;
    final String name;
    final String group;
    final String url;
    final String logo;
    final Type type;
    final MediaLanguage.Code language;
    final byte automaticAdultClass;
    final byte adultClass;
    final boolean adult;
    final int policyRevision;

    Channel(String id, String name, String group, String url, Type type) {
        this(id, name, group, url, "", type);
    }

    Channel(String id, String name, String group, String url, String logo, Type type) {
        this(id, name, group, url, logo, type, null, AdultContentPolicy.CLASS_UNKNOWN);
    }

    Channel(String id, String name, String group, String url, String logo, Type type,
            MediaLanguage.Code cachedLanguage, byte cachedAdultClass) {
        this.id = id == null ? "" : id;
        this.name = name == null || name.isBlank() ? "Unbenannter Eintrag" : name.trim();
        this.group = group == null || group.isBlank() ? "Weitere" : group.trim();
        this.url = url == null ? "" : url.trim();
        this.logo = logo == null ? "" : logo.trim();
        this.type = type == null ? Type.LIVE : type;
        this.language = cachedLanguage == null || cachedLanguage == MediaLanguage.Code.ALL
                ? MediaLanguage.detectRaw(this.group, this.name)
                : cachedLanguage;
        this.automaticAdultClass = cachedAdultClass == AdultContentPolicy.CLASS_UNKNOWN
                ? AdultContentPolicy.classifyRaw(this.group, this.name, this.url)
                : cachedAdultClass;
        this.adultClass = AdultGroupPolicy.resolve(this.group, this.automaticAdultClass);
        this.adult = this.adultClass != AdultContentPolicy.CLASS_SAFE;
        this.policyRevision = AdultGroupPolicy.revision();
    }
}