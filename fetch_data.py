#!/usr/bin/env python3
"""
台股熱力圖資料抓取腳本
- 每日盤後執行（建議 15:30 後）
- 抓取 TWSE 上市股票日成交資料 + 產業分類
- 最多保存 70 個交易日，超過自動刪除舊資料
- 自動產生 data/chart_data.js 供 index.html 使用
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
    try:
        return float(str(s).replace(',', '').replace('+', ''))
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

def compute_period(sorted_dates, n, all_data):
    use = sorted_dates[:n]
    if not use:
        return None
    latest_d, oldest_d = use[0], use[-1]
    latest_stocks = {s['code']: s for s in all_data.get(latest_d, {}).get('stocks', [])}
    oldest_stocks = {s['code']: s for s in all_data.get(oldest_d, {}).get('stocks', [])}

    code_value = defaultdict(int)
    for d in use:
        for s in all_data.get(d, {}).get('stocks', []):
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
            'stocks': [{'c': i['code'], 'n': i['name'], 'p': i['pct'], 'v': i['value']} for i in items],
        })
    sectors.sort(key=lambda x: x['totalValue'], reverse=True)

    return {'fromDate': oldest_d, 'toDate': latest_d, 'actualDays': len(use), 'sectors': sectors}

def main():
    print("=" * 52)
    print(f"  台股熱力圖資料抓取")
    print(f"  {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 52)

    # 1. 產業分類
    print("\n[1/4] 抓取產業分類...")
    try:
        basic = fetch("https://openapi.twse.com.tw/v1/opendata/t187ap03_L")
        code_to_ind = {r['公司代號']: r['產業別'] for r in basic}
        print(f"      {len(code_to_ind)} 支公司")
    except Exception as e:
        print(f"      錯誤: {e}")
        sys.exit(1)

    # 2. 今日行情
    print("\n[2/4] 抓取今日行情...")
    try:
        prices = fetch("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL")
    except Exception as e:
        print(f"      錯誤: {e}")
        sys.exit(1)

    trade_date = twse_date_to_ad(prices[0].get('Date', '')) or datetime.date.today().strftime('%Y%m%d')
    print(f"      交易日: {trade_date}")

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
            'code': code, 'name': r['Name'],
            'close': close, 'change': change, 'pct': pct,
            'value': int(value),
            'sector': INDUSTRY_NAMES.get(ind_code, '其他'),
            'sectorCode': ind_code,
        })
    print(f"      {len(stocks)} 支有效股票")

    # 3. 儲存快照 + 更新 manifest
    print(f"\n[3/4] 儲存資料...")
    out_path = os.path.join(DATA_DIR, f"{trade_date}.json")
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump({'date': trade_date, 'stocks': stocks}, f, ensure_ascii=False)
    print(f"      儲存: {trade_date}.json")

    manifest = load_manifest()
    if trade_date not in manifest['dates']:
        manifest['dates'].append(trade_date)
    manifest['dates'].sort(reverse=True)

    if len(manifest['dates']) > MAX_DAYS:
        for old_d in manifest['dates'][MAX_DAYS:]:
            old_file = os.path.join(DATA_DIR, f"{old_d}.json")
            if os.path.exists(old_file):
                os.remove(old_file)
                print(f"      刪除舊資料: {old_d}.json")
        manifest['dates'] = manifest['dates'][:MAX_DAYS]

    save_manifest(manifest)
    print(f"      資料庫: {len(manifest['dates'])} 個交易日 (最多 {MAX_DAYS} 天)")

    # 4. 計算各週期並產生 chart_data.js
    print(f"\n[4/4] 計算熱力圖資料...")
    needed = manifest['dates'][:61]  # 最多需要 60 個交易日
    all_data = {d: load_day(d) for d in needed if load_day(d)}
    avail = sorted(all_data.keys(), reverse=True)
    print(f"      可用天數: {len(avail)}")

    chart = {}
    for n in [1, 3, 5, 20, 60]:
        key = f'{n}d'
        res = compute_period(avail, n, all_data)
        if res:
            chart[key] = res
            print(f"      {n}日: {res['fromDate']} ~ {res['toDate']} ({res['actualDays']}天) {len(res['sectors'])}個產業")

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
