from playwright.sync_api import sync_playwright

PLAYER_ID = 12086

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, channel="chrome", args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36", extra_http_headers={"Referer": "https://www.cricbuzz.com/"})
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        page = context.new_page()

        profile_url = f"https://www.cricbuzz.com/profiles/{PLAYER_ID}"
        page.goto(profile_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)
        batting_link = page.evaluate(f"""() => {{
            const a = Array.from(document.querySelectorAll('a[href*="/{PLAYER_ID}/"][href*="batting"]'));
            return a.length ? a[0].href : null;
        }}""")
        page.goto(batting_link, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)

        # Get series names and their seriesId from the __next_f data
        series_map = page.evaluate("""() => {
            const scripts = Array.from(document.querySelectorAll('script:not([src])'));
            for (const s of scripts) {
                if (s.textContent.includes('seriesMap') || s.textContent.includes('seriesID')) {
                    return s.textContent.slice(0, 3000);
                }
            }
            // Try __next_f chunks
            const chunks = window.__next_f || [];
            for (const chunk of chunks) {
                if (Array.isArray(chunk) && typeof chunk[1] === 'string' && chunk[1].includes('seriesMap')) {
                    return chunk[1].slice(chunk[1].indexOf('seriesMap'), chunk[1].indexOf('seriesMap') + 1000);
                }
            }
            return null;
        }""")
        print("Series map data:")
        print(series_map)

        browser.close()

if __name__ == "__main__":
    main()
