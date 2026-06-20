# 台股熱力圖

依產業分類的台股上市熱力圖，支援當日 / 3日 / 5日 / 20日 / 60日切換。

- **區塊大小** = 成交值（億）
- **顏色** = 漲跌幅（台股慣例：紅漲綠跌）
- **資料來源** = 台灣證券交易所 TWSE OpenAPI

## 本機使用

```bash
# 第一次或每日盤後執行（抓取當日資料）
python3 fetch_data.py

# 開啟熱力圖（直接用瀏覽器開啟，或啟動本機伺服器）
open index.html
# 或
python3 -m http.server 8722   # → http://localhost:8722
```

## 部署到 GitHub Pages（雲端自動更新）

1. 在 GitHub 建立一個**私有或公開 repo**，將此資料夾推上去：
   ```bash
   cd ~/Documents/自動化/熱力圖
   git init
   git add .
   git commit -m "初始化台股熱力圖"
   git remote add origin https://github.com/你的帳號/repo名稱.git
   git push -u origin main
   ```

2. 到 GitHub → Settings → Pages → Source 選 **Deploy from a branch**，Branch 選 `main`，Folder 選 `/ (root)`，按 Save。

3. 約 1–2 分鐘後，網站會在 `https://你的帳號.github.io/repo名稱/` 上線。

4. 之後每個**交易日 15:35** GitHub Actions 會自動抓取新資料並更新網站，**完全不需要開機**。

## 資料儲存

- 最多保留 **70 個交易日**的快照（`data/YYYYMMDD.json`）
- 超過自動刪除最舊的一天
- `data/chart_data.js` 為預計算的熱力圖資料（HTML 讀取此檔）

## 手動觸發更新

在 GitHub → Actions → 每日更新台股資料 → Run workflow
