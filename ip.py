# streamlit_app.py

# pip install streamlit playwright pandas
# playwright install chromium

import asyncio
import re
import pandas as pd
import streamlit as st
from playwright.async_api import async_playwright

st.set_page_config(
    page_title="SenderScore Domain Extractor",
    layout="wide"
)

# =========================
# SESSION STATE
# =========================
if "all_domains" not in st.session_state:
    st.session_state.all_domains = []

if "root_domains" not in st.session_state:
    st.session_state.root_domains = []

if "status" not in st.session_state:
    st.session_state.status = "Idle"

# =========================
# FUNCTIONS
# =========================
def get_root_domain(domain):
    domain = domain.lower().strip()
    parts = domain.split(".")
    if len(parts) >= 2:
        return parts[-2] + "." + parts[-1]
    return domain

def add_domain(domain):
    domain = domain.lower().strip()

    if domain not in st.session_state.all_domains:
        st.session_state.all_domains.append(domain)

    root = get_root_domain(domain)

    if root not in st.session_state.root_domains:
        st.session_state.root_domains.append(root)

async def wait_for_cloudflare(page, timeout=60):
    st.session_state.status = "Waiting for Cloudflare..."

    for i in range(timeout):
        try:
            cf_present = await page.locator("text=Verify you are human").count()

            if cf_present == 0:
                title = await page.title()

                if (
                    "just a moment" not in title.lower()
                    and "attention required" not in title.lower()
                ):
                    return True

        except:
            pass

        await page.wait_for_timeout(1000)

    return False

async def scrape_sender_domains(url):
    st.session_state.status = "Opening browser..."

    st.session_state.all_domains = []
    st.session_state.root_domains = []

    try:
        async with async_playwright() as p:

            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled"
                ]
            )

            page = await browser.new_page()

            await page.set_viewport_size({
                "width": 1400,
                "height": 900
            })

            await page.evaluate("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)

            st.session_state.status = "Opening SenderScore..."

            try:
                await page.goto(
                    url,
                    wait_until="networkidle",
                    timeout=120000
                )
            except:
                pass

            await page.wait_for_timeout(3000)

            # Cloudflare wait
            cf_ok = await wait_for_cloudflare(page)

            if not cf_ok:
                st.session_state.status = "Cloudflare verification failed"
                await browser.close()
                return

            st.session_state.status = "Searching for domains..."

            found = False

            for _ in range(40):

                try:
                    count = await page.locator("table tbody tr").count()

                    if count > 0:
                        found = True
                        break

                except:
                    pass

                await page.wait_for_timeout(500)

            # Scroll if not found
            if not found:

                for i in range(1, 15):
                    await page.evaluate(
                        f"window.scrollTo(0, document.body.scrollHeight * {i/15})"
                    )
                    await page.wait_for_timeout(300)

                await page.wait_for_timeout(2000)

            st.session_state.status = "Extracting domains..."

            visited = set()
            page_num = 1

            while True:

                rows = page.locator("table tbody tr")
                count = await rows.count()

                current_page_domains = []

                for i in range(count):

                    try:
                        row = rows.nth(i)

                        txt = (
                            await row.locator("td").first.inner_text()
                        ).strip().lower()

                        txt = txt.replace("www.", "")
                        txt = re.sub(r"[^a-z0-9.-]", "", txt)

                        if (
                            "." in txt
                            and "/" not in txt
                            and " " not in txt
                            and len(txt) > 3
                        ):
                            current_page_domains.append(txt)
                            add_domain(txt)

                    except:
                        pass

                if not current_page_domains:
                    break

                first = current_page_domains[0]

                if first in visited:
                    break

                visited.add(first)

                st.session_state.status = (
                    f"Page {page_num} - "
                    f"{len(st.session_state.all_domains)} domains extracted"
                )

                next_clicked = False

                for selector in [
                    "a.paginate_button.next",
                    "li.paginate_button.next a",
                    "text=Next"
                ]:

                    try:
                        btn = page.locator(selector).first

                        if await btn.count() == 0:
                            continue

                        cls = await btn.get_attribute("class") or ""

                        if "disabled" in cls.lower():
                            break

                        await btn.click()

                        await page.wait_for_timeout(3000)

                        page_num += 1
                        next_clicked = True

                        break

                    except:
                        pass

                if not next_clicked:
                    break

            st.session_state.status = (
                f"Completed! "
                f"{len(st.session_state.all_domains)} domains extracted"
            )

            await browser.close()

    except Exception as e:
        st.session_state.status = f"Error: {str(e)}"

# =========================
# UI
# =========================
st.title("SenderScore Domain Extractor")

url = st.text_input(
    "Paste SenderScore URL"
)

col1, col2 = st.columns(2)

with col1:
    extract = st.button(
        "Extract Domains",
        use_container_width=True
    )

with col2:
    clear = st.button(
        "Clear Results",
        use_container_width=True
    )

if clear:
    st.session_state.all_domains = []
    st.session_state.root_domains = []
    st.session_state.status = "Cleared"

if extract:

    if url.strip():

        asyncio.run(
            scrape_sender_domains(url)
        )

# =========================
# STATUS
# =========================
st.info(
    st.session_state.status
)

# =========================
# STATS
# =========================
s1, s2 = st.columns(2)

with s1:
    st.metric(
        "All Domains",
        len(st.session_state.all_domains)
    )

with s2:
    st.metric(
        "Root Domains",
        len(st.session_state.root_domains)
    )

# =========================
# RESULTS
# =========================
c1, c2 = st.columns(2)

with c1:

    st.subheader("All Domains")

    if st.session_state.all_domains:

        df = pd.DataFrame({
            "Domains": st.session_state.all_domains
        })

        st.dataframe(
            df,
            use_container_width=True,
            height=500
        )

        st.download_button(
            "Download All Domains",
            "\n".join(st.session_state.all_domains),
            file_name="all_domains.txt"
        )

with c2:

    st.subheader("Root Domains")

    if st.session_state.root_domains:

        df2 = pd.DataFrame({
            "Root Domains": st.session_state.root_domains
        })

        st.dataframe(
            df2,
            use_container_width=True,
            height=500
        )

        st.download_button(
            "Download Root Domains",
            "\n".join(st.session_state.root_domains),
            file_name="root_domains.txt"
        )
