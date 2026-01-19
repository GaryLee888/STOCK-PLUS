import shioaji as sj
import pandas as pd
import time
import requests
import os
import io
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont

# ==========================================
# 核心策略參數 (與本地端介面參數完全一致)
# ==========================================
SCAN_SEC = 12             # 掃頻(秒)
FILTER_CHG = 3.0          # 漲幅下限%
YEST_VOL_LIMIT = 3000     # 昨日交易量 > 3000
FILTER_EST_VOL = 1.5      # 預估量倍數 > 1.5
MOMENTUM_LIMIT = 1.2      # 1分動能% > 1.2
RETRACEMENT_LIMIT = 0.5   # 回徹限制% < 0.5
MIN_VOL_LIMIT = 2000      # 成交張數 > 2000
VWAP_GAP_LIMIT = 2.5      # 均價乖離% < 2.5

# ==========================================
# 系統與 API 設定
# ==========================================
API_KEY = os.getenv("API_KEY")
SECRET_KEY = os.getenv("SECRET_KEY")
DISCORD_URL = "https://discord.com/api/webhooks/917970232084152411/kkkoyrfBEpN-UVEqweE0iNtpuUFjK4UAc7UKQWaJmio6rT5FJ1TukrE2xARYEZyeuKrQ"

def get_daily_filename():
    return f"DayTrade_Log_{datetime.now().strftime('%Y-%m-%d')}.xlsx"

class DayTradeWorker:
    def __init__(self):
        self.api = sj.Shioaji()
        self.trigger_history = {}
        self.reported_log = {}
        self.ref_map = {}
        self.name_map = {}
        self.cat_map = {}
        self.last_total_vol_map = {} # 用於計算 1 分鐘爆量動能
        self.market_history = {"001": [], "OTC": []} # 大盤監控
        self.market_safe = True
        self.results = [] 

    def check_market_risk(self, api):
        """同步本地端的 check_market_risk 大盤下殺預警"""
        try:
            snaps = api.snapshots([api.Contracts.Indices.TSE["001"], api.Contracts.Indices.OTC["OTC"]])
            now = datetime.now()
            danger = False
            for s in snaps:
                if s.close <= 0: continue
                self.market_history[s.code] = [(t, p) for t, p in self.market_history[s.code] if t > now - timedelta(minutes=5)]
                self.market_history[s.code].append((now, s.close))
                past = [p for t, p in self.market_history[s.code] if t < now - timedelta(minutes=2)]
                if past and (s.close - past[-1]) / past[-1] * 100 < -0.12: danger = True
            self.market_safe = not danger
        except: pass

    def login_and_prepare(self):
        try:
            self.api.login(API_KEY.strip(), SECRET_KEY.strip())
            raw = [c for m in [self.api.Contracts.Stocks.TSE, self.api.Contracts.Stocks.OTC] 
                   for c in m if len(c.code) == 4 and "處置" not in c.name]
            for c in raw:
                if c.reference:
                    self.ref_map[c.code] = float(c.reference)
                    self.name_map[c.code] = c.name
                    self.cat_map[c.code] = c.category
            self.all_codes = [c for c in raw if c.code in self.ref_map]
            requests.post(DISCORD_URL, data={"content": "✅ **終極精準雷達已啟動** | 邏輯已完全同步本地版"})
            return True
        except: return False

    def create_card(self, item):
        # (此部分維持字體防呆邏輯，確保圖片產出正常)
        potential_fonts = ["/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", "msjhbd.ttc"]
        f_title = f_price = f_info = None
        for font_path in potential_fonts:
            try:
                if os.path.exists(font_path):
                    f_title, f_price, f_info = ImageFont.truetype(font_path, 44), ImageFont.truetype(font_path, 70), ImageFont.truetype(font_path, 26)
                    break
            except: continue
        if not f_title: f_title = f_price = f_info = ImageFont.load_default()

        img = Image.new('RGB', (600, 400), color=(18, 19, 23))
        draw = ImageDraw.Draw(img)
        draw.rectangle([0, 0, 15, 400], fill=(255, 60, 60))
        draw.rectangle([15, 0, 600, 45], fill=(255, 215, 0))
        draw.text((40, 8), "🚀 終極精準！發財電報", fill=(0, 0, 0), font=f_info)
        draw.text((40, 65), f"{item['code']} {item['name']}", fill=(255, 255, 255), font=f_title)
        draw.text((40, 130), f"{item['price']}", fill=(255, 60, 60), font=f_price)
        draw.text((320, 160), f"漲幅 {item['chg']}%", fill=(255, 60, 60), font=f_info)
        draw.text((40, 360), f"動能: {item['min_v']}% | 均偏: {item['vwap_dist']}%", fill=(255, 215, 0), font=ImageFont.load_default())
        
        buf = io.BytesIO(); img.save(buf, format='PNG'); buf.seek(0); return buf

    def start_monitoring(self):
        if not self.login_and_prepare(): return

        while True:
            now = datetime.now(); hm = now.hour * 100 + now.minute
            if hm > 1345: break
            if hm < 900: time.sleep(30); continue
            
            self.check_market_risk(self.api)
            
            # 同步本地端的動態門檻調整
            if hm < 1000: v_base, m_adj, h_thr = 0.75, 2.0, 15
            elif hm < 1130: v_base, m_adj, h_thr = 0.55, 1.5, 10
            elif hm < 1300: v_base, m_adj, h_thr = 0.40, 1.2, 8
            else: v_base, m_adj, h_thr = 0.60, 2.5, 20

            # 調整 1 分動能門檻
            adj_mom = (MOMENTUM_LIMIT * m_adj) * (SCAN_SEC / 60.0)
            elapsed_mins = max(((now.hour - 9) * 60 + now.minute), 1)

            for i in range(0, len(self.all_codes), 100):
                batch = self.all_codes[i:i+100]
                try:
                    snaps = self.api.snapshots(batch)
                    for s in snaps:
                        code = s.code; price = s.close; ref = self.ref_map.get(code, 0)
                        if not code or price <= 0 or ref <= 0: continue
                        
                        # 1. 漲幅與成交量過濾 (昨日量 > 3000)
                        chg = round(((price - ref) / ref * 100), 2)
                        if chg < FILTER_CHG or s.total_volume < MIN_VOL_LIMIT or s.yesterday_volume < YEST_VOL_LIMIT: continue

                        # 2. 預估量過濾
                        est_ratio = round(((float(s.total_volume) / elapsed_mins) * 270) / (float(s.yesterday_volume) if s.yesterday_volume > 0 else 1), 2)
                        if est_ratio < FILTER_EST_VOL: continue

                        # 3. 均價乖離 (VWAP) 過濾
                        vwap = (s.amount / s.total_volume) if s.total_volume > 0 else price
                        vwap_dist = round(((price - vwap) / vwap * 100), 2)
                        if vwap_dist < 0 or vwap_dist > VWAP_GAP_LIMIT: continue

                        # 4. 1 分鐘爆量動能
                        vol_diff = 0; min_vol_pct = 0.0
                        if code in self.last_total_vol_map:
                            vol_diff = s.total_volume - self.last_total_vol_map[code]
                            if vol_diff > 0: min_vol_pct = round((vol_diff / s.total_volume) * 100, 2)
                        self.last_total_vol_map[code] = s.total_volume
                        
                        # 5. 回徹限制
                        daily_high = s.high if s.high > 0 else price
                        if price < daily_high * 0.995 or ((daily_high - price) / daily_high * 100) > RETRACEMENT_LIMIT: continue
                        if (min_vol_pct < adj_mom and vol_diff < 100): continue

                        # 6. Hits 累計
                        self.trigger_history[code] = [t for t in self.trigger_history.get(code, []) if t > now - timedelta(minutes=10)] + [now]
                        hits = len(self.trigger_history[code])
                        
                        if hits >= h_thr and self.market_safe:
                            if not self.reported_log.get(code) or (now - self.reported_log[code] > timedelta(minutes=45)):
                                item = {"時間": now.strftime("%H:%M:%S"), "code": code, "name": self.name_map[code], "price": price, "chg": chg, 
                                        "tp": price*1.025, "sl": price*0.985, "cond": "💎 終極突破", "min_v": min_vol_pct, "vwap_dist": vwap_dist, "hit": hits}
                                self.results.append(item)
                                buf = self.create_card(item)
                                requests.post(DISCORD_URL, data={"content": f"🚀 **精準雷達爆發！**\n🔥 **{code} {item['name']}**\n📈 漲幅: {chg}% | 動能: {min_vol_pct}%"}, files={"file": (f"{code}.png", buf)})
                                self.reported_log[code] = now
                except: continue
            time.sleep(SCAN_SEC)

        # 盤後結算 (新增績效計算)
        if self.results:
            codes = [i['code'] for i in self.results]
            snap_map = {s.code: s.close for s in self.api.snapshots(codes)}
            for i in self.results:
                cp = snap_map.get(i['code'], 0)
                i['收盤價'] = cp
                i['績效%'] = round(((cp - i['price']) / i['price'] * 100), 2) if i['price'] > 0 else 0
            pd.DataFrame(self.results).to_excel(get_daily_filename(), index=False)
        self.api.logout()

if __name__ == "__main__":
    DayTradeWorker().start_monitoring()
