# FILE: brv_license_app/hooks.py
app_name = "brv_license_app"
app_title = "BRV License App"
app_publisher = "BRV Softare"
app_description = "License client"
app_email = "info@brvsoftware.com.tr"

app_license = "mit"



# Her istek başında lisans kısıtını uygla
auth_hooks = ["brv_license_app.overrides.enforce_request"]

# 6 saatte bir otomatik doğrulama - 48 saat grace period içinde 8 deneme şansı
scheduler_events = {
    "cron": {
        "0 */6 * * *": [
            "brv_license_app.brv_license_app.doctype.license_settings.license_settings.scheduled_auto_validate"
        ]
    }
}

# Desk'e global JS enjekte et
app_include_js = [
    "/assets/brv_license_app/js/license_guard.js",
    "/assets/brv_license_app/js/license_banner.js",
    "/assets/brv_license_app/js/about_override.js",
]

# Oturum açılışında istemciye lisans özetini gönder
boot_session = "brv_license_app.overrides.boot_session"

# Her migrate sonrasında site_config.json içine lisans/e-posta varsayılanlarını uygula
after_migrate = "brv_license_app.utils.site_config.ensure_license_site_config"

# İzin/allowlist — License Settings'in çalışabilmesi için gerekli standart endpointler
license_allowlist_paths = [
    "/app",  # Desk shell (SPA index) – gerekli
    "/login",
    "/api/method/login",
    "/api/method/logout",
    "/api/method/ping",
    "/api/method/frappe.boot.get_bootinfo",
    "/api/method/frappe.desk.desk.get_desk_sidebar",
    "/api/method/frappe.desk.desktop.get_workspace_sidebar_items",
    "/api/method/frappe.desk.form.meta.get_meta",
    "/api/method/frappe.client.get",
    "/api/method/frappe.client.get_value",
    "/api/method/frappe.desk.search.search_link",
    # Desk default fetches (read-only) needed for shell to render
    "/api/method/frappe.desk.doctype.event.event.",
    "/api/method/frappe.desk.doctype.notification_log.notification_log.",
    "/assets/",
    "/app/license-settings",  # License Settings sayfası
    "/api/method/brv_license_app.api.license.healthz",
    
    # AI telemetry/logging (non-critical; allow even under lock so troubleshooting works)
    "/api/method/brv_license_app.api.ingest.log_ai_interaction",

    # Form yükleme/kaydetme
    "/api/method/frappe.desk.form.load.getdoc",
    "/api/method/frappe.desk.form.save.savedocs",

    # Doc method çağrıları (ör. activate/validate/deactivate)
    "/api/method/run_doc_method",
    
    # License Settings API'leri
    "/api/method/brv_license_app.brv_license_app.doctype.license_settings.license_settings",
]
