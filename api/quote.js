// Vercel Serverless Function：代理 TWSE mis 即時報價，加上 CORS 並強制不快取
// 前端以同源 /api/quote?ex_ch=tse_2330.tw|otc_6488.tw 呼叫，避免瀏覽器 CORS 限制
export default async function handler(req, res) {
  const exCh = req.query.ex_ch;
  if (!exCh) {
    res.status(400).json({ error: 'missing ex_ch' });
    return;
  }

  const url = 'https://mis.twse.com.tw/stock/api/getStockInfo.jsp'
    + `?ex_ch=${encodeURIComponent(exCh)}&json=1&delay=0&_=${Date.now()}`;

  try {
    const r = await fetch(url, {
      headers: {
        'Referer': 'https://mis.twse.com.tw/stock/index.jsp',
        'User-Agent': 'Mozilla/5.0 (compatible; heatmap/1.0)',
      },
    });
    const data = await r.json();
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Cache-Control', 'no-store, max-age=0');
    res.status(200).json(data);
  } catch (e) {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.status(502).json({ error: String(e) });
  }
}
