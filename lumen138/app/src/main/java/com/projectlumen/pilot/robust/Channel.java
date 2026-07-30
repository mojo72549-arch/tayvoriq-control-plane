package com.projectlumen.pilot.robust;

import java.util.Objects;

final class Channel {
    enum Type { LIVE, MOVIE, SERIES }

    final String id;
    final String name;
    final String group;
    final String url;
    final String logoUrl;
    final Type type;

    Channel(String id, String name, String group, String url, Type type) {
        this(id, name, group, url, "", type);
    }

    Channel(String id, String name, String group, String url, String logoUrl, Type type) {
        this.id = id == null ? "" : id;
        this.name = name == null || name.isBlank() ? "Unbenannter Inhalt" : name.trim();
        this.group = group == null || group.isBlank() ? "Weitere" : group.trim();
        this.url = url == null ? "" : url.trim();
        this.logoUrl = logoUrl == null ? "" : logoUrl.trim();
        this.type = type == null ? Type.LIVE : type;
    }

    @Override public boolean equals(Object other) {
        return other instanceof Channel && id.equals(((Channel) other).id);
    }

    @Override public int hashCode() { return Objects.hash(id); }
}
