# Keep kotlinx.serialization-generated companion serializers.
-keepattributes *Annotation*
-keepattributes InnerClasses

-keep,includedescriptorclasses class com.bilalahmad.invertermonitor.**$$serializer { *; }
-keepclassmembers class com.bilalahmad.invertermonitor.** {
    *** Companion;
}
-keepclasseswithmembers class com.bilalahmad.invertermonitor.** {
    kotlinx.serialization.KSerializer serializer(...);
}

# OkHttp / Okio.
-dontwarn okhttp3.**
-dontwarn okio.**
