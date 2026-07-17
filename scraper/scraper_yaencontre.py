import json, re, base64, time, random, os, sys
from datetime import date
from urllib.parse import urljoin

from curl_cffi import requests as curl_requests

BASE_URL = "https://www.yaencontre.com"
MEDIA_URL = "https://media.yaencontre.com/img/photo/"
DATASET_FILE = os.path.join(os.path.dirname(__file__), "..", "propiedades.json")
FULL_DESCRIPTION = "--full" in sys.argv

SEARCH_URLS = [
    ("venta", "piso",      "FLAT",       "/venta/pisos/isla-la-palma"),
    ("venta", "casa",      "HOUSE",      "/venta/casas/isla-la-palma"),
    ("venta", "atico",     "PENTHOUSE",  "/venta/aticos/isla-la-palma"),
    ("venta", "estudio",   "STUDIO",     "/venta/estudios/isla-la-palma"),
    ("alquiler", "piso",   "FLAT",       "/alquiler/pisos/isla-la-palma"),
    ("alquiler", "casa",   "HOUSE",      "/alquiler/casas/isla-la-palma"),
    ("vacacional", "piso", "FLAT",       "/alquiler/vacacional/isla-la-palma"),
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

TIPO_MAP = {
    "FLAT": "piso", "HOUSE": "casa", "PENTHOUSE": "atico",
    "STUDIO": "estudio", "APARTMENT": "apartamento", "DUPLEX": "piso",
    "VILLA": "chalet", "RURAL": "casa", "CHALET": "chalet",
}

FEATURE_MAP = {
    "piscina": "piscina",
    "garaje": "garaje", "parking": "garaje",
    "terraza": "terraza", "balcon": "terraza", "porche": "terraza",
    "ascensor": "ascensor", "elevador": "ascensor",
    "vistas al mar": "vistas_mar",
    "reformado": "reformado", "rehabilitado": "reformado",
    "amueblado": "amueblado", "equipado": "amueblado",
    "trastero": "trastero",
    "jardin": "jardin",
}

MUNICIPIO_MAP = {
    "santa cruz de la palma": "Santa Cruz de La Palma",
    "los llanos de aridane": "Los Llanos de Aridane",
    "llanos de aridane (los)": "Los Llanos de Aridane",
    "el paso": "El Paso",
    "paso (el)": "El Paso",
    "tazacorte": "Tazacorte",
    "brena alta": "Breña Alta",
    "brena baja": "Breña Baja",
    "villa de mazo": "Villa de Mazo",
    "fuencaliente": "Fuencaliente",
    "fuencaliente de la palma": "Fuencaliente",
    "puntallana": "Puntallana",
    "tijarafe": "Tijarafe",
    "barlovento": "Barlovento",
    "garafia": "Garafía",
    "san andres y sauces": "San Andrés y Sauces",
    "puntagorda": "Puntagorda",
}


def log(msg):
    print(f"[yaencontre] {msg}")


def fetch(url):
    full_url = urljoin(BASE_URL, url)
    try:
        time.sleep(random.uniform(2.0, 4.0))
        resp = curl_requests.get(full_url, headers=HEADERS, timeout=30)
        if resp.status_code == 200:
            return resp.text
        elif resp.status_code == 429:
            log(f"  Rate limit, esperando 60s...")
            time.sleep(60)
            return fetch(url)
        else:
            log(f"  HTTP {resp.status_code} en {url}")
            # Retry once with fresh request
            time.sleep(10)
            resp2 = curl_requests.get(full_url, headers=HEADERS, timeout=30)
            if resp2.status_code == 200:
                return resp2.text
            return None
    except Exception as e:
        log(f"  Error en {url}: {e}")
        return None


def extract_initial_state(html):
    for pat in [
        r'window\.__INITIAL_STATE__\s*=\s*JSON\.parse\(\s*atob\(\s*"([^"]+)"\s*\)\s*\)',
        r'window\.__INITIAL_STATE__\s*=\s*JSON\.parse\(\s*atob\(\s*\'([^\']+)\'\s*\)\s*\)',
    ]:
        m = re.search(pat, html)
        if m:
            try:
                decoded = base64.b64decode(m.group(1)).decode('utf-8')
                return json.loads(decoded)
            except Exception as e:
                log(f"  Error decodificando state: {e}")
                continue
    if "ssr_initialState" in html:
        m = re.search(r'<script[^>]*id="ssr_initialState"[^>]*>\s*([A-Za-z0-9+/=]+)\s*</script>', html)
        if m:
            try:
                decoded = base64.b64decode(m.group(1)).decode('utf-8')
                return json.loads(decoded)
            except Exception:
                pass
    return None


def extract_properties_from_state(state, operacion_defecto, tipo_defecto):
    props = []
    results = state.get("results", {})
    current = results.get("currentPageItems", {})
    items_lookup = current.get("byId", {})
    sorted_ids = current.get("sortedItems", [])

    for pid in sorted_ids:
        entry = items_lookup.get(pid)
        if not entry:
            continue
        item = entry.get("item", entry)
        family = item.get("family", "")
        # Skip non-residential
        if family in ("LAND", "GARAGE", "COMMERCIAL", "OFFICE", "WAREHOUSE", "BUILDING", "STORAGE"):
            continue
        props.append((item, operacion_defecto, tipo_defecto))
    return props


def build_image_url(slug, width=380):
    if not slug:
        return None
    return f"{MEDIA_URL}w{width}/{slug}"


def map_property(item, operacion_defecto, tipo_defecto):
    family = item.get("family", "")
    tipo = TIPO_MAP.get(family, tipo_defecto)

    item_op = item.get("operation", "")
    if item_op == "RENT":
        operacion = "alquiler"
    elif item_op == "HOLIDAY_RENTAL":
        operacion = "vacacional"
    else:
        operacion = operacion_defecto

    desc = item.get("description", "") or ""

    images = item.get("images", [])
    imagen_principal = build_image_url(images[0]["slug"], 380) if images else None

    address = item.get("address", {})
    geo = address.get("geoLocation", {})
    lat = geo.get("lat")
    lon = geo.get("lon")

    owner = item.get("owner", {})
    commercial_id = owner.get("commercialId", 0)
    reference = item.get("reference", "")
    prop_id = f"ye-{reference}"

    characteristics = [c.strip().lower() for c in item.get("characteristics", [])]
    extras = {}
    for feat, field in FEATURE_MAP.items():
        extras[field] = any(feat in c for c in characteristics)

    zona_raw = item.get("locations", {}).get("municipality", "") or ""
    zona = MUNICIPIO_MAP.get(zona_raw.lower().strip(), "Otros")
    if zona == "Otros":
        zn = address.get("qualifiedName", "") or ""
        for k, v in MUNICIPIO_MAP.items():
            if k in zn.lower():
                zona = v
                break

    is_new = item.get("isNewConstruction", False)
    estado = "obra_nueva" if is_new else "segunda_mano"

    return {
        "id": prop_id,
        "titulo": (item.get("title") or "").strip(),
        "precio": item.get("price", 0),
        "precio_m2": item.get("squareMeterPrice"),
        "moneda": "EUR",
        "zona": zona,
        "tipo": tipo,
        "operacion": operacion,
        "dormitorios": item.get("rooms"),
        "banos": item.get("bathrooms"),
        "metros": item.get("area"),
        "metros_parcela": None,
        "piscina": extras.get("piscina", False),
        "garaje": extras.get("garaje", False),
        "terraza": extras.get("terraza", False),
        "ascensor": extras.get("ascensor", False),
        "vistas_mar": extras.get("vistas_mar", False),
        "reformado": extras.get("reformado", False),
        "amueblado": extras.get("amueblado", False),
        "trastero": extras.get("trastero", False),
        "jardin": extras.get("jardin", False),
        "etiquetas": item.get("characteristics", []),
        "estado": estado,
        "planta": None,
        "descripcion": desc,
        "fuente": (owner.get("name") or "").strip(),
        "fuente_id": commercial_id,
        "url": urljoin(BASE_URL, item.get("url", "")),
        "imagen_principal": imagen_principal,
        "imagenes": [build_image_url(img["slug"]) for img in images[:10]],
        "latitud": lat,
        "longitud": lon,
        "verificada": False,
        "activa": True,
        "fecha_actualizacion": date.today().isoformat(),
    }


def fetch_detail_description(prop_url):
    # prop_url is a full URL, extract path
    path = prop_url.replace(BASE_URL, "")
    html = fetch(path)
    if not html:
        return None
    state = extract_initial_state(html)
    if not state:
        return None
    detail = state.get("details", {})
    if detail.get("description"):
        desc = detail["description"]
        if not desc.endswith("..."):
            return desc
    return None


def deduplicate(properties):
    seen = set()
    unique = []
    for p in properties:
        key = p["id"]
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def merge_verified(existing_path, new_props):
    if not os.path.exists(existing_path):
        return new_props
    with open(existing_path, "r", encoding="utf-8") as f:
        existing = json.load(f)
    verified = [p for p in existing.get("propiedades", []) if p.get("verificada") is True]
    if verified:
        log(f"Manteniendo {len(verified)} propiedades verificadas")
    all_props = {p["id"]: p for p in new_props}
    for vp in verified:
        all_props[vp["id"]] = vp
    return list(all_props.values())


def scrape():
    all_raw = []
    seen_ids = set()

    for operacion, tipo_label, familia, path in SEARCH_URLS:
        page_num = 1
        num_pages = 1
        log(f"Scrapeando {operacion}/{tipo_label} ({path})...")

        while page_num <= num_pages:
            url = path if page_num == 1 else f"{path}/pag-{page_num}"
            html = fetch(url)
            if not html:
                log(f"  Fallo en página {page_num}, saltando")
                break

            state = extract_initial_state(html)
            if not state:
                log(f"  No se encontró __INITIAL_STATE__ en página {page_num}")
                idx = html.find("__INITIAL_STATE__")
                if idx >= 0:
                    log(f"  Fragmento: {html[idx:idx+150]}")
                break

            if page_num == 1:
                pag = state.get("pagination", {})
                num_pages = pag.get("numPages", 1)
                total = state.get("results", {}).get("totalItems", 0)
                log(f"  Total: {total}, páginas: {num_pages}")

            new_props = extract_properties_from_state(state, operacion, tipo_label)
            before = len(seen_ids)
            for item, op, tp in new_props:
                cid = item.get("owner", {}).get("commercialId", "")
                ref = item.get("reference", "")
                key = ref
                if key not in seen_ids:
                    seen_ids.add(key)
                    all_raw.append((item, op, tp))
            log(f"  Página {page_num}/{num_pages}: {len(new_props)} items ({len(seen_ids) - before} nuevos)")
            page_num += 1

        log(f"  Total acumulado: {len(seen_ids)}")

    log(f"\nTotal propiedades únicas: {len(all_raw)}")
    mapped = []
    for item, op, tp in all_raw:
        prop = map_property(item, op, tp)
        mapped.append(prop)

    if FULL_DESCRIPTION:
        log("\nObteniendo descripciones completas...")
        for i, prop in enumerate(mapped):
            if not prop["descripcion"] or prop["descripcion"].endswith("..."):
                desc = fetch_detail_description(prop["url"])
                if desc:
                    prop["descripcion"] = desc
                if (i + 1) % 20 == 0:
                    log(f"  Progreso: {i + 1}/{len(mapped)}")

    final = merge_verified(DATASET_FILE, mapped)
    final = deduplicate(final)

    zonas = sorted(set(p["zona"] for p in final if p["zona"]))
    tipos = sorted(set(p["tipo"] for p in final if p["tipo"]))

    dataset = {
        "meta": {
            "nombre": "Directorio Vivienda La Palma",
            "version": "3.0",
            "fecha_actualizacion": date.today().isoformat(),
            "fuente": "yaencontre.com",
            "zonas": zonas,
            "tipos": tipos,
            "total": len(final),
            "verificadas": sum(1 for p in final if p.get("verificada")),
        },
        "propiedades": final,
    }

    os.makedirs(os.path.dirname(DATASET_FILE), exist_ok=True)
    with open(DATASET_FILE, "w", encoding="utf-8") as f:
        json.dump(dataset, f, ensure_ascii=False, indent=2)

    log(f"\nCompletado: {len(final)} propiedades en {DATASET_FILE}")
    return dataset


if __name__ == "__main__":
    scrape()
