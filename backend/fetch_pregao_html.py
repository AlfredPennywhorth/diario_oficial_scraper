from playwright.sync_api import sync_playwright

def save_html():
    url = "http://diariooficial.prefeitura.sp.gov.br/md_epubli_visualizar.php?l6Wf7e3JZ_J_tIsMh4onqVnjiQd1FO-7AqbBXVfZe63brYS6IYtRumsnuW5GXy6bVYzuXffG60ZvaHgvwLHyIg,,"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(url)
        content = page.content()
        with open("backend/logs/pregao_debug.html", "w", encoding="utf-8") as f:
            f.write(content)
        browser.close()
        print("HTML salvo em backend/logs/pregao_debug.html")

if __name__ == "__main__":
    save_html()
