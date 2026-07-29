package com.projectlumen.pilot.robust;

/** Central build switch for the optional parental protection feature. */
final class ParentalFeature {
    private static volatile Boolean testOverride;

    private ParentalFeature() { }

    static boolean enabled() {
        Boolean override = testOverride;
        return override != null ? override : BuildConfig.PARENTAL_PROTECTION_ENABLED;
    }

    static void setEnabledForTests(Boolean enabled) {
        testOverride = enabled;
    }
}
