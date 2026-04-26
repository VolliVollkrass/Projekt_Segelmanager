def is_boot_access_allowed(teilnahme):
    return (
        teilnahme.status == "bestaetigt"
        and teilnahme.boot is not None
        and teilnahme.toern.status == "ZUTEILUNG_FIXIERT"
    )