package com.projectlumen.pilot.robust;

final class Channel {
    enum Type { LIVE, MOVIE, SERIES }
    final String id;
    final String name;
    final String group;
    final String url;
    final String logo;
    final Type type;

    Channel(String id, String name, String group, String url, Type type) {
        this(id, name, group, url, "", type);
    }

    Channel(String id, String name, String group, String url, String logo, Type type) {
        this.id = id == null ? "" : id;
        this.name = name == null || name.isBlank() ? "Unbenannter Eintrag" : name.trim();
        this.group = group == null || group.isBlank() ? "Weitere" : group.trim();
        this.url = url == null ? "" : url.trim();
        this.logo = logo == null ? "" : logo.trim();
        this.type = type == null ? Type.LIVE : type;
    }
}
