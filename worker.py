import shioaji as sj
import pandas as pd
import time
import requests
import os
import io
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont

# ==========================================
# 1. 系統設定 (從 GitHub Secrets 讀取)
# ==========================================
API_KEY = os.getenv("API_KEY")
SECRET_KEY = os.getenv("SECRET_KEY")
DISCORD_URL = "https://discord.com/api/webhooks/1457393304537927764/D2vpM73dMl2Z-bLfI0Us52eGdCQyjztASwkBP3RzyF2jaALzEeaigajpXQfzsgLdyzw4"

class DayTradeWorker:
    def __init__(self):
        self.api = sj.Shioaji()
        self.trigger_history = {}
        self.reported_log = {}
        self.last_vol_map = {}
        self.name_map = {}
        self.ref_map = {}
        self.cat_map = {}
        
    def login_and_prepare(self):
        print(f"[{datetime.now()}] 正在登入 Shioaji...")
        self.api.login(API_KEY, SECRET_KEY)
        # 抓取全市場股票合約
        raw = [c for m in [self.api.Contracts.Stocks.TSE, self.api.Contracts.Stocks.OTC] 
               for c in m if len(c.code) == 4 and "處置" not in c.name]
        for c in raw:
            if c.reference:
                self.ref_map[c.code] = float(c.reference)
                self.name_map[c.code] = c.name
                self.cat_map[c.code] = c.category
        self.all_codes = [c for c in raw if c.code in self.ref_map]
        print(f"成功載入 {len(self.all_codes)} 檔標的。")

    def create_card(self, item):
        # GitHub Actions 環境下需確保專案內有 msjhbd.ttc 檔案
        font_p = "msjhbd.ttc" if os.path.exists("msjhbd.ttc") else None
        try:
            f_title = ImageFont.truetype(font_p, 44) if font_p else ImageFont.load_default()
            f_price = ImageFont.truetype(font_p, 70) if font_p else ImageFont.load_default()
            f_info = ImageFont.truetype(font_p, 26) if font_p else ImageFont.load_default()
        except:
            f_title = f_price = f_info = ImageFont.load_default()

        img = Image.new('RGB', (600, 400), color=(18, 19, 23))
        draw = ImageDraw.Draw(img)
        draw.rectangle([0, 0, 15, 400], fill=(255, 60, 60)) # 側邊紅條
        draw.text((40, 60), f"{item['code']} {item['name']}", fill=(255, 255, 255), font=f_title)
        draw.text((40, 130), f"現價: {item['price']}", fill=(255, 60, 60), font=f_price)
        draw.text((40, 240), f"漲幅: {item['chg']}%  目標: {item['tp']}", fill=(255, 215, 0), font=f_info)
        draw.text((40, 280), f"策略: {item['cond']}", fill=(200, 200, 200), font=f_info)
        
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        return buf

    def start_monitoring(self):
        self.login_and_prepare()
        print("⚡ 進入監控循環...")
        
        while True:
            now = datetime.now()
            hm = now.hour * 100 + now.minute
            
            # 設定自動結束時間 (13:45)
            if hm > 1345:
                print("收盤時間已到，停止執行。")
                break
            
            # 判斷時間權重 (仿原程式邏輯)
            if hm < 1000: h_thr = 15
            elif hm < 1130: h_thr = 10
            else: h_thr = 18

            # 分批處理 Snapshot (每批100檔避免逾時)
            for i in range(0, len(self.all_codes), 100):
                batch = self.all_codes[i:i+100]
                try:
                    snaps = self.api.snapshots(batch)
                    elapsed = max(((now.hour - 9) * 60 + now.minute), 1)
                    
                    for s in snaps:
                        code = s.code
                        if s.close <= 0 or code not in self.ref_map: continue
                        
                        ref = self.ref_map[code]
                        chg = round((s.close - ref) / ref * 100, 2)
                        
                        # 核心過濾條件
                        if chg < 3.0 or s.total_volume < 2000: continue
                        
                        # 預估量倍數
                        est_v = round(((s.total_volume / elapsed) * 270) / (s.yesterday_volume if s.yesterday_volume > 0 else 1), 2)
                        if est_v < 1.5: continue
                        
                        # 觸發次數計算
                        self.trigger_history[code] = [t for t in self.trigger_history.get(code, []) if t > now - timedelta(minutes=10)] + [now]
                        hits = len(self.trigger_history[code])
                        
                        # 符合發報門檻
                        if hits >= h_thr:
                            last_r = self.reported_log.get(code)
                            if not last_r or (now - last_r > timedelta(minutes=45)):
                                item = {
                                    "code": code, "name": self.name_map[code], "price": s.close,
                                    "chg": chg, "tp": round(s.close * 1.025, 2), "sl": round(s.close * 0.985, 2),
                                    "cond": "💎 精準強勢突破", "hit": hits
                                }
                                # 發送 Discord
                                buf = self.create_card(item)
                                content = f"🚀 **發財電報**\n🔥 **{item['code']} {item['name']}**\n📈 漲幅: {item['chg']}% | 預估量: {est_v}x"
                                requests.post(DISCORD_URL, data={"content": content}, files={"file": ("alert.png", buf)}, timeout=10)
                                self.reported_log[code] = now
                                print(f"已通報: {code} {item['name']}")
                except:
                    continue
            
            time.sleep(12) # 掃頻間隔

if __name__ == "__main__":
    worker = DayTradeWorker()
    worker.run = worker.start_monitoring()
