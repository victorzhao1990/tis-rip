#!/usr/bin/env python3
from selenium import webdriver
import time
import os.path
import xml.etree.ElementTree as ET
import shutil
import subprocess
from bs4 import BeautifulSoup
import os
import sys


def mkfilename(s):
    fn = ""
    for x in s:
        if x.isalnum() or x == " ":
            fn += x
        else:
            fn += "_"
    return fn

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

def download_ewd(driver, ewd):
    SYSTEMS = ["system", "routing", "overall"]

    for s in SYSTEMS:
        fn = os.path.join(ewd, s, "index.xml")
        d = os.path.join(ewd, s)
        if not os.path.exists(d):
            os.makedirs(d)

        if os.path.exists(fn):
            continue

        url = "https://techinfo.toyota.com/t3Portal/external/en/ewdappu/" + ewd + "/ewd/contents/" + s + "/title.xml"
        print("Loading", url)
        driver.get(url)
        print("Saving...")
        xml_src = driver.execute_script('return document.getElementById("webkit-xml-viewer-source-xml").innerHTML')
        with open(fn, 'w') as fh:
            fh.write(xml_src)

    for s in SYSTEMS:
        idx = os.path.join(ewd, s, "index.xml")
        print(idx)
        tree = ET.parse(idx)
        root = tree.getroot()
        for child in root:
            name = child.findall('name')[0].text
            fig = child.findall('fig')[0].text
            fn = os.path.join(ewd, s, mkfilename(fig + " " + name) + ".pdf")

            if os.path.exists(fn):
                continue

            print("Downloading ", name, "...")
            url = "https://techinfo.toyota.com/t3Portal/external/en/ewdappu/" + ewd + "/ewd/contents/" + s + "/pdf/" + fig + ".pdf"
            driver.get(url)
            # this will have downloaded the file, or not
            temp_dl_path = os.path.join("download", fig + ".pdf.crdownload")
            while os.path.exists(temp_dl_path):
                time.sleep(0.2)
            dl_path = os.path.join("download", fig + ".pdf")
            if not os.path.exists(dl_path):
                time.sleep(1)
            if not os.path.exists(dl_path):
                print("Didn't download ", url, "!")
                continue
            shutil.move(dl_path, fn)
            print("Done ", name)

def toc_parse_items(base, items):
    if len(items) == 0:
        return ""
    
    wrap = "<ul>"

    for i in items:
        wrap += "<li>"
        name = i.findall("name")[0].text
        wrap += name

        if "href" in i.attrib and i.attrib["href"] != "":
            # it has a link, parse it
            bn = os.path.splitext(os.path.basename(i.attrib["href"]))[0]
            html_path = os.path.join(base, "html", bn + ".html")
            pdf_path = os.path.join(base, "pdf", bn + ".pdf")

            if os.path.exists(html_path):
                wrap += " [<a href=\"html/" + bn + ".html\">HTML</a>] "
            if os.path.exists(pdf_path):
                wrap += " [<a href=\"pdf/" + bn + ".pdf\">PDF</a>] "

        wrap += toc_parse_items(base, i.findall("item"))
        wrap += "</li>"

    wrap += "</ul>"
    return wrap

def build_toc_index(base):
    if not os.path.exists(base):
        return False
    toc_path = os.path.join(base, "toc.xml")
    if not os.path.exists(toc_path):
        print("toc.xml missing in ", base)
        return False

    print("Building TOC index from ", toc_path, "...")
    
    tree = ET.parse(toc_path)
    root = tree.getroot()

    body = toc_parse_items(base, root.findall("item"))
    index_out = os.path.join(base, "index.html")
    with open(index_out, "w") as fh:
        fh.write("<!doctype html>\n")
        fh.write("<html><head><title>" + base + "</title></head><body>")
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

def breadcrumb_pdf_path(breadcrumb, output_dir):
    """Convert TOC breadcrumb list to an output PDF path."""
    folder = breadcrumb[0].replace(" ", "_") if breadcrumb else "General"
    filename = "_ ".join(mkfilename(p) for p in breadcrumb) + ".pdf"
    return os.path.join(output_dir, folder, filename)

def download_manual(driver, t, id, output_dir):
    if not os.path.exists(os.path.join(id, "html")):
        os.makedirs(os.path.join(id, "html"))
    toc_path = os.path.join(id, "toc.xml")
    if not os.path.exists(toc_path):
        print("Downloading the TOC for", id)
        url = "https://techinfo.toyota.com/t3Portal/external/en/" + t + "/" + id + "/toc.xml"
        driver.get(url)
        xml_src = driver.execute_script('return document.getElementById("webkit-xml-viewer-source-xml").innerHTML')
        with open(toc_path, 'w') as fh:
            fh.write(xml_src)

    tree = ET.parse(toc_path)
    root = tree.getroot()
    breadcrumb_map = build_href_breadcrumb(root)
    n = 0
    c = 0

    for i in root.iter("item"):
        if not 'href' in i.attrib or i.attrib['href'] == '':
            continue
        c += 1

    for i in root.iter("item"):
        if not 'href' in i.attrib or i.attrib['href'] == '':
            continue
        href = i.attrib['href']
        url = "https://techinfo.toyota.com" + href
        n += 1

        breadcrumb = breadcrumb_map.get(href, [])
        pdf_p = breadcrumb_pdf_path(breadcrumb, os.path.join(output_dir, id)) if breadcrumb else os.path.join(output_dir, id, os.path.basename(href)[:-5] + ".pdf")

        print("Downloading", href, " (", n, "/", c, ")...")
        # all are html files, load them all up one at a time and then save them
        f_parts = href.split('/')
        f_p = os.path.join(id, "html", f_parts[len(f_parts)-1])

        if os.path.exists(f_p) and not os.path.exists(pdf_p):
            os.makedirs(os.path.dirname(pdf_p), exist_ok=True)
            make_pdf(f_p, pdf_p)


        if os.path.exists(f_p) or os.path.exists(pdf_p):
            continue
        driver.get(url)
        page_source = driver.page_source

        if "location='/t3Portal" in page_source:
            print("\tPDF redirect found!")
            import re
            import requests
            m = re.search(r"location='(/t3Portal[^']+)'", page_source)
            if m is None:
                print("\tCould not extract redirect URL, skipping")
                continue
            pdf_url = "https://techinfo.toyota.com" + m.group(1)
            import base64
            driver.get(pdf_url)
            time.sleep(2)
            pdf_data = driver.execute_cdp_cmd("Page.printToPDF", {"printBackground": True})
            os.makedirs(os.path.dirname(pdf_p), exist_ok=True)
            with open(pdf_p, 'wb') as fh:
                fh.write(base64.b64decode(pdf_data['data']))

            print("\tDone")
        else:
            print("\tInjecting scripts...")
            # we want to inject jQuery now
            driver.execute_script("""var s=window.document.createElement('script');\
            s.src='https://cdnjs.cloudflare.com/ajax/libs/jquery/3.4.1/jquery.min.js';\
            window.document.head.appendChild(s);""")

            # remove the toyota footer
            src = None
            try :
                src = driver.execute_script(open("injected.js", "r").read())
            except:
                time.sleep(1)
                src = driver.execute_script(open("injected.js", "r").read())

            with open(f_p, 'w') as fh:
                fh.write(src)

            fix_links(f_p)

            print("\tDone")
    
    build_toc_index(id)

def make_pdf(src, dest):
    print("Creating PDF from", src, "to", dest)
    subprocess.run(["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "--print-to-pdf=" + dest, "--no-gpu", "--headless", "file://" + os.path.abspath(src)])


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("You must pass the documents you wish to download as arguments to this script!")
        sys.exit(1)

    output_dir = "."
    EWDS = []
    REPAIR_MANUALS = []
    COLLISION_MANUALS = []

    args = sys.argv[1:]
    if "--output" in args:
        idx = args.index("--output")
        output_dir = args[idx + 1]
        args = args[:idx] + args[idx + 2:]

    for arg in args:
        if arg.startswith('EM'):
            EWDS.append(arg)
        elif arg.startswith('RM'):
            REPAIR_MANUALS.append(arg)
        elif arg.startswith('BM'):
            COLLISION_MANUALS.append(arg)
        else:
            print("Unknown document type for '" + arg + "'!")
            sys.exit(1)
    
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("user-data-dir=./user-data")
    chrome_options.add_experimental_option("prefs", {
        "download.default_directory": os.path.abspath("download"),
        "download.prompt_for_download": False,
        "plugins.always_open_pdf_externally": True,
    })

    shutil.rmtree("download", True)
    os.makedirs("download")

    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    driver.execute_cdp_cmd("Page.setDownloadBehavior", {
        "behavior": "allow",
        "downloadPath": os.path.abspath("download"),
    })

    driver.get("https://techinfo.toyota.com")
    input("Please login and press enter to continue...")

    # for each in ewd download
    print("Downloading electrical wiring diagrams...")
    for ewd in EWDS:
        download_ewd(driver, ewd)

    # download all collision manuals
    print("Downloading collision repair manuals...")
    for cr in COLLISION_MANUALS:
        download_manual(driver, "cr", cr, output_dir)

    # download all repair manuals
    print("Downloading repair manuals...")
    for rm in REPAIR_MANUALS:
        download_manual(driver, "rm", rm, output_dir)

    driver.close()
