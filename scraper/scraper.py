"""
DEPRECATED: Este scraper de 20+ fuentes individuales ha sido reemplazado por
scraper_yaencontre.py, que obtiene datos estructurados de yaencontre.com
(108 agencias, 442+ propiedades) con bypass de DataDome via curl_cffi.
Mantenido solo como referencia histórica.
"""

import json
import re
import sys
import os
from datetime import date
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

FUENTES_FILE = os.path.join(os.path.dirname(__file__), "fuentes_scraper.json")
DATASET_FILE = os.path.join(os.path.dirname(__file__), "..", "propiedades.json")
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
PRECIO_MAXIMO = 220000
ZONAS_OBJETIVO = ["los llanos", "el paso", "tazacorte"]


def extraer_precio(texto):
    numeros = re.findall(r'[\d.]+', texto.replace('.', '').replace(',', '.'))
    for n in numeros:
        try:
            v = int(n.replace('.', ''))
            if 10000 < v < 10000000:
                return v
        except ValueError:
            continue
    return None


def extraer_dormitorios(texto):
    m = re.search(r'(\d+)\s*(?:dormitorio|hab|habitacion)', texto, re.IGNORECASE)
    return int(m.group(1)) if m else None


def extraer_banos(texto):
    m = re.search(r'(\d+)\s*(?:banos?|baños?|bano|baño)', texto, re.IGNORECASE)
    return int(m.group(1)) if m else None


def extraer_metros(texto):
    m = re.search(r'(\d+)\s*m²|(\d+)\s*m2|(\d+)\s*metros', texto, re.IGNORECASE)
    if m:
        return int(m.group(1) or m.group(2) or m.group(3))
    return None


def tiene_caracteristica(texto, palabras):
    return any(p in texto.lower() for p in palabras)


def detectar_tipo(texto):
    t = texto.lower()
    if any(p in t for p in ['obra nueva', 'nueva construccion', 'estreno']):
        return "obra_nueva"
    if 'apartamento' in t:
        return "apartamento"
    if any(p in t for p in ['adosada', 'adosado']):
        return "adosada"
    if any(p in t for p in ['chalet', 'villa']):
        return "chalet"
    if 'casa' in t:
        return "casa"
    if 'piso' in t:
        return "piso"
    if 'desarrollo' in t:
        return "desarrollo"
    return "casa"


def detectar_zona(texto):
    t = texto.lower()
    if 'tazacorte' in t:
        return "Tazacorte"
    if 'los llanos' in t or 'llanos' in t:
        return "Los Llanos de Aridane"
    if 'el paso' in t:
        return "El Paso"
    if 'santa cruz' in t:
        return "Santa Cruz de La Palma"
    if 'brena alta' in t:
        return "Breña Alta"
    if 'brena baja' in t or 'brena' in t:
        return "Breña Baja"
    return None


def extraer_caracteristicas(texto):
    t = texto.lower()
    return {
        "piscina": tiene_caracteristica(t, ["piscina", "pool", "swimming"]),
        "garaje": tiene_caracteristica(t, ["garaje", "garage", "parking", "aparcamiento", "plaza"]),
        "terraza": tiene_caracteristica(t, ["terraza", "balcon", "balcón", "patio"]),
        "ascensor": tiene_caracteristica(t, ["ascensor", "elevador", "lift"]),
        "vistas_mar": tiene_caracteristica(t, ["vistas al mar", "vista mar", "vistas mar", "sea view"]),
        "reformado": tiene_caracteristica(t, ["reformado", "renovado", "reforma", "reformada"]),
        "amueblado": tiene_caracteristica(t, ["amueblado", "amueblada", "mobiliario", "mueblado"]),
        "trastero": tiene_caracteristica(t, ["trastero", "almacen", "storage"]),
        "jardin": tiene_caracteristica(t, ["jardin", "jardín", "garden", "patio"]),
    }


def generar_id(nombre_fuente):
    prefijos = {
        "my home la palma": "MHLP",
        "kenjy home": "KEN",
        "marai inmobiliaria": "MRA",
        "ilp inmobiliaria": "ILP",
        "wellmann immobilien": "WLM",
        "pisos.com": "PIS",
        "mitula": "MIT",
        "nestoria": "NES",
        "trovit": "TRO",
        "milanuncios": "MIL",
        "yaencontre": "YAE",
        "palminvest": "PINV",
        "la palma 24": "LP24",
        "mi casa en la palma": "MCLP",
        "palmacasas": "PCAS",
        "idealista": "IDE",
        "fotocasa": "FOT",
    }
    base = "GEN"
    for k, v in prefijos.items():
        if k in nombre_fuente.lower():
            base = v
            break
    return f"{base}-{date.today().strftime('%Y%m%d')}-"


def scrape_requests(fuente):
    headers = {"User-Agent": USER_AGENT}
    try:
        resp = requests.get(fuente["url"], headers=headers, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"  [ERROR] {fuente['nombre']}: {e}")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    propiedades = []

    selector = fuente.get("selector_tarjeta")
    if not selector:
        print(f"  [SKIP] {fuente['nombre']}: sin selector_tarjeta")
        return []

    tarjetas = soup.select(selector)
    print(f"  [OK] {fuente['nombre']}: {len(tarjetas)} tarjetas encontradas")

    for tarjeta in tarjetas:
        try:
            titulo_el = tarjeta.select_one(fuente["selector_titulo"]) if fuente.get("selector_titulo") else None
            precio_el = tarjeta.select_one(fuente["selector_precio"]) if fuente.get("selector_precio") else None
            link_el = tarjeta.select_one(fuente["selector_link"]) if fuente.get("selector_link") else None
            desc_el = tarjeta.select_one(fuente["selector_descripcion"]) if fuente.get("selector_descripcion") else None

            titulo = titulo_el.get_text(strip=True) if titulo_el else ""
            precio_texto = precio_el.get_text(strip=True) if precio_el else ""
            url = urljoin(fuente["url"], link_el.get("href", "")) if link_el else ""
            descripcion = desc_el.get_text(strip=True) if desc_el else ""

            precio = extraer_precio(precio_texto)
            if not precio or precio > PRECIO_MAXIMO:
                continue

            texto_completo = f"{titulo} {descripcion}"
            zona = detectar_zona(texto_completo)
            if not zona or not any(z in zona.lower() for z in ZONAS_OBJETIVO):
                continue

            caracteristicas = extraer_caracteristicas(texto_completo)
            prop = {
                "id": generar_id(fuente["nombre"]) + str(abs(hash(url)) % 100000),
                "titulo": titulo,
                "precio": precio,
                "moneda": "EUR",
                "zona": zona,
                "tipo": detectar_tipo(texto_completo),
                "dormitorios": extraer_dormitorios(texto_completo),
                "banos": extraer_banos(texto_completo),
                "metros": extraer_metros(texto_completo),
                "metros_parcela": None,
                "piscina": caracteristicas["piscina"],
                "garaje": caracteristicas["garaje"],
                "terraza": caracteristicas["terraza"],
                "ascensor": caracteristicas["ascensor"],
                "vistas_mar": caracteristicas["vistas_mar"],
                "reformado": caracteristicas["reformado"],
                "amueblado": caracteristicas["amueblado"],
                "trastero": caracteristicas["trastero"],
                "jardin": caracteristicas["jardin"],
                "estado": "obra_nueva" if "obra_nueva" in texto_completo.lower() else "segunda_mano",
                "planta": None,
                "descripcion": descripcion if descripcion else titulo,
                "fuente": fuente["nombre"],
                "url": url,
                "verificada": True,
                "fecha_verificacion": str(date.today()),
                "activa": True,
                "fecha_actualizacion": str(date.today()),
            }
            propiedades.append(prop)
        except Exception as e:
            print(f"    [WARN] Error procesando tarjeta: {e}")
            continue

    return propiedades


def scrape_playwright(fuente):
    if sync_playwright is None:
        print(f"  [SKIP] {fuente['nombre']}: Playwright no instalado")
        return []

    propiedades = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=USER_AGENT)
            page.goto(fuente["url"], timeout=60000)
            page.wait_for_load_state("networkidle")

            selector = fuente.get("selector_tarjeta")
            if not selector:
                print(f"  [SKIP] {fuente['nombre']}: sin selector_tarjeta")
                browser.close()
                return []

            tarjetas = page.query_selector_all(selector)
            print(f"  [OK] {fuente['nombre']}: {len(tarjetas)} tarjetas encontradas (Playwright)")

            for tarjeta in tarjetas:
                try:
                    titulo = ""
                    if fuente.get("selector_titulo"):
                        el = tarjeta.query_selector(fuente["selector_titulo"])
                        if el:
                            titulo = el.inner_text().strip()

                    precio_texto = ""
                    if fuente.get("selector_precio"):
                        el = tarjeta.query_selector(fuente["selector_precio"])
                        if el:
                            precio_texto = el.inner_text().strip()

                    url = ""
                    if fuente.get("selector_link"):
                        el = tarjeta.query_selector(fuente["selector_link"])
                        if el:
                            url = urljoin(fuente["url"], el.get_attribute("href") or "")

                    descripcion = ""
                    if fuente.get("selector_descripcion"):
                        el = tarjeta.query_selector(fuente["selector_descripcion"])
                        if el:
                            descripcion = el.inner_text().strip()

                    precio = extraer_precio(precio_texto)
                    if not precio or precio > PRECIO_MAXIMO:
                        continue

                    texto_completo = f"{titulo} {descripcion}"
                    zona = detectar_zona(texto_completo)
                    if not zona or not any(z in zona.lower() for z in ZONAS_OBJETIVO):
                        continue

                    caracteristicas = extraer_caracteristicas(texto_completo)
                    prop = {
                        "id": generar_id(fuente["nombre"]) + str(abs(hash(url)) % 100000),
                        "titulo": titulo,
                        "precio": precio,
                        "moneda": "EUR",
                        "zona": zona,
                        "tipo": detectar_tipo(texto_completo),
                        "dormitorios": extraer_dormitorios(texto_completo),
                        "banos": extraer_banos(texto_completo),
                        "metros": extraer_metros(texto_completo),
                        "metros_parcela": None,
                        "piscina": caracteristicas["piscina"],
                        "garaje": caracteristicas["garaje"],
                        "terraza": caracteristicas["terraza"],
                        "ascensor": caracteristicas["ascensor"],
                        "vistas_mar": caracteristicas["vistas_mar"],
                        "reformado": caracteristicas["reformado"],
                        "amueblado": caracteristicas["amueblado"],
                        "trastero": caracteristicas["trastero"],
                        "jardin": caracteristicas["jardin"],
                        "estado": "obra_nueva" if "obra_nueva" in texto_completo.lower() else "segunda_mano",
                        "planta": None,
                        "descripcion": descripcion if descripcion else titulo,
                        "fuente": fuente["nombre"],
                        "url": url,
                        "verificada": True,
                        "fecha_verificacion": str(date.today()),
                        "activa": True,
                        "fecha_actualizacion": str(date.today()),
                    }
                    propiedades.append(prop)
                except Exception as e:
                    print(f"    [WARN] Error en tarjeta Playwright: {e}")
                    continue

            browser.close()
    except Exception as e:
        print(f"  [ERROR] {fuente['nombre']} (Playwright): {e}")

    return propiedades


def deduplicar(lista_nuevas, existentes):
    urls_existentes = {p.get("url") for p in existentes if p.get("url")}
    ids_existentes = {p["id"] for p in existentes}
    nuevas = []
    for p in lista_nuevas:
        if p.get("url") and p["url"] in urls_existentes:
            continue
        if p["id"] in ids_existentes:
            continue
        nuevas.append(p)
    return nuevas


def cargar_dataset():
    if not os.path.exists(DATASET_FILE):
        return {"propiedades": []}
    with open(DATASET_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def guardar_dataset(dataset):
    dataset["meta"]["fecha_actualizacion"] = str(date.today())
    dataset["total_verificadas"] = sum(
        1 for p in dataset["propiedades"] if p.get("verificada")
    )
    dataset["total"] = len(dataset["propiedades"])
    with open(DATASET_FILE, "w", encoding="utf-8") as f:
        json.dump(dataset, f, ensure_ascii=False, indent=2)
    print(f"\nDataset guardado: {dataset['total']} propiedades ({dataset['total_verificadas']} verificadas)")


def main():
    print("Scraper Viviendas La Palma")
    print("=" * 50)

    if not os.path.exists(FUENTES_FILE):
        print(f"ERROR: No se encuentra {FUENTES_FILE}")
        sys.exit(1)

    with open(FUENTES_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)

    dataset = cargar_dataset()
    existentes = dataset["propiedades"]
    todas_nuevas = []
    fuentes_activas = [f for f in config["fuentes"] if f.get("activo", False)]

    print(f"\nFuentes activas: {len(fuentes_activas)}")
    print(f"Propiedades existentes: {len(existentes)}")
    print()

    for fuente in fuentes_activas:
        print(f"Scrapeando: {fuente['nombre']}")
        print(f"  URL: {fuente['url']}")
        print(f"  Método: {fuente.get('metodo', 'requests')}")

        if fuente.get("metodo") == "playwright":
            props = scrape_playwright(fuente)
        else:
            props = scrape_requests(fuente)

        print(f"  Resultado: {len(props)} propiedades < {PRECIO_MAXIMO/1000}K en zona objetivo")
        todas_nuevas.extend(props)
        print()

    nuevas = deduplicar(todas_nuevas, existentes)
    print(f"\nNuevas propiedades encontradas: {len(nuevas)}")

    if nuevas:
        dataset["propiedades"].extend(nuevas)
        guardar_dataset(dataset)
    else:
        print("No hay propiedades nuevas que añadir.")


if __name__ == "__main__":
    main()
