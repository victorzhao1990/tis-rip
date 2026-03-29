#!/usr/bin/env python3
import argparse
import base64
import json
from selenium import webdriver
import time
import os.path
import xml.etree.ElementTree as ET
import shutil
import subprocess
from bs4 import BeautifulSoup
import os
import re
import sys
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait


def mkfilename(s):
    fn = ""
    for x in s:
        if x.isalnum() or x == " ":
            fn += x
        else:
            fn += "_"
    return fn


def cache_doc_dir(cache_root, doc_id):
    return os.path.join(cache_root, doc_id)


def cache_html_dir(cache_root, doc_id):
    return os.path.join(cache_doc_dir(cache_root, doc_id), "html")


def cache_toc_path(cache_root, doc_id):
    return os.path.join(cache_doc_dir(cache_root, doc_id), "toc.xml")


def cache_selection_path(cache_root, doc_id):
    return os.path.join(cache_doc_dir(cache_root, doc_id), "selection.json")


def cache_html_path(cache_root, doc_id, href):
    return os.path.join(cache_html_dir(cache_root, doc_id), os.path.basename(href))


def cache_download_dir(cache_root):
    return os.path.join(cache_root, "download")


def cache_ewd_system_dir(cache_root, doc_id, system_name):
    return os.path.join(cache_doc_dir(cache_root, doc_id), system_name)


def cache_ewd_index_path(cache_root, doc_id, system_name):
    return os.path.join(cache_ewd_system_dir(cache_root, doc_id, system_name), "index.xml")


def output_doc_dir(output_root, doc_id):
    return os.path.join(output_root, doc_id)


def selection_folder_name(selection):
    parts = []
    for key, label in (("models", "models"), ("engines", "engines"), ("years", "years")):
        values = selection.get(key, []) if selection else []
        if values:
            value_part = "+".join(mkfilename(v).strip() or "Untitled" for v in values)
        else:
            value_part = "all"
        parts.append(label + "_" + value_part)
    return "__".join(parts)


def output_selection_dir(output_root, doc_id, selection):
    return os.path.join(output_doc_dir(output_root, doc_id), selection_folder_name(selection))


def output_manual_root(output_root, doc_id, artifact):
    return os.path.join(output_doc_dir(output_root, doc_id), artifact)


def output_ewd_system_dir(output_root, doc_id, system_name):
    return os.path.join(output_doc_dir(output_root, doc_id), system_name)


def fix_links(fn):
    modified = False
    doc = open(fn, 'r').read()
    soup = BeautifulSoup(doc, 'lxml')
    for link in soup.find_all("a"):
        href = link.get('href')
        if href is None:
            continue
        
        if '?' in href:
            href = href.split('?')[0]
        
        if not href.startswith('/t3Portal/document'):
            continue
        
        new_path = os.path.basename(href)
        if href != new_path:
            link['href'] = new_path
            modified = True
    
    if modified:
        print("Writing ", fn)
        with open(fn, 'w') as fh:
            fh.write(soup.prettify())


def get_xml_viewer_source(driver, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        assert_not_login_page(driver, "fetching XML")
        els = driver.find_elements(By.ID, "webkit-xml-viewer-source-xml")
        if els:
            return els[0].get_attribute("innerHTML")
        time.sleep(0.2)
    raise TimeoutException("Timed out waiting for XML viewer source")


def page_requires_login(driver):
    current_url = driver.current_url.lower()
    if "login" in current_url or "signin" in current_url:
        return True

    password_fields = driver.find_elements(By.CSS_SELECTOR, "input[type='password']")
    if password_fields:
        return True

    page_text = driver.page_source.lower()
    if "please login" in page_text or "sign in" in page_text:
        return True

    return False


def assert_not_login_page(driver, context):
    if page_requires_login(driver):
        raise RuntimeError("Toyota TIS login is required while " + context)


def page_has_http_error(driver):
    current_url = driver.current_url.lower()
    if current_url.startswith("chrome-error://"):
        return "browser error page"

    title = (driver.title or "").strip().lower()
    body_text = (driver.execute_script("return document.body ? document.body.innerText : '';") or "").strip().lower()

    patterns = [
        "403 forbidden",
        "404 not found",
        "http error 403",
        "http error 404",
        "error 403",
        "error 404",
    ]

    for pattern in patterns:
        if pattern in title or pattern in body_text:
            return pattern

    return None


def assert_not_http_error_page(driver, context):
    error_hint = page_has_http_error(driver)
    if error_hint:
        raise RuntimeError("Received " + error_hint + " while " + context)


def fetch_xml_document(driver, url):
    driver.get(url)
    assert_not_http_error_page(driver, "fetching XML from " + url)
    xml_src = get_xml_viewer_source(driver)
    if not xml_src or not xml_src.strip():
        raise RuntimeError("Received empty XML from " + url)
    return xml_src


def load_manual_page(driver, url):
    driver.get(url)
    assert_not_login_page(driver, "loading " + url)
    assert_not_http_error_page(driver, "loading " + url)
    page_source = driver.page_source
    if not page_source or not page_source.strip():
        raise RuntimeError("Received empty page from " + url)
    return page_source


def fetch_pdf_via_print(driver, pdf_url, pdf_path):
    driver.get(pdf_url)
    assert_not_login_page(driver, "rendering PDF " + pdf_url)
    assert_not_http_error_page(driver, "rendering PDF " + pdf_url)
    time.sleep(2)
    pdf_data = driver.execute_cdp_cmd(
        "Page.printToPDF",
        {
            "printBackground": True,
            "displayHeaderFooter": False,
        },
    )
    os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
    with open(pdf_path, 'wb') as fh:
        fh.write(base64.b64decode(pdf_data['data']))


def inject_and_save_html(driver, dest_path):
    src = None
    try:
        src = driver.execute_script(open("injected.js", "r").read())
    except Exception:
        time.sleep(1)
        src = driver.execute_script(open("injected.js", "r").read())

    if not src or not src.strip():
        raise RuntimeError("Injected HTML was empty for " + dest_path)

    with open(dest_path, 'w') as fh:
        fh.write(src)

    fix_links(dest_path)


def wait_for_download(download_dir, filename, timeout=30):
    temp_dl_path = os.path.join(download_dir, filename + ".crdownload")
    dl_path = os.path.join(download_dir, filename)
    deadline = time.time() + timeout

    while time.time() < deadline:
        if os.path.exists(dl_path) and not os.path.exists(temp_dl_path):
            return dl_path
        time.sleep(0.2)

    if os.path.exists(dl_path):
        return dl_path
    return None


def parse_xml_file(path):
    try:
        return ET.parse(path)
    except ET.ParseError as exc:
        raise RuntimeError("Failed to parse XML file " + path + ": " + str(exc)) from exc


def extract_models_from_tocdata(tocdata):
    return [m.findtext("tocmodelname", "").strip() for m in tocdata.findall("./tocmodel") if m.findtext("tocmodelname", "").strip()]


def extract_engines_from_tocdata(tocdata):
    engines = []
    for tocmodel in tocdata.findall("./tocmodel"):
        text = (tocmodel.findtext("tocengine") or "").strip()
        if not text:
            continue
        for engine in [x.strip() for x in text.split(",") if x.strip()]:
            if engine not in engines:
                engines.append(engine)
    return engines


def extract_model_engine_pairs_from_tocdata(tocdata):
    pairs = []
    for tocmodel in tocdata.findall("./tocmodel"):
        model = (tocmodel.findtext("tocmodelname") or "").strip()
        engine_text = (tocmodel.findtext("tocengine") or "").strip()
        if not model:
            continue
        engines = [x.strip() for x in engine_text.split(",") if x.strip()]
        if not engines:
            pairs.append((model, ""))
            continue
        for engine in engines:
            pair = (model, engine)
            if pair not in pairs:
                pairs.append(pair)
    return pairs


def extract_years_from_tocdata(tocdata):
    years = []
    for key in ("fromyear", "toyear"):
        value = (tocdata.attrib.get(key) or "").strip()
        if value.isdigit() and value not in years:
            years.append(value)
    return years


def normalize_string_filters(values):
    return {m.strip().lower() for m in (values or []) if m and m.strip()}


def normalize_year_filters(values):
    return {str(v).strip() for v in (values or []) if str(v).strip().isdigit()}


def normalize_filter_spec(filter_spec=None):
    filter_spec = filter_spec or {}
    return {
        "models": normalize_string_filters(filter_spec.get("models")),
        "engines": normalize_string_filters(filter_spec.get("engines")),
        "years": normalize_year_filters(filter_spec.get("years")),
    }


def dedupe_preserve_order(values):
    deduped = []
    seen = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped


def item_metadata(item, sibling_index=None, siblings=None, inherited=None):
    inherited = inherited or {}
    models = []
    engines = []
    years = []
    model_engine_pairs = []
    tocdata_nodes = list(item.findall("./tocdata"))

    if not tocdata_nodes and siblings is not None and sibling_index is not None:
        if sibling_index + 1 < len(siblings) and siblings[sibling_index + 1].tag == "tocdata":
            tocdata_nodes.append(siblings[sibling_index + 1])
        elif sibling_index > 0 and siblings[sibling_index - 1].tag == "tocdata":
            tocdata_nodes.append(siblings[sibling_index - 1])

    for tocdata in tocdata_nodes:
        models.extend(extract_models_from_tocdata(tocdata))
        engines.extend(extract_engines_from_tocdata(tocdata))
        years.extend(extract_years_from_tocdata(tocdata))
        model_engine_pairs.extend(extract_model_engine_pairs_from_tocdata(tocdata))

    if not models:
        models.extend(inherited.get("models", []))
    if not engines:
        engines.extend(inherited.get("engines", []))
    if not years:
        years.extend(inherited.get("years", []))
    if not model_engine_pairs:
        model_engine_pairs.extend(inherited.get("model_engine_pairs", []))

    return {
        "models": dedupe_preserve_order(models),
        "engines": dedupe_preserve_order(engines),
        "years": dedupe_preserve_order(years),
        "model_engine_pairs": dedupe_preserve_order(model_engine_pairs),
    }


def metadata_matches(metadata, filter_spec):
    filters = normalize_filter_spec(filter_spec)
    if filters["models"] and filters["engines"]:
        pairs = metadata.get("model_engine_pairs", [])
        if pairs:
            if not any(model.lower() in filters["models"] and engine.lower() in filters["engines"] for model, engine in pairs if model and engine):
                return False
        else:
            if not any(m.lower() in filters["models"] for m in metadata.get("models", [])):
                return False
            if not any(e.lower() in filters["engines"] for e in metadata.get("engines", [])):
                return False
    else:
        if filters["models"] and not any(m.lower() in filters["models"] for m in metadata.get("models", [])):
            return False
        if filters["engines"] and not any(e.lower() in filters["engines"] for e in metadata.get("engines", [])):
            return False
    if filters["years"] and not any(str(y) in filters["years"] for y in metadata.get("years", [])):
        return False
    return True


def available_models(root):
    models = []
    seen = set()
    for tocdata in root.findall(".//tocdata"):
        for model in extract_models_from_tocdata(tocdata):
            key = model.lower()
            if key not in seen:
                seen.add(key)
                models.append(model)
    return models


def available_values(manual_items, field):
    values = []
    seen = set()
    for _, _, metadata in manual_items:
        for value in metadata.get(field, []):
            key = value.lower() if isinstance(value, str) else value
            if key not in seen:
                seen.add(key)
                values.append(value)
    if field == "years":
        return sorted(values, key=lambda x: int(x))
    return values


def available_engines_for_models(manual_items, selected_models):
    if not selected_models:
        return available_values(manual_items, "engines")

    selected = normalize_string_filters(selected_models)
    engines = []
    seen = set()
    for _, _, metadata in manual_items:
        pairs = metadata.get("model_engine_pairs", [])
        if pairs:
            values = [engine for model, engine in pairs if model.lower() in selected and engine]
        else:
            values = metadata.get("engines", [])
        for engine in values:
            key = engine.lower()
            if key not in seen:
                seen.add(key)
                engines.append(engine)
    return engines


def load_saved_selection(cache_root, doc_id):
    path = cache_selection_path(cache_root, doc_id)
    if not os.path.exists(path):
        return None
    with open(path, "r") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise RuntimeError("Invalid saved selection format in " + path)

    result = {}
    for key in ("models", "engines", "years"):
        value = data.get(key, "all")
        if value == "all":
            result[key] = []
        elif isinstance(value, list):
            result[key] = [str(v) for v in value]
        else:
            raise RuntimeError("Invalid saved selection format in " + path)
    return result


def save_selection(cache_root, doc_id, selection):
    os.makedirs(cache_doc_dir(cache_root, doc_id), exist_ok=True)
    path = cache_selection_path(cache_root, doc_id)
    payload = {}
    for key in ("models", "engines", "years"):
        values = selection.get(key, [])
        payload[key] = "all" if not values else values
    with open(path, "w") as fh:
        json.dump(payload, fh, indent=2)


def prompt_multi_selection(doc_id, label, values, suggestion):
    if not values:
        return []
    print("Available", label, "for", doc_id + ":")
    for idx, value in enumerate(values, start=1):
        print(" ", str(idx) + ".", value)
    print(suggestion)
    print("  all")
    print("  a comma-separated list like 1,3")

    while True:
        choice = input("> ").strip()
        if choice.lower() == "all":
            return []

        picks = []
        valid = True
        for part in choice.split(","):
            part = part.strip()
            if not part:
                continue
            if not part.isdigit():
                valid = False
                break
            idx = int(part)
            if idx < 1 or idx > len(values):
                valid = False
                break
            picked = values[idx - 1]
            if picked not in picks:
                picks.append(picked)

        if valid and picks:
            return picks

        print("Invalid selection. Enter 'all' or one or more numbers separated by commas.")


def format_selection(selection):
    parts = []
    for key, label in (("models", "models"), ("engines", "engines"), ("years", "years")):
        values = selection.get(key, [])
        parts.append(label + "=" + ("all" if not values else ", ".join(values)))
    return "; ".join(parts)


def resolve_filter_selection(cache_root, doc_id, root, override_selection=None, force_prompt=False, has_override=False):
    override_selection = override_selection or {}
    normalized_override = {
        "models": override_selection.get("models", []) or [],
        "engines": override_selection.get("engines", []) or [],
        "years": [str(y) for y in (override_selection.get("years", []) or [])],
    }

    if has_override or any(normalized_override.values()):
        save_selection(cache_root, doc_id, normalized_override)
        return normalized_override

    saved = None if force_prompt else load_saved_selection(cache_root, doc_id)
    if saved is not None:
        print("Using saved selection for", doc_id + ":", format_selection(saved))
        return saved

    manual_items = list(iter_manual_items(root))
    models = available_values(manual_items, "models")
    selected_models = prompt_multi_selection(
        doc_id,
        "models",
        models,
        "Suggested: pick one or more models if you know your vehicle. Otherwise choose all.",
    )

    items_after_model = [item for item in manual_items if metadata_matches(item[2], {"models": selected_models})]
    engines = available_engines_for_models(items_after_model, selected_models)
    selected_engines = prompt_multi_selection(
        doc_id,
        "engines",
        engines,
        "Suggested: pick your engine for a more precise manual. Otherwise choose all.",
    )

    items_after_engine = [
        item for item in items_after_model
        if metadata_matches(item[2], {"models": selected_models, "engines": selected_engines})
    ]
    years = available_values(items_after_engine, "years")
    selected_years = prompt_multi_selection(
        doc_id,
        "years",
        years,
        "Suggested: pick your model year if you know it. Otherwise choose all.",
    )

    selection = {
        "models": selected_models,
        "engines": selected_engines,
        "years": selected_years,
    }
    save_selection(cache_root, doc_id, selection)
    return selection


def download_ewd(driver, ewd, output_dir, cache_root):
    SYSTEMS = ["system", "routing", "overall"]
    download_dir = cache_download_dir(cache_root)

    for s in SYSTEMS:
        fn = cache_ewd_index_path(cache_root, ewd, s)
        d = cache_ewd_system_dir(cache_root, ewd, s)
        os.makedirs(d, exist_ok=True)

        if os.path.exists(fn):
            continue

        url = "https://techinfo.toyota.com/t3Portal/external/en/ewdappu/" + ewd + "/ewd/contents/" + s + "/title.xml"
        print("Loading", url)
        print("Saving...")
        xml_src = fetch_xml_document(driver, url)
        with open(fn, 'w') as fh:
            fh.write(xml_src)

    for s in SYSTEMS:
        idx = cache_ewd_index_path(cache_root, ewd, s)
        print(idx)
        tree = parse_xml_file(idx)
        root = tree.getroot()
        for child in root:
            name = child.findall('name')[0].text
            fig = child.findall('fig')[0].text
            output_system_dir = output_ewd_system_dir(output_dir, ewd, s)
            os.makedirs(output_system_dir, exist_ok=True)
            fn = os.path.join(output_system_dir, mkfilename(fig + " " + name) + ".pdf")

            if os.path.exists(fn):
                continue

            print("Downloading ", name, "...")
            url = "https://techinfo.toyota.com/t3Portal/external/en/ewdappu/" + ewd + "/ewd/contents/" + s + "/pdf/" + fig + ".pdf"
            driver.get(url)
            dl_path = wait_for_download(download_dir, fig + ".pdf")
            if dl_path is None:
                print("Didn't download ", url, "!")
                continue
            shutil.move(dl_path, fn)
            print("Done ", name)

def toc_parse_items(cache_root, output_root, doc_id, items, ancestors=None, filter_spec=None, inherited_metadata=None):
    if ancestors is None:
        ancestors = []
    if len(items) == 0:
        return ""
    
    wrap = "<ul>"
    visible_children = 0

    for idx, i in enumerate(items):
        if i.tag != "item":
            continue
        wrap += "<li>"
        name = i.findall("name")[0].text
        breadcrumb = ancestors + [name]
        metadata = item_metadata(i, idx, items, inherited_metadata)
        child_markup = toc_parse_items(
            cache_root,
            output_root,
            doc_id,
            list(i),
            breadcrumb,
            filter_spec,
            metadata or inherited_metadata,
        )
        show_item = bool(child_markup)

        if "href" in i.attrib and i.attrib["href"] != "":
            show_item = metadata_matches(metadata, filter_spec)

        if not show_item:
            wrap = wrap[:-4]
            continue

        visible_children += 1
        wrap += name

        if "href" in i.attrib and i.attrib["href"] != "":
            html_path = html_output_path(output_root, breadcrumb, i.attrib["href"])
            pdf_path = pdf_output_path(output_root, breadcrumb, i.attrib["href"])

            if os.path.exists(html_path):
                html_href = os.path.relpath(html_path, output_root)
                wrap += " [<a href=\"" + html_href + "\">HTML</a>] "
            if os.path.exists(pdf_path):
                pdf_href = os.path.relpath(pdf_path, output_root)
                wrap += " [<a href=\"" + pdf_href + "\">PDF</a>] "

        wrap += child_markup
        wrap += "</li>"

    wrap += "</ul>"
    if visible_children == 0:
        return ""
    return wrap

def build_toc_index(cache_root, output_root, doc_id, filter_spec=None):
    if not os.path.exists(output_root):
        return False
    toc_path = cache_toc_path(cache_root, doc_id)
    if not os.path.exists(toc_path):
        print("toc.xml missing in ", toc_path)
        return False

    print("Building TOC index from ", toc_path, "...")
    
    tree = parse_xml_file(toc_path)
    root = tree.getroot()

    normalized_filters = normalize_filter_spec(filter_spec)
    body = toc_parse_items(cache_root, output_root, doc_id, root.findall("item"), filter_spec=normalized_filters)
    index_out = os.path.join(output_root, "index.html")
    with open(index_out, "w") as fh:
        fh.write("<!doctype html>\n")
        fh.write("<html><head><title>" + doc_id + "</title></head><body>")
        fh.write(body)
        fh.write("</body></html>")

def build_href_breadcrumb(root):
    """Returns dict mapping href -> list of section names from root to leaf."""
    result = {}
    def traverse(item, ancestors):
        name_els = item.findall("name")
        name = name_els[0].text.strip() if name_els and name_els[0].text else ""
        path = ancestors + [name]
        href = item.attrib.get("href", "")
        if href:
            result[href] = path
        for child in item.findall("item"):
            traverse(child, path)
    for item in root.findall("item"):
        traverse(item, [])
    return result

def breadcrumb_artifact_path(breadcrumb, output_dir, extension):
    """Convert TOC breadcrumb list to a nested output artifact path."""
    if not breadcrumb:
        return os.path.join(output_dir, "General." + extension)

    parts = [mkfilename(p).strip() or "Untitled" for p in breadcrumb]
    folder_parts = parts[:-1]
    filename = parts[-1]

    if len(filename.encode()) > 180:
        filename = filename.encode()[:180].decode(errors="ignore").rstrip()

    return os.path.join(output_dir, *folder_parts, filename + "." + extension)


def flat_artifact_path(output_root, href, extension):
    bn = os.path.splitext(os.path.basename(href))[0]
    return os.path.join(output_root, bn + "." + extension)


def pdf_output_path(output_root, breadcrumb, href):
    pdf_root = os.path.join(output_root, "pdf")
    if not breadcrumb:
        return flat_artifact_path(pdf_root, href, "pdf")
    return breadcrumb_artifact_path(breadcrumb, pdf_root, "pdf")


def html_output_path(output_root, breadcrumb, href):
    html_root = os.path.join(output_root, "html")
    return flat_artifact_path(html_root, href, "html")


def sync_output_html(cache_html, output_html):
    os.makedirs(os.path.dirname(output_html), exist_ok=True)
    shutil.copy2(cache_html, output_html)


def iter_manual_items(root):
    for parent in root.iter("item"):
        children = list(parent)
        parent_metadata = item_metadata(parent)
        for idx, item in enumerate(children):
            if item.tag != "item":
                continue
            href = item.attrib.get("href", "")
            if href:
                yield item, href, item_metadata(item, idx, children, parent_metadata)


def load_manual_toc(cache_root, doc_id):
    toc_path = cache_toc_path(cache_root, doc_id)
    if not os.path.exists(toc_path):
        raise RuntimeError("Missing cached TOC for " + doc_id + " at " + toc_path)
    tree = parse_xml_file(toc_path)
    root = tree.getroot()
    return toc_path, root


def render_manual_from_cache(doc_id, output_dir, cache_root, filter_selection=None, force_prompt=False, has_override=False):
    _, root = load_manual_toc(cache_root, doc_id)
    breadcrumb_map = build_href_breadcrumb(root)
    rendered = 0
    selection = resolve_filter_selection(cache_root, doc_id, root, filter_selection, force_prompt, has_override)
    output_root = output_selection_dir(output_dir, doc_id, selection)
    os.makedirs(output_root, exist_ok=True)
    normalized_filters = normalize_filter_spec(selection)

    for _, href, metadata in iter_manual_items(root):
        if not metadata_matches(metadata, normalized_filters):
            continue
        breadcrumb = breadcrumb_map.get(href, [])
        pdf_p = pdf_output_path(output_root, breadcrumb, href)
        cache_html_p = cache_html_path(cache_root, doc_id, href)
        output_html_p = html_output_path(output_root, breadcrumb, href)

        if not os.path.exists(cache_html_p):
            continue

        sync_output_html(cache_html_p, output_html_p)

        if os.path.exists(pdf_p):
            continue

        os.makedirs(os.path.dirname(pdf_p), exist_ok=True)
        make_pdf(cache_html_p, pdf_p)
        rendered += 1

    build_toc_index(cache_root, output_root, doc_id, normalized_filters)
    print("Rendered", rendered, "PDFs from cache for", doc_id)


def reindex_manual(doc_id, output_dir, cache_root, filter_selection=None, force_prompt=False, has_override=False):
    _, root = load_manual_toc(cache_root, doc_id)
    selection = resolve_filter_selection(cache_root, doc_id, root, filter_selection, force_prompt, has_override)
    output_root = output_selection_dir(output_dir, doc_id, selection)
    os.makedirs(output_root, exist_ok=True)
    build_toc_index(cache_root, output_root, doc_id, selection)
    print("Rebuilt index for", doc_id)


def download_manual(driver, t, doc_id, output_dir, cache_root, filter_selection=None, force_prompt=False, has_override=False):
    html_dir = cache_html_dir(cache_root, doc_id)
    os.makedirs(html_dir, exist_ok=True)

    toc_path = cache_toc_path(cache_root, doc_id)
    if not os.path.exists(toc_path):
        print("Downloading the TOC for", doc_id)
        url = "https://techinfo.toyota.com/t3Portal/external/en/" + t + "/" + doc_id + "/toc.xml"
        xml_src = fetch_xml_document(driver, url)
        with open(toc_path, 'w') as fh:
            fh.write(xml_src)

    _, root = load_manual_toc(cache_root, doc_id)
    selection = resolve_filter_selection(cache_root, doc_id, root, filter_selection, force_prompt, has_override)
    output_root = output_selection_dir(output_dir, doc_id, selection)
    os.makedirs(output_root, exist_ok=True)
    breadcrumb_map = build_href_breadcrumb(root)
    n = 0
    normalized_filters = normalize_filter_spec(selection)
    manual_items = [
        (item, href, metadata)
        for item, href, metadata in iter_manual_items(root)
        if metadata_matches(metadata, normalized_filters)
    ]
    c = len(manual_items)

    for _, href, _ in manual_items:
        url = "https://techinfo.toyota.com" + href
        n += 1

        breadcrumb = breadcrumb_map.get(href, [])
        pdf_p = pdf_output_path(output_root, breadcrumb, href)
        output_html_p = html_output_path(output_root, breadcrumb, href)

        print("Downloading", href, " (", n, "/", c, ")...")
        # all are html files, load them all up one at a time and then save them
        f_p = cache_html_path(cache_root, doc_id, href)

        if os.path.exists(f_p):
            sync_output_html(f_p, output_html_p)

        if os.path.exists(f_p) and not os.path.exists(pdf_p):
            os.makedirs(os.path.dirname(pdf_p), exist_ok=True)
            make_pdf(f_p, pdf_p)


        if os.path.exists(f_p) or os.path.exists(pdf_p):
            continue
        page_source = load_manual_page(driver, url)

        if "location='/t3Portal" in page_source:
            print("\tPDF redirect found!")
            m = re.search(r"location='(/t3Portal[^']+)'", page_source)
            if m is None:
                print("\tCould not extract redirect URL, skipping")
                continue
            pdf_url = "https://techinfo.toyota.com" + m.group(1)
            fetch_pdf_via_print(driver, pdf_url, pdf_p)

            print("\tDone")
        else:
            print("\tInjecting scripts...")
            inject_and_save_html(driver, f_p)
            sync_output_html(f_p, output_html_p)
            os.makedirs(os.path.dirname(pdf_p), exist_ok=True)
            make_pdf(f_p, pdf_p)

            print("\tDone")
    
    build_toc_index(cache_root, output_root, doc_id, normalized_filters)


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Download Toyota TIS manuals and save them as local PDFs."
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--render-from-cache",
        action="store_true",
        help="Render missing PDFs from cached HTML and rebuild indexes without logging in.",
    )
    mode_group.add_argument(
        "--reindex",
        action="store_true",
        help="Rebuild indexes from cached TOCs without downloading or rendering.",
    )
    parser.add_argument(
        "--output",
        default="output",
        help="Directory to write PDFs and index files into (default: %(default)s)",
    )
    parser.add_argument(
        "--cache-dir",
        default="cache",
        help="Directory to store cached TOCs, HTML, and temporary downloads (default: %(default)s)",
    )
    parser.add_argument(
        "--model",
        action="append",
        default=[],
        help="Limit RM/BM manuals to a specific tocmodelname such as 'GR Corolla'. Can be passed multiple times.",
    )
    parser.add_argument(
        "--engine",
        action="append",
        default=[],
        help="Limit RM/BM manuals to one or more engines such as 'G16E-GTS'. Can be passed multiple times.",
    )
    parser.add_argument(
        "--year",
        action="append",
        default=[],
        help="Limit RM/BM manuals to one or more model years such as 2025. Can be passed multiple times.",
    )
    parser.add_argument(
        "--choose-filters",
        action="store_true",
        help="Prompt again for RM/BM filter selection even if a saved choice already exists.",
    )
    parser.add_argument(
        "--all-filters",
        action="store_true",
        help="Disable RM/BM filtering and run non-interactively with all models, engines, and years.",
    )
    parser.add_argument(
        "doc_ids",
        nargs="+",
        help="One or more document IDs such as RM3560U, BM3560U, or EM1234.",
    )
    return parser.parse_args(argv)

def make_pdf(src, dest):
    print("Creating PDF from", src, "to", dest)
    result = subprocess.run(
        [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "--print-to-pdf=" + dest,
            "--no-pdf-header-footer",
            "--no-gpu",
            "--headless",
            "file://" + os.path.abspath(src),
        ],
        capture_output=True,
        text=True,
    )

    benign_patterns = [
        "Error parsing certificate:",
        "ERROR: Failed parsing extensions",
        "CVDisplayLinkCreateWithCGDisplay failed",
        "task_policy_set TASK_CATEGORY_POLICY",
        "task_policy_set TASK_SUPPRESSION_POLICY",
    ]

    stderr_lines = []
    for line in result.stderr.splitlines():
        if any(pattern in line for pattern in benign_patterns):
            continue
        stderr_lines.append(line)

    if stderr_lines:
        print("\n".join(stderr_lines))

    if result.returncode != 0:
        raise RuntimeError("Chrome PDF generation failed for " + dest)


if __name__ == "__main__":
    args = parse_args(sys.argv[1:])

    output_dir = args.output
    cache_root = args.cache_dir
    download_dir = cache_download_dir(cache_root)
    EWDS = []
    REPAIR_MANUALS = []
    COLLISION_MANUALS = []

    for arg in args.doc_ids:
        if arg.startswith('EM'):
            EWDS.append(arg)
        elif arg.startswith('RM'):
            REPAIR_MANUALS.append(arg)
        elif arg.startswith('BM'):
            COLLISION_MANUALS.append(arg)
        else:
            print("Unknown document type for '" + arg + "'!")
            sys.exit(1)

    filter_selection = {
        "models": args.model,
        "engines": args.engine,
        "years": args.year,
    }
    has_filter_override = any(filter_selection.values())

    if args.all_filters:
        filter_selection = {"models": [], "engines": [], "years": []}
        args.choose_filters = False
        has_filter_override = True

    if args.reindex:
        for doc_id in COLLISION_MANUALS + REPAIR_MANUALS:
            reindex_manual(doc_id, output_dir, cache_root, filter_selection, args.choose_filters, has_filter_override)
        if EWDS:
            print("Reindex mode does not apply to electrical wiring diagrams.")
        if EWDS and any(filter_selection.values()):
            print("Model, engine, and year filters do not apply to electrical wiring diagrams.")
        sys.exit(0)

    if args.render_from_cache:
        for doc_id in COLLISION_MANUALS + REPAIR_MANUALS:
            render_manual_from_cache(doc_id, output_dir, cache_root, filter_selection, args.choose_filters, has_filter_override)
        if EWDS:
            print("Render-from-cache mode does not apply to electrical wiring diagrams.")
        if EWDS and any(filter_selection.values()):
            print("Model, engine, and year filters do not apply to electrical wiring diagrams.")
        sys.exit(0)
    
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("user-data-dir=./user-data")
    chrome_options.add_experimental_option("prefs", {
        "download.default_directory": os.path.abspath(download_dir),
        "download.prompt_for_download": False,
        "plugins.always_open_pdf_externally": True,
    })

    os.makedirs(cache_root, exist_ok=True)
    shutil.rmtree(download_dir, True)
    os.makedirs(download_dir)

    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    try:
        driver.execute_cdp_cmd("Page.setDownloadBehavior", {
            "behavior": "allow",
            "downloadPath": os.path.abspath(download_dir),
        })

        driver.get("https://techinfo.toyota.com")
        input("Please login and press enter to continue...")

        # for each in ewd download
        print("Downloading electrical wiring diagrams...")
        for ewd in EWDS:
            download_ewd(driver, ewd, output_dir, cache_root)

        # download all collision manuals
        print("Downloading collision repair manuals...")
        for cr in COLLISION_MANUALS:
            download_manual(driver, "cr", cr, output_dir, cache_root, filter_selection, args.choose_filters, has_filter_override)

        # download all repair manuals
        print("Downloading repair manuals...")
        for rm in REPAIR_MANUALS:
            download_manual(driver, "rm", rm, output_dir, cache_root, filter_selection, args.choose_filters, has_filter_override)
        if EWDS and any(filter_selection.values()):
            print("Model, engine, and year filters do not apply to electrical wiring diagrams.")
    finally:
        driver.quit()
