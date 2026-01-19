import shioaji as sj
import pandas as pd
import time
import requests
import os
import io
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont

# ==========================================
# 1. 系統設定 (由 GitHub Secrets 自動注入)
# ==========================================
API_KEY = os.getenv("API_KEY")
SECRET_KEY = os.getenv("SECRET_KEY")
DISCORD_URL = "https://discord.com/api/webhooks/1457393304537927764/D2vpM73dMl2Z-bLfI0Us52eGdCQyjztASwkBP3RzyF2jaALzEeaigajpXQfzsgLdyzw4"

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
        self.results = [] 

    def login_and_prepare(self):
        print(f"[{datetime.now()}] 正在登入 Shioaji...")
        if not API_KEY or not SECRET_KEY:
            print("❌ 錯誤：找不到 API_KEY 或 SECRET_KEY，請檢查 GitHub Secrets！")
            return False

        try:
            self.api.login(API_KEY.strip(), SECRET_KEY.strip())
            print("✅ Shioaji 登入成功！")
            
            # --- 啟動連線測試通知 ---
            try:
                requests.post(DISCORD_URL, data={"content": f"🔔 **當沖雷達啟動通知**\n時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n狀態: 🟢 雲端監控已就緒，明天準時開盤！"}, timeout=10)
            except:
                print("⚠️ Discord 通知發送失敗，請檢查 Webhook 網址")
            
            raw = [c for m in [self.api.Contracts.Stocks.TSE, self.api.Contracts.Stocks.OTC] 
                   for c in m if len(c.code) == 4 and "處置" not in c.name]
            for c in raw:
                if c.reference:
                    self.ref_map[c.code] = float(c.reference)
                    self.name_map[c.code] = c.name
                    self.cat_map[c.code] = c.category
            self.all_codes = [c for c in raw if c.code in self.ref_map]
            print(f"成功載入 {len(self.all_codes)} 檔標的。")
            return True
        except Exception as e:
            print(f"❌ 登入失敗: {e}")
            return False

    def create_card(self, item):
        # --- 字體讀取防呆機制 ---
        font_p = "msjhbd.ttc"
        try:
            if os.path.exists(font_p):
                f_title = ImageFont.truetype(font_p, 44)
                f_price = ImageFont.truetype(font_p, 70)
                f_info = ImageFont.truetype(font_p, 26)
                f_small = ImageFont.truetype(font_p, 18)
            else:
                print(f"⚠️ 找不到字體檔 {font_p}，改用系統預設字體")
                f_title = f_price = f_info = f_small = ImageFont.load_default()
        except:
            f_title = f_price = f_info = f_small = ImageFont.load_default()

        img = Image.new('RGB', (600, 400), color=(18, 19, 23))
        draw = ImageDraw.Draw(img)
        # 繪圖區
        draw.rectangle([0, 0, 15, 400], fill=(255, 60, 60))
        draw.rectangle([15, 0, 600, 45], fill=(255, 215, 0))
        draw.text((40, 8), "🚀 財神降臨！發財電報 💰💰💰", fill=(0, 0, 0), font=f_info)
        draw.text((40, 65), f"{item['code']} {item['name']}", fill=(255, 255, 255), font=f_title)
        draw.text((40, 130), f"{item['price']}", fill=(255, 60, 60), font=f_price)
        draw.text((320, 160), f"漲幅 {item['chg']}%", fill=(255, 60, 60), font=f_info)
        draw.text((40, 240), f"目標停利：{item['tp']:.2f}", fill=(255, 60, 60), font=f_info)
        draw.text((310, 240), f"建議停損：{item['sl']:.2f}", fill=(0, 200, 0), font=f_info)
        draw.text((40, 362), f"訊號: {item['cond']} | 時間: {item['時間']}", fill=(255, 215, 0), font=f_small)
        
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        return buf

    def start_monitoring(self):
        if not self.login_and_prepare():
            return

        print("⚡ 開始市場監控...")
        while True:
            now = datetime.now()
            hm = now.hour * 100 + now.minute
            
            # 收盤停止時間 (13:45)
            if hm > 1345:
                print("🏁 收盤時間到，準備產出報表並結束任務。")
                break
            
            # 動態門檻
            h_thr = 15 if hm < 1000 else 10 if hm < 1130 else 18

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
                        
                        if chg < 3.0 or s.total_volume < 2000: continue
                        
                        est_v = round(((s.total_volume / elapsed) * 270) / (s.yesterday_volume if s.yesterday_volume > 0 else 1), 2)
                        if est_v < 1.5: continue
                        
                        self.trigger_history[code] = [t for t in self.trigger_history.get(code, []) if t > now - timedelta(minutes=10)] + [now]
                        if len(self.trigger_history[code]) >= h_thr:
                            if not self.reported_log.get(code) or (now - self.reported_log[code] > timedelta(minutes=45)):
                                item = {
                                    "時間": now.strftime("%H:%M:%S"), "code": code, "name": self.name_map[code], 
                                    "price": s.close, "chg": chg, "tp": round(s.close * 1.025, 2), 
                                    "sl": round(s.close * 0.985, 2), "cond": "💎 強勢突破"
                                }
                                self.results.append(item)
                                # 發報
                                buf = self.create_card(item)
                                content = f"🚀 **發財電報**\n🔥 **{item['code']} {item['name']}** 爆發！\n📈 漲幅: {item['chg']}% | 預估量: {est_v}x"
                                requests.post(DISCORD_URL, data={"content": content}, files={"file": (f"{code}.png", buf)}, timeout=10)
                                self.reported_log[code] = now
                                print(f"通報成功: {code} {item['name']}")
                except:
                    continue
            
            time.sleep(15) 

        # 收盤存檔
        if self.results:
            df = pd.DataFrame(self.results)
            df.to_excel(get_daily_filename(), index=False)
            print(f"報表已產出: {get_daily_filename()}")

if __name__ == "__main__":
    worker = DayTradeWorker()
    worker.start_monitoring()
