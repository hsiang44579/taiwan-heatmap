#!/usr/bin/env python3
"""
台股熱力圖資料抓取腳本（支援上市＋上櫃）
"""

import urllib.request
import json
import os
import datetime
import sys
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
os.makedirs(DATA_DIR, exist_ok=True)

MAX_DAYS = 70

INDUSTRY_NAMES = {
    "01": "水泥", "02": "食品", "03": "塑膠", "04": "紡織纖維", "05": "電機機械",
    "06": "電器電纜", "08": "玻璃陶瓷", "09": "造紙", "10": "鋼鐵", "11": "橡膠",
    "12": "汽車", "14": "建材營造", "15": "航運", "16": "觀光餐旅", "17": "金融保險",
    "18": "貿易百貨", "20": "其他", "21": "化學工業", "22": "生技醫療", "23": "油電燃氣",
    "24": "半導體", "25": "電腦週邊", "26": "光電", "27": "通信網路", "28": "電子零組件",
    "29": "電子通路", "30": "資訊服務", "31": "其他電子", "32": "文化創意",
    "35": "綠能環保", "36": "數位雲端", "37": "運動休閒", "38": "居家生活",
}

def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())

def parse_num(s):
    if s is None:
        return None
    try:
        return float(str(s).replace(',', '').replace('+', '').strip())
    except Exception:
        return None

def twse_date_to_ad(twse_date):
    s = str(twse_date).strip()
    if len(s) == 7 and s.isdigit():
        return f"{int(s[:3]) + 1911}{s[3:]}"
    return None

def load_manifest():
    path = os.path.join(DATA_DIR, 'manifest.json')
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    return {'dates': []}

def save_manifest(m):
    with open(os.path.join(DATA_DIR, 'manifest.json'), 'w', encoding='utf-8') as f:
        json.dump(m, f, ensure_ascii=False, indent=2)

def load_day(date_str):
    path = os.path.join(DATA_DIR, f"{date_str}.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding='utf-8') as f:
        return json.load(f)

def build_shares_map(basic_list, code_key, shares_key, capital_key=None, par_key=None):
    """建立 {stock_code: issued_shares} 字典，優先用發行股數，次選資本額÷面額"""
    m = {}
    for r in basic_list:
        code   = r.get(code_key, '').strip()
        shares = parse_num(r.get(shares_key, ''))
        if code and shares and shares > 0:
            m[code] = shares
        elif code and capital_key:
            cap = parse_num(r.get(capital_key, ''))
            par = parse_num(r.get(par_key, '')) or 10.0
            if cap and par:
                m[code] = cap / par
    return m

def calc_mktcap(close, shares_map, code):
    shares = shares_map.get(code)
    if not shares or not close:
        return 0
    return round(close * shares)

def parse_tse_stocks(prices, code_to_ind, capital_map=None):
    trade_date = twse_date_to_ad(prices[0].get('Date', '')) if prices else None
    capital_map = capital_map or {}
    stocks = []
    for r in prices:
        code = r.get('Code', '')
        if not (code.isdigit() and len(code) == 4):
            continue
        close = parse_num(r.get('ClosingPrice'))
        change = parse_num(r.get('Change'))
        value = parse_num(r.get('TradeValue'))
        if close is None or change is None or not value:
            continue
        prev = close - change
        pct = round(change / prev * 100, 2) if prev else 0
        ind_code = code_to_ind.get(code, '')
        stocks.append({
            'code': code, 'name': r.get('Name', ''),
            'close': close, 'pct': pct,
            'value': int(value),
            'mktcap': calc_mktcap(close, capital_map, code),
            'sector': INDUSTRY_NAMES.get(ind_code, '其他'),
        })
    return stocks, trade_date

def get_field(r, *names):
    for n in names:
        v = r.get(n)
        if v is not None and str(v).strip() not in ('', '--', '-'):
            return str(v).strip()
    return ''

def parse_otc_stocks(data, code_to_ind, capital_map=None):
    if not data:
        return [], None
    records = data if isinstance(data, list) else []
    if not records:
        print("      [警告] OTC 資料格式異常，非陣列")
        return [], None

    print(f"      [OTC 欄位] {list(records[0].keys())[:10]}")
    capital_map = capital_map or {}

    trade_date = None
    stocks = []
    for r in records:
        code = get_field(r, 'SecuritiesCompanyCode', 'Code', 'stockCode', '公司代號')
        if not (code.isdigit() and len(code) == 4):
            continue
        name = get_field(r, 'CompanyName', 'SecuritiesCompanyName', 'Name', '公司名稱')
        close = parse_num(get_field(r, 'Close', 'ClosingPrice', '收盤'))
        change = parse_num(get_field(r, 'Change', '漲跌'))
        # TPEx 回傳 TradingShares × Average，沒有直接的 TradeValue
        value = parse_num(get_field(r, 'TradeValue', '成交值'))
        if not value:
            shares = parse_num(get_field(r, 'TradingShares', '成交股數'))
            avg    = parse_num(get_field(r, 'Average', '均價'))
            if shares and avg:
                value = shares * avg

        if not trade_date:
            raw = get_field(r, 'Date', 'date', '日期')
            trade_date = twse_date_to_ad(raw) if raw else None

        if close is None or change is None or not value:
            continue
        prev = close - change
        pct = round(change / prev * 100, 2) if prev else 0
        ind_code = code_to_ind.get(code, '')
        stocks.append({
            'code': code, 'name': name,
            'close': close, 'pct': pct,
            'value': int(value),
            'mktcap': calc_mktcap(close, capital_map, code),
            'sector': INDUSTRY_NAMES.get(ind_code, '其他'),
        })
    return stocks, trade_date

def get_stocks_for_market(day_data, market):
    if not day_data:
        return []
    if market == 'all':
        tse = day_data.get('tse', day_data.get('stocks', []))
        otc = day_data.get('otc', [])
        # 上市上櫃合併，code 不重複
        seen = set()
        result = []
        for s in tse + otc:
            if s['code'] not in seen:
                seen.add(s['code'])
                result.append(s)
        return result
    elif market == 'tse':
        return day_data.get('tse', day_data.get('stocks', []))
    elif market == 'otc':
        return day_data.get('otc', [])
    return []

def compute_period(sorted_dates, n, all_data, market='tse'):
    use = sorted_dates[:n]
    if not use:
        return None
    latest_d, oldest_d = use[0], use[-1]
    latest_stocks = {s['code']: s for s in get_stocks_for_market(all_data.get(latest_d), market)}
    oldest_stocks = {s['code']: s for s in get_stocks_for_market(all_data.get(oldest_d), market)}

    code_value = defaultdict(int)
    for d in use:
        for s in get_stocks_for_market(all_data.get(d), market):
            code_value[s['code']] += s.get('value', 0)

    result = []
    for code, total_val in code_value.items():
        if total_val < 500_000:
            continue
        latest = latest_stocks.get(code)
        if not latest:
            continue
        close_now = latest.get('close', 0)
        if n == 1 or oldest_d == latest_d:
            pct = latest.get('pct', 0)
        else:
            oldest = oldest_stocks.get(code)
            close_base = oldest.get('close', 0) if oldest else 0
            pct = round((close_now / close_base - 1) * 100, 2) if close_base else latest.get('pct', 0)
        result.append({
            'code': code,
            'name': latest.get('name', ''),
            'close': close_now,
            'pct': pct,
            'value': total_val,
            'mktcap': latest.get('mktcap', 0),
            'sector': latest.get('sector', '其他'),
        })

    by_sec = defaultdict(list)
    for s in result:
        by_sec[s['sector']].append(s)

    sectors = []
    for sec_name, items in by_sec.items():
        items.sort(key=lambda x: x['value'], reverse=True)
        sec_total = sum(i['value'] for i in items)
        if sec_total < 50_000_000:
            continue
        avg_pct = sum(i['pct'] * i['value'] for i in items) / sec_total
        sectors.append({
            'name': sec_name,
            'totalValue': sec_total,
            'avgPct': round(avg_pct, 2),
            'stocks': [{'c': i['code'], 'n': i['name'], 'p': i['pct'],
                        'v': i['value'], 'cl': round(i['close'], 2),
                        'm': i.get('mktcap', 0)} for i in items],
        })
    sectors.sort(key=lambda x: x['totalValue'], reverse=True)

    return {'fromDate': oldest_d, 'toDate': latest_d, 'actualDays': len(use), 'sectors': sectors}

def main():
    print("=" * 52)
    print(f"  台股熱力圖資料抓取（上市＋上櫃）")
    print(f"  {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 52)

    # 1. 上市產業分類＋發行股數
    print("\n[1/5] 抓取上市產業分類...")
    try:
        basic_tse = fetch("https://openapi.twse.com.tw/v1/opendata/t187ap03_L")
        code_to_ind_tse = {r['公司代號']: r['產業別'] for r in basic_tse}
        shares_map_tse  = build_shares_map(basic_tse, '公司代號',
                                            '已發行普通股數或TDR原股發行股數',
                                            '實收資本額', '普通股每股面額')
        print(f"      {len(code_to_ind_tse)} 支上市公司　(含市值資料 {len(shares_map_tse)} 支)")
    except Exception as e:
        print(f"      錯誤: {e}")
        sys.exit(1)

    # 2. 上櫃產業分類＋發行股數
    print("\n[2/5] 抓取上櫃產業分類...")
    shares_map_otc = {}
    try:
        basic_otc = fetch("https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O")
        code_to_ind_otc = {r['SecuritiesCompanyCode']: r['SecuritiesIndustryCode'] for r in basic_otc}
        shares_map_otc  = build_shares_map(basic_otc, 'SecuritiesCompanyCode',
                                            'IssueShares', 'Paidin.Capital.NTDollars',
                                            'ParValueOfCommonStock')
        print(f"      {len(code_to_ind_otc)} 支上櫃公司　(含市值資料 {len(shares_map_otc)} 支)")
    except Exception as e:
        print(f"      上櫃分類失敗（繼續）: {e}")
        code_to_ind_otc = {}

    # 3. 上市行情
    print("\n[3/5] 抓取上市行情...")
    try:
        tse_prices = fetch("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL")
        tse_stocks, trade_date = parse_tse_stocks(tse_prices, code_to_ind_tse, shares_map_tse)
        mc_count = sum(1 for s in tse_stocks if s.get('mktcap', 0) > 0)
        print(f"      {len(tse_stocks)} 支　交易日: {trade_date}　市值計算: {mc_count} 支")
    except Exception as e:
        print(f"      錯誤: {e}")
        sys.exit(1)

    # 4. 上櫃行情
    print("\n[4/5] 抓取上櫃行情...")
    otc_stocks = []
    try:
        otc_raw = fetch("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes")
        otc_stocks, otc_date = parse_otc_stocks(otc_raw, code_to_ind_otc, shares_map_otc)
        print(f"      {len(otc_stocks)} 支　交易日: {otc_date}")
        if not trade_date and otc_date:
            trade_date = otc_date
    except Exception as e:
        print(f"      上櫃行情失敗（繼續執行）: {e}")

    if not trade_date:
        trade_date = datetime.date.today().strftime('%Y%m%d')

    # 5. 儲存 & 計算
    print(f"\n[5/5] 儲存資料與計算熱力圖...")
    out_path = os.path.join(DATA_DIR, f"{trade_date}.json")
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump({'date': trade_date, 'tse': tse_stocks, 'otc': otc_stocks}, f, ensure_ascii=False)
    print(f"      {trade_date}.json (TSE:{len(tse_stocks)} OTC:{len(otc_stocks)})")

    manifest = load_manifest()
    if trade_date not in manifest['dates']:
        manifest['dates'].append(trade_date)
    manifest['dates'].sort(reverse=True)

    if len(manifest['dates']) > MAX_DAYS:
        for old_d in manifest['dates'][MAX_DAYS:]:
            old_file = os.path.join(DATA_DIR, f"{old_d}.json")
            if os.path.exists(old_file):
                os.remove(old_file)
                print(f"      刪除: {old_d}.json")
        manifest['dates'] = manifest['dates'][:MAX_DAYS]

    save_manifest(manifest)
    print(f"      資料庫: {len(manifest['dates'])} 個交易日（最多 {MAX_DAYS} 天）")

    needed = manifest['dates'][:61]
    all_data = {d: load_day(d) for d in needed if load_day(d)}
    avail = sorted(all_data.keys(), reverse=True)
    print(f"      可用天數: {len(avail)}")

    chart = {}
    for n in [1, 3, 5, 20, 60]:
        key = f'{n}d'
        chart[key] = {}
        for market in ['tse', 'otc', 'all']:
            res = compute_period(avail, n, all_data, market)
            if res:
                chart[key][market] = res
        tse_r = chart[key].get('tse', {})
        otc_r = chart[key].get('otc', {})
        print(f"      {n}日 TSE:{len(tse_r.get('sectors',[]))}個產業  OTC:{len(otc_r.get('sectors',[]))}個產業")

    chart['updatedAt'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    chart['totalDays'] = len(manifest['dates'])

    js_path = os.path.join(DATA_DIR, 'chart_data.js')
    with open(js_path, 'w', encoding='utf-8') as f:
        f.write(f"/* 自動產生 {chart['updatedAt']} — 請勿手動修改 */\n")
        f.write(f"const CHART_DATA = {json.dumps(chart, ensure_ascii=False)};\n")
    print(f"      chart_data.js 已更新")
    print(f"\n✓ 完成！請開啟 index.html 查看熱力圖。\n")

if __name__ == '__main__':
    main()
