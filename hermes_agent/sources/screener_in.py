"""
Hermes — Screener.in Integration
Deep fundamentals: Piotroski F-Score, 10-year data, DuPont analysis.
Screener.in is the best free source for Indian company financials.
"""

import logging
import requests
from bs4 import BeautifulSoup

log = logging.getLogger("hermes.screener")

BASE = "https://www.screener.in"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml",
}


def _get_page(symbol: str) -> BeautifulSoup | None:
    sym = symbol.replace(".NS","").upper()
    try:
        url = f"{BASE}/company/{sym}/consolidated/"
        r   = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code == 404:
            url = f"{BASE}/company/{sym}/"
            r   = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            return BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        log.debug(f"Screener fetch failed {sym}: {e}")
    return None


def _parse_number(text: str) -> float | None:
    if not text:
        return None
    clean = text.strip().replace(",","").replace("%","").replace("₹","").replace("Cr","").strip()
    try:
        return float(clean)
    except ValueError:
        return None


def get_screener_data(symbol: str) -> dict | None:
    """
    Scrape Screener.in for key ratios and financial data.
    Returns: sales growth, profit growth, ROCE, ROE, P/E, D/E, promoter%
    """
    soup = _get_page(symbol)
    if not soup:
        return None

    sym = symbol.replace(".NS","").upper()
    result = {"symbol": sym}

    try:
        # Key ratios section
        ratios = {}
        ratio_section = soup.find("section", id="top-ratios")
        if ratio_section:
            for li in ratio_section.find_all("li"):
                name_tag = li.find("span", class_="name")
                val_tag  = li.find("span", class_="value") or li.find("span", class_="number")
                if name_tag and val_tag:
                    key = name_tag.get_text(strip=True).lower()
                    val = val_tag.get_text(strip=True)
                    ratios[key] = val

        result["market_cap"]  = _parse_number(ratios.get("market cap",""))
        result["pe"]          = _parse_number(ratios.get("stock p/e","") or ratios.get("p/e",""))
        result["pb"]          = _parse_number(ratios.get("price to book","") or ratios.get("p/b",""))
        result["roce"]        = _parse_number(ratios.get("roce",""))
        result["roe"]         = _parse_number(ratios.get("roe",""))
        result["div_yield"]   = _parse_number(ratios.get("dividend yield",""))
        result["debt_equity"] = _parse_number(ratios.get("debt / equity","") or ratios.get("d/e",""))
        result["current_ratio"]= _parse_number(ratios.get("current ratio",""))

        # Quarterly profit trend (last 4 quarters)
        profit_table = soup.find("section", id="quarters")
        profits = []
        if profit_table:
            rows = profit_table.find_all("tr")
            for row in rows:
                cells = row.find_all("td")
                label = row.find("td")
                if label and "net profit" in label.get_text("",strip=True).lower():
                    profits = [_parse_number(c.get_text(strip=True)) for c in cells[1:5]]
                    profits = [p for p in profits if p is not None]
                    break

        result["recent_profits"] = profits
        result["profit_trend"]   = (
            "GROWING"    if len(profits) >= 2 and profits[0] > profits[-1] else
            "DECLINING"  if len(profits) >= 2 and profits[0] < profits[-1] else
            "STABLE"
        )

        # Sales growth (10 year CAGR if available)
        compounded = {}
        comp_section = soup.find("section", id="compounded-growth")
        if comp_section:
            for row in comp_section.find_all("tr"):
                cells = row.find_all("td")
                if len(cells) >= 2:
                    key = cells[0].get_text(strip=True).lower()
                    val = _parse_number(cells[1].get_text(strip=True))
                    if val is not None:
                        compounded[key] = val

        result["sales_cagr_10y"]  = compounded.get("sales",  None)
        result["profit_cagr_10y"] = compounded.get("profit", None)
        result["stock_cagr_10y"]  = compounded.get("stock price", None)

        # Piotroski F-Score (simplified 5-point version from available data)
        f_score = 0
        if result.get("roe") and result["roe"] > 0:          f_score += 1
        if result.get("roce") and result["roce"] > 15:        f_score += 1
        if result.get("debt_equity") is not None and result["debt_equity"] < 1: f_score += 1
        if result.get("current_ratio") and result["current_ratio"] > 1: f_score += 1
        if result.get("profit_trend") == "GROWING":           f_score += 1

        result["f_score"]      = f_score
        result["f_score_max"]  = 5
        result["f_interpretation"] = (
            "Strong"  if f_score >= 4 else
            "Average" if f_score >= 3 else
            "Weak"
        )

        return result
    except Exception as e:
        log.warning(f"Screener parse failed {sym}: {e}")
        return result if result else None


def get_watchlist_screener(watchlist: list) -> list:
    results = []
    for sym in watchlist:
        if sym == "NIFTY50":
            continue
        r = get_screener_data(sym)
        if r:
            results.append(r)
    return results
