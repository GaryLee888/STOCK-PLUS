import shioaji as sj
import pandas as pd
import time
import requests
import os
import io
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont

# ==========================================
# 1. 系統設定
# ==========================================
API_KEY = os.getenv("5FhL23V9b4zhqK6yMnMK3SdvCAnCdHAtrESypTGprqRz")
SECRET_KEY = os.getenv("HV8yi9TPBEpyTYxNFyLyEB9tiEjnWpNZeNLcVyf4WRw")
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
        self.results = [] # 用於存儲當日成交紀錄

    def login_and_prepare(self):
        print(f"[{datetime.now()}] 正在登入 Shioaji...")
        self.api.login(API_KEY, SECRET_KEY)
        raw = [c for m in [self.api.Contracts.Stocks.TSE, self.api.Contracts.Stocks.OTC] 
               for c in m if len(c.code) == 4 and "處置" not in c.name]
        for c in raw:
            if c.reference:
                self.ref_map[c.code] = float(c.reference)
                self.name_map[c.code] = c.name
                self.cat_map[c.code] = c.category
        self.all_codes = [c for c in raw if c.code in self.ref_map]

    def create_card(self, item):
        font_p = "msjhbd.ttc" if os.path.exists("msjhbd.ttc") else None
        try:
            f_title = ImageFont.truetype(font_p, 44) if font_p else ImageFont.load_default()
            f_price = ImageFont.truetype(font_p, 70) if font_p else ImageFont.load_default()
            f_info = ImageFont.truetype(font_p, 26) if font_p else ImageFont.load_default()
        except:
            f_title = f_price = f_info = ImageFont.load_default()

        img = Image.new('RGB', (600, 400), color=(18, 19, 23))
        draw = ImageDraw.Draw(img)
        draw.rectangle([0, 0, 15, 400], fill=(255, 60, 60))
        draw.text((40, 60), f"{item['code']} {item['name']}", fill=(255, 255, 255), font=f_title)
        draw.text((40, 130), f"現價: {item['price']}", fill=(255, 60, 60), font=f_price)
        draw.text((40, 240), f"漲幅: {item['chg']}%  目標: {item['tp']}", fill=(255, 215, 0), font=f_info)
        draw.text((40, 280), f"策略: {item['cond']}", fill=(200, 200, 200), font=f_info)
        buf = io.BytesIO(); img.save(buf, format='PNG'); buf.seek(0)
        return buf

    def start_monitoring(self):
        self.login_and_prepare()
        while True:
            now = datetime.now()
            hm = now.hour * 100 + now.minute
            if hm > 1345: break # 13:45 自動關閉並進入存檔
            
            h_thr = 15 if hm < 1000 else 10
            for i in range(0, len(self.all_codes), 100):
                batch = self.all_codes[i:i+100]
                try:
                    snaps = self.api.snapshots(batch)
                    elapsed = max(((now.hour - 9) * 60 + now.minute), 1)
                    for s in snaps:
                        code = s.code
                        if s.close <= 0: continue
                        ref = self.ref_map[code]
                        chg = round((s.close - ref) / ref * 100, 2)
                        if chg < 3.0 or s.total_volume < 2000: continue
                        
                        est_v = round(((s.total_volume / elapsed) * 270) / (s.yesterday_volume if s.yesterday_volume > 0 else 1), 2)
                        if est_v < 1.5: continue
                        
                        self.trigger_history[code] = [t for t in self.trigger_history.get(code, []) if t > now - timedelta(minutes=10)] + [now]
                        if len(self.trigger_history[code]) >= h_thr:
                            if not self.reported_log.get(code) or (now - self.reported_log[code] > timedelta(minutes=45)):
                                item = {"時間": now.strftime("%H:%M:%S"), "code": code, "name": self.name_map[code], "price": s.close, "chg": chg, "tp": round(s.close * 1.025, 2), "cond": "強勢突破"}
                                # 加入 Excel 列表
                                self.results.append(item)
                                # Discord 發報
                                buf = self.create_card(item)
                                requests.post(DISCORD_URL, data={"content": f"🚀 {code} {item['name']} 觸發!"}, files={"file": ("alert.png", buf)})
                                self.reported_log[code] = now
                except: continue
            time.sleep(15)

        # 存檔邏輯
        if self.results:
            df = pd.DataFrame(self.results)
            df.to_excel(get_daily_filename(), index=False)
            print(f"報表已產出: {get_daily_filename()}")

if __name__ == "__main__":
    DayTradeWorker().start_monitoring()

