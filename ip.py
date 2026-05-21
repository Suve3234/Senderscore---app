# pip install flask playwright
# python -m playwright install chromium

import asyncio
import threading
import re
import os
import platform
import shutil
import tempfile

from flask import Flask, render_template_string, request
from playwright.async_api import async_playwright

app = Flask(__name__)

LIVE_DATA = {
    "running": False,
    "stop_requested": False,
    "status": "Idle",
    "all_domains": [],
    "root_domains": [],
}

HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>SenderScore Extractor</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        *{ margin:0; padding:0; box-sizing:border-box; font-family:Arial,sans-serif; }
        body{ background:#0f172a; color:#e2e8f0; padding:20px; font-size:14px; }
        .wrap{ max-width:1200px; margin:auto; }
        h1{ text-align:center; font-size:22px; color:#60a5fa; margin-bottom:4px; }
        .sub{ text-align:center; color:#64748b; font-size:13px; margin-bottom:20px; }
        .box{ background:#1e293b; border:1px solid #334155; border-radius:12px; padding:16px; margin-bottom:16px; }
        .row{ display:flex; gap:10px; }
        input{ flex:1; background:#0f172a; border:1px solid #334155; color:white; border-radius:8px; padding:10px 14px; font-size:14px; outline:none; }
        input:focus{ border-color:#3b82f6; }
        .btn{ border:none; background:#2563eb; color:white; padding:10px 20px; border-radius:8px; cursor:pointer; font-size:14px; font-weight:600; white-space:nowrap; }
        .btn:hover{ background:#1d4ed8; }
        .stopbtn{ border:none; background:#dc2626; color:white; padding:10px 20px; border-radius:8px; cursor:pointer; font-size:14px; font-weight:600; white-space:nowrap; display:none; }
        .stopbtn:hover{ background:#b91c1c; }
        .status{ margin-top:12px; color:#94a3b8; font-size:13px; }
        .stats{ display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-bottom:16px; }
        .stat{ background:#1e293b; border:1px solid #334155; border-radius:10px; padding:16px; text-align:center; }
        .num{ font-size:28px; font-weight:700; color:#60a5fa; }
        .lbl{ font-size:12px; color:#94a3b8; margin-top:4px; }
        .grid{ display:grid; grid-template-columns:1fr 1fr; gap:12px; }
        .col{ background:#1e293b; border:1px solid #334155; border-radius:12px; padding:16px; }
        .colhead{ display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; }
        .coltitle{ font-size:15px; font-weight:600; color:#60a5fa; }
        .cbtn{ border:none; background:#059669; color:white; padding:6px 14px; border-radius:6px; cursor:pointer; font-size:13px; }
        .cbtn:hover{ background:#047857; }
        .list{ height:500px; overflow-y:auto; }
        .list::-webkit-scrollbar{ width:5px; }
        .list::-webkit-scrollbar-thumb{ background:#334155; border-radius:4px; }
        .item{ padding:8px 10px; margin-bottom:6px; background:#0f172a; border-radius:6px; font-size:13px; color:#cbd5e1; word-break:break-all; }
        .item:hover{ background:#1e40af; color:white; }
        @media(max-width:700px){ .grid,.stats{ grid-template-columns:1fr; } .row{ flex-direction:column; } }
    </style>
</head>
<body>
<div class="wrap">
    <h1>SenderScore Domain Extractor</h1>
    <div class="sub">Extract sending domains from SenderScore report URLs</div>

    <div class="box">
        <form method="POST">
            <div class="row">
                <input type="text" name="url" id="urlInput" placeholder="Paste SenderScore URL here..." required>
                <button class="btn" type="submit" id="extractBtn">Extract</button>
                <button class="stopbtn" type="button" id="stopBtn" onclick="stopExtraction()">Stop</button>
            </div>
        </form>
        <div class="status">Status: <span id="statusText">{{ status }}</span></div>
    </div>

    <div class="stats">
        <div class="stat">
            <div class="num" id="totalDomains">{{ all_domains|length }}</div>
            <div class="lbl">All Domains</div>
        </div>
        <div class="stat">
            <div class="num" id="rootCount">{{ root_domains|length }}</div>
            <div class="lbl">Root Domains</div>
        </div>
    </div>

    <div class="grid">
        <div class="col">
            <div class="colhead">
                <span class="coltitle">All Domains</span>
                <button class="cbtn" onclick="copyDomains('allList')">Copy</button>
            </div>
            <div class="list" id="allList">
                {% for d in all_domains %}<div class="item">{{ d }}</div>{% endfor %}
            </div>
        </div>
        <div class="col">
            <div class="colhead">
                <span class="coltitle">Root Domains</span>
                <button class="cbtn" onclick="copyDomains('rootList')">Copy</button>
            </div>
            <div class="list" id="rootList">
                {% for d in root_domains %}<div class="item">{{ d }}</div>{% endfor %}
            </div>
        </div>
    </div>
</div>
<script>
function copyDomains(id){
    let t=""
    document.querySelectorAll("#"+id+" .item").forEach(el=>{ t+=el.innerText+"\\n" })
    navigator.clipboard.writeText(t)
    alert("Copied!")
}

function stopExtraction(){
    fetch("/stop", {
        method: "POST",
        headers: {"Content-Type": "application/json"}
    }).then(()=>{
        document.getElementById("stopBtn").style.display="none"
        document.getElementById("extractBtn").style.display="inline-block"
        document.getElementById("statusText").innerText="Stopping..."
    }).catch(()=>{
        document.getElementById("statusText").innerText="Stop request failed."
    })
}

async function refreshData(){
    try{
        const d=(await (await fetch("/live")).json())
        document.getElementById("statusText").innerText=d.status
        document.getElementById("totalDomains").innerText=d.all_domains.length
        document.getElementById("rootCount").innerText=d.root_domains.length
        document.getElementById("allList").innerHTML=d.all_domains.map(x=>`<div class="item">${x}</div>`).join("")
        document.getElementById("rootList").innerHTML=d.root_domains.map(x=>`<div class="item">${x}</div>`).join("")

        // Show/hide stop button based on running state
        if(d.running){
            document.getElementById("stopBtn").style.display="inline-block"
            document.getElementById("extractBtn").style.display="none"
        } else {
            document.getElementById("stopBtn").style.display="none"
            document.getElementById("extractBtn").style.display="inline-block"
        }
    }catch(e){}
}

setInterval(refreshData, 1500)
</script>
</body>
</html>
"""

def get_chrome_profile():
    sys_name = platform.system().lower()
    if "windows" in sys_name:
        return os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data")
    elif "darwin" in sys_name:
        return os.path.expanduser("~/Library/Application Support/Google/Chrome")
    else:
        return os.path.expanduser("~/.config/google-chrome")

def copy_chrome_cookies_to_temp():
    src = get_chrome_profile()
    tmp_dir = tempfile.mkdtemp(prefix="chrome_ss_")
    tmp_default = os.path.join(tmp_dir, "Default")
    os.makedirs(tmp_default, exist_ok=True)
    src_default = os.path.join(src, "Default")
    for f in ["Cookies", "Cookies-journal"]:
        src_file = os.path.join(src_default, f)
        dst_file = os.path.join(tmp_default, f)
        if os.path.exists(src_file):
            shutil.copy2(src_file, dst_file)
    return tmp_dir

def get_root_domain(domain):
    domain = domain.lower().strip()
    parts = domain.split(".")
    if len(parts) >= 2:
        return parts[-2] + "." + parts[-1]
    return domain

def add_domain(domain):
    domain = domain.lower().strip()
    if domain in LIVE_DATA["all_domains"]:
        return
    LIVE_DATA["all_domains"].append(domain)
    root = get_root_domain(domain)
    if root not in LIVE_DATA["root_domains"]:
        LIVE_DATA["root_domains"].append(root)

async def wait_for_cloudflare(page, timeout=60):
    print("[CF] Waiting for Cloudflare...", flush=True)
    LIVE_DATA["status"] = "Waiting for Cloudflare check..."
    for i in range(timeout):
        try:
            cf_present = await page.locator("text=Verify you are human").count()
            if cf_present == 0:
                title = await page.title()
                if "just a moment" not in title.lower() and "attention required" not in title.lower():
                    print(f"[CF] Passed after {i}s", flush=True)
                    return True
        except Exception:
            pass
        await page.wait_for_timeout(1000)
    return False

async def scrape_sender_domains(url):
    LIVE_DATA["running"] = True
    LIVE_DATA["stop_requested"] = False
    LIVE_DATA["status"] = "Opening Chrome..."
    LIVE_DATA["all_domains"] = []
    LIVE_DATA["root_domains"] = []

    tmp_profile = copy_chrome_cookies_to_temp()

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch_persistent_context(
                user_data_dir=tmp_profile,
                channel="chrome",
                headless=False,
                args=[
                    "--start-maximized",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-blink-features=AutomationControlled",
                ]
            )

            page = browser.pages[0] if browser.pages else await browser.new_page()

            # Hide automation before navigation
            await page.evaluate("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                window.chrome = { runtime: {} };
            """)

            LIVE_DATA["status"] = "Opening SenderScore..."
            print(f"[SCRAPER] Going to: {url}", flush=True)

            try:
                await page.goto(url, wait_until="networkidle", timeout=120000)
            except Exception:
                # networkidle can timeout on heavy pages — that's fine, continue
                pass

            await page.wait_for_timeout(3000)
            print(f"[SCRAPER] Page title: {await page.title()}", flush=True)

            cf_ok = await wait_for_cloudflare(page, timeout=60)
            if not cf_ok:
                LIVE_DATA["status"] = "❌ Cloudflare check did not pass."
                await browser.close()
                LIVE_DATA["running"] = False
                return

            LIVE_DATA["status"] = "Waiting for domain table..."

            found = False
            for _ in range(30):
                if LIVE_DATA["stop_requested"]:
                    break
                try:
                    count = await page.locator("table tbody tr").count()
                    if count > 0:
                        found = True
                        break
                except Exception:
                    pass
                await page.wait_for_timeout(500)

            if not found and not LIVE_DATA["stop_requested"]:
                LIVE_DATA["status"] = "Scrolling to find table..."
                for i in range(1, 16):
                    await page.evaluate(f"window.scrollTo(0, document.body.scrollHeight * {i/15})")
                    await page.wait_for_timeout(150)
                await page.wait_for_timeout(1000)
                for _ in range(20):
                    if LIVE_DATA["stop_requested"]:
                        break
                    try:
                        count = await page.locator("table tbody tr").count()
                        if count > 0:
                            found = True
                            break
                    except Exception:
                        pass
                    await page.wait_for_timeout(500)

            if not found:
                LIVE_DATA["status"] = "❌ Could not find domains table."
                await browser.close()
                LIVE_DATA["running"] = False
                return

            LIVE_DATA["status"] = "Extracting domains..."
            visited = set()
            page_num = 1

            while True:
                if LIVE_DATA["stop_requested"]:
                    LIVE_DATA["status"] = f"⛔ Stopped. {len(LIVE_DATA['all_domains'])} domains collected."
                    break

                await page.wait_for_timeout(250)

                rows = page.locator("table tbody tr")
                count = await rows.count()
                current_page_domains = []

                for i in range(count):
                    try:
                        row = rows.nth(i)
                        txt = (await row.locator("td").first.inner_text()).strip().lower()
                        txt = txt.replace("www.", "")
                        txt = re.sub(r"[^a-z0-9.-]", "", txt)
                        if "." in txt and " " not in txt and "/" not in txt and len(txt) > 3:
                            current_page_domains.append(txt)
                            add_domain(txt)
                            LIVE_DATA["status"] = f"Page {page_num} — {len(LIVE_DATA['all_domains'])} domains extracted"
                    except Exception:
                        pass

                if not current_page_domains:
                    break

                first = current_page_domains[0]
                if first in visited:
                    break
                visited.add(first)

                # Check stop before clicking next
                if LIVE_DATA["stop_requested"]:
                    LIVE_DATA["status"] = f"⛔ Stopped. {len(LIVE_DATA['all_domains'])} domains collected."
                    break

                next_clicked = False
                for selector in [
                    "a.paginate_button.next",
                    "li.paginate_button.next a",
                    "text=Next",
                ]:
                    try:
                        btn = page.locator(selector).first
                        if await btn.count() == 0:
                            continue
                        cls = await btn.get_attribute("class") or ""
                        if "disabled" in cls.lower():
                            break
                        await btn.scroll_into_view_if_needed()
                        await btn.click()
                        await page.wait_for_timeout(5)
                        page_num += 1
                        next_clicked = True
                        break
                    except Exception:
                        pass

                if not next_clicked:
                    break

            if not LIVE_DATA["stop_requested"]:
                LIVE_DATA["status"] = f"✅ Completed! {len(LIVE_DATA['all_domains'])} domains extracted"

            await browser.close()

    except Exception as e:
        LIVE_DATA["status"] = f"❌ Error: {str(e)}"
        print(f"[SCRAPER] Error: {e}", flush=True)
    finally:
        shutil.rmtree(tmp_profile, ignore_errors=True)

    LIVE_DATA["running"] = False

def start_scraper(url):
    asyncio.run(scrape_sender_domains(url))

@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "POST":
        url = request.form.get("url")
        if url and not LIVE_DATA["running"]:
            thread = threading.Thread(target=start_scraper, args=(url,))
            thread.daemon = True
            thread.start()
    return render_template_string(
        HTML,
        status=LIVE_DATA["status"],
        all_domains=LIVE_DATA["all_domains"],
        root_domains=LIVE_DATA["root_domains"],
    )

@app.route("/stop", methods=["POST"])
def stop():
    LIVE_DATA["stop_requested"] = True
    LIVE_DATA["status"] = "⛔ Stopping..."
    print("[FLASK] Stop requested.", flush=True)
    from flask import jsonify
    return jsonify({"ok": True})

@app.route("/live")
def live():
    return {
        "running": LIVE_DATA["running"],
        "status": LIVE_DATA["status"],
        "all_domains": LIVE_DATA["all_domains"],
        "root_domains": LIVE_DATA["root_domains"],
    }

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True, use_reloader=False)
