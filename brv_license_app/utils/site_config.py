import json
import os
from pathlib import Path

import frappe

from .logging import license_logger


LICENSE_DEFAULTS = {
    "lmfwc_base_url": "https://brvsoftware.com.tr",
    "lmfwc_consumer_key": "ck_1ca7afb874e5abc162e37b6bb9382dc1fc70a3bd",
    "lmfwc_consumer_secret": "cs_79f1877b138b0d09d2e0e0a0d3549c8329891b83",
    "mute_emails": 0,
    "server_script_enabled": 1,
}


def _sites_root() -> Path:
    """Return bench 'sites' directory for current process."""
    # frappe.get_site_path() → /.../sites/<sitename>[/subdir]
    site_path = Path(frappe.get_site_path())
    return site_path.parent


def ensure_license_site_config() -> None:
    """Ensure all *.com sites have BRV license defaults in site_config.json.

    Idempotent: existing keys are only updated if value differs.
    Intended to be run from hooks (after_migrate) or via:
        bench execute brv_license_app.utils.site_config.ensure_license_site_config
    """
    sites_dir = _sites_root()
    updated_any = False

    for site_dir in sites_dir.iterdir():
        if not site_dir.is_dir():
            continue
        if not site_dir.name.endswith(".com"):
            continue

        cfg_path = site_dir / "site_config.json"
        if not cfg_path.exists():
            continue

        try:
            raw = cfg_path.read_text(encoding="utf-8")
            data = json.loads(raw or "{}")
        except Exception:
            license_logger.error("Failed to read/parse %s", cfg_path)
            continue

        changed = False
        for key, value in LICENSE_DEFAULTS.items():
            if data.get(key) != value:
                data[key] = value
                changed = True

        if not changed:
            continue

        tmp_path = cfg_path.with_suffix(".json.tmp")
        try:
            tmp_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            os.replace(tmp_path, cfg_path)
            updated_any = True
            license_logger.info("Updated site_config.json for site %s", site_dir.name)
        except Exception:
            license_logger.exception("Failed to update %s", cfg_path)
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except Exception:
                pass

    if not updated_any:
        license_logger.debug("No site_config.json changes needed for *.com sites")

