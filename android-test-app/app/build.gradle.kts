plugins {
    id("com.android.application")
}

android {
    namespace = "com.tayvoriq.addonmanager"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.tayvoriq.addonmanager.test"
        minSdk = 26
        targetSdk = 36
        versionCode = 4
        versionName = "1.3-neon-test"
        manifestPlaceholders["admobAppId"] = "ca-app-pub-3940256099942544~3347511713"
    }

    buildTypes {
        debug {
            applicationIdSuffix = ".debug"
            versionNameSuffix = "-debug"
        }
        release {
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

dependencies {
    implementation("com.google.android.gms:play-services-ads:25.4.0")
}
