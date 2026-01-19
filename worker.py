import shioaji as sj
import pandas as pd
import time
import requests
import os
import io
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont

# ==========================================
# 1. 系統設定 (由 GitHub Secrets 注入)
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
        self.results = [] 

    def login_and_prepare(self):
        print(f"[{datetime.now()}] 正在登入 Shioaji...")
        if not API_KEY or not SECRET_KEY:
            print("❌ 錯誤：找不到 API_KEY 或 SECRET_KEY，請檢查 GitHub Secrets！")
            return False
        try:
            self.api.login(API_KEY.strip(), SECRET_KEY.strip())
            print("✅ Shioaji 登入成功！")
            
            # 發送啟動成功訊息
            try:
                requests.post(DISCORD_URL, data={"content": f"🔔 **當沖雷達啟動成功**\n時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n狀態: 🟢 雲端監控已就緒。"}, timeout=10)
            except: pass
            
            raw = [c for m in [self.api.Contracts.Stocks.TSE, self.api.Contracts.Stocks.OTC] 
                   for c in m if len(c.code) == 4 and "處置" not in c.name]
            for c in raw:
                if c.reference:
                    self.ref_map[c.code] = float(c.reference)
                    self.name_map[c.code] = c.name
            self.all_codes = [c for c in raw if c.code in self.ref_map]
            print(f"成功載入 {len(self.all_codes)} 檔標的。")
            return True
        except Exception as e:
            print(f"❌ 登入失敗: {e}")
            return False

    def create_card(self, item):
        # --- 關鍵：Linux 系統字體搜尋路徑 ---
        potential_fonts = [
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", # .yml 安裝的中文字體
            "msjhbd.ttc",                                    # 你上傳的檔案
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" # Linux 內建英文字體
        ]
        
        f_title = f_price = f_info = f_small = None
        for font_path in potential_fonts:
            try:
                if os.path.exists(font_path):
                    f_title = ImageFont.truetype(font_path, 44)
                    f_price = ImageFont.truetype(font_path, 70)
                    f_info = ImageFont.truetype(font_path, 26)
                    f_small = ImageFont.truetype(font_path, 18)
                    break
            except: continue
        
        if f_title is None:
            f_title = f_price = f_info = f_small = ImageFont.load_default()

        # 開始繪製圖片
        img = Image.new('RGB', (600, 400), color=(18, 19, 23))
        draw = ImageDraw.Draw(img)
        draw.rectangle([0, 0, 15, 400], fill=(255, 60, 60)) # 左側裝飾
        draw.rectangle([15, 0, 600, 45], fill=(255, 215, 0)) # 上方黃條
        
        draw.text((40, 8), "🚀 財神降臨！發財電報", fill=(0, 0, 0), font=f_info)
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
        if not self.login_and_prepare(): return

        print("⚡ 開始市場監控...")
        while True:
            now = datetime.now()
            hm = now.hour * 100 + now.minute

            # 收盤與自動測試判斷
            if hm < 850 or hm > 1345:
                # 測試模式：若非交易時段，發送一則測試通知確認功能
                if not self.results: # 避免重複發送
                    print("🛠 非交易時段，執行發報測試...")
                    test_item = {"時間": now.strftime("%H:%M:%S"), "code": "2330", "name": "台積電測試", "price": 1000.0, "chg": 5.0, "tp": 1025.0, "sl": 985.0, "cond": "測試中"}
                    buf = self.create_card(test_item)
                    requests.post(DISCORD_URL, data={"content": "📢 **功能測試**：圖片與中文字體顯示正常！"}, files={"file": ("test.png", buf)})
                    # 產生一個空報表避免 GitHub Artifacts 報錯
                    pd.DataFrame([test_item]).to_excel(get_daily_filename(), index=False)
                break
            
            # 正式盤中掃描邏輯
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
                                item = {"時間": now.strftime("%H:%M:%S"), "code": code, "name": self.name_map[code], "price": s.close, "chg": chg, "tp": s.close*1.025, "sl": s.close*0.985, "cond": "💎 強勢突破"}
                                self.results.append(item)
                                buf = self.create_card(item)
                                requests.post(DISCORD_URL, data={"content": f"🚀 {code} {item['name']} 爆發！"}, files={"file": (f"{code}.png", buf)})
                                self.reported_log[code] = now
                except: continue
            time.sleep(15)

        # 最終存檔
        if self.results:
            pd.DataFrame(self.results).to_excel(get_daily_filename(), index=False)

if __name__ == "__main__":
    DayTradeWorker().start_monitoring()
