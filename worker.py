import shioaji as sj
import pandas as pd
import time
import requests
import os
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont
import io

# 設定區 (GitHub Actions 會透過環境變數傳入)
API_KEY = "5FhL23V9b4zhqK6yMnMK3SdvCAnCdHAtrESypTGprqRz"
SECRET_KEY = "HV8yi9TPBEpyTYxNFyLyEB9tiEjnWpNZeNLcVyf4WRw"
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/917970232084152411/kkkoyrfBEpN-UVEqweE0iNtpuUFjK4UAc7UKQWaJmio6rT5FJ1TukrE2xARYEZyeuKrQ"

class TradingWorker:
    def __init__(self):
        self.api = sj.Shioaji()
        self.trigger_history = {}
        self.reported_log = {}

    def login(self):
        self.api.login(API_KEY, SECRET_KEY)
        raw = [c for m in [self.api.Contracts.Stocks.TSE, self.api.Contracts.Stocks.OTC] for c in m if len(c.code) == 4]
        self.ref_map = {c.code: float(c.reference) for c in raw if c.reference}
        self.name_map = {c.code: c.name for c in raw}
        self.all_contracts = [c for c in raw if c.code in self.ref_map]

    def create_card(self, item):
        img = Image.new('RGB', (600, 400), color=(18, 19, 23))
        draw = ImageDraw.Draw(img)
        draw.rectangle([0, 0, 15, 400], fill=(255, 60, 60))
        # 繪圖邏輯同前... (省略重複繪圖代碼以簡潔)
        buf = io.BytesIO(); img.save(buf, format='PNG'); buf.seek(0)
        return buf

    def run(self):
        self.login()
        print("🚀 監控啟動...")
        while True:
            now = datetime.now()
            hm = now.hour * 100 + now.minute
            
            # 自動停止時間：13:40
            if hm > 1340: 
                print("🏁 交易時段結束，腳本停止。")
                break
                
            # 核心掃描邏輯 (100檔一組抓快照)
            for i in range(0, len(self.all_contracts), 100):
                snaps = self.api.snapshots(self.all_contracts[i:i+100])
                for s in snaps:
                    # ... 你的判斷邏輯 (漲幅 > 3%, 爆量等) ...
                    # 符合條件則 requests.post(WEBHOOK, ...)
                    pass
            
            time.sleep(12)

if __name__ == "__main__":
    worker = TradingWorker()
    worker.run()