import cups

from ocfweb.caching import cache

@cache(ttl=60)
def get_printers():
    try:
        conn = cups.Connection(host='printhost')
        return conn.getPrinters()
    except Exception:
        return {}
