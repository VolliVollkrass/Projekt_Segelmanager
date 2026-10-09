# Nach dem Abschluss bleibt das Boot-Dashboard offen — dort liegt die
# Bootskasse, und abgerechnet wird oft erst nach dem Törn.
BOOT_DASHBOARD_STATUS = ("ZUTEILUNG_FIXIERT", "ABGESCHLOSSEN")


def is_boot_access_allowed(teilnahme):
    return (
        teilnahme.status == "bestaetigt"
        and teilnahme.boot is not None
        and teilnahme.toern.status in BOOT_DASHBOARD_STATUS
    )
