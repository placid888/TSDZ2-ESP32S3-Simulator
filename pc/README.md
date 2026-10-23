# PC Virtual Bench 控制台

本機瀏覽器介面 + Python 串口橋接 + 實體 ESP32-S3 模型。
畫面數據一律來自 ESP32 `TELEMETRY`，PC 不產生替代模擬值。

## 啟動

Windows：雙擊 `pc/start.cmd`；會在本機啟動服務並開啟瀏覽器。
也可執行 `pc/start.ps1`。
它優先尋找專案的 `.venv` 及本機既有 Espressif Python 環境。
也可以使用 `./pc/start.ps1 -Python '完整的 python.exe 路徑'`。

其他環境或手動啟動：

```sh
python -m venv pc/.venv
# 啟用此環境後：
python -m pip install -r pc/requirements.txt
python pc/server.py
```

開啟 http://127.0.0.1:8765 。選擇 COM5 等裝置串口，按「連接裝置」。
板子必須燒入支援 protocol 1 `TELEMETRY` 的 Bench 韌體。
USB-UART（CH343）使用 `sdkconfig.bench-uart`，115200 baud。

1. 選擇平路、爬坡或空載情境，或自行修改參數。
2. 按「套用設定」再按 RUN。連接與載入情境均不會自動啟動。
3. 觀察轉速、電壓、電流曲線與邏輯訊號、八通道 DAC code。
4. 煞車切斷驅動電流；STOP 清除 PWM、轉速、電流及 DAC code。
5. 匯出 CSV 可保留目前連線最近約五分鐘的資料（記憶體環形緩衝）。
6. 中斷連線會先送 STOP，確認結果顯示於紀錄。

關閉瀏覽器頁面不會自動停止 ESP32；結束測試請按 STOP 或中斷連線。
USB 實體斷線時無法確認裝置已停止；這不是硬體緊急停止機制。
模型仍為 fake PWM、邏輯 GPIO 與 DAC mock；沒有接入真實 STM8。

## 自動化介面

- `GET /api/ports`：可用串口。
- `GET /api/state`：連線、資料時間、最新 telemetry、曲線資料與紀錄。
- `POST /api/connect`，JSON `{"port":"COM5"}`。
- `POST /api/settings`，JSON `{"settings":{"PWM":40,"CADENCE":80}}`。
- `POST /api/command`，JSON `{"command":"RUN"}` 或 STOP。
- `POST /api/disconnect`，JSON `{}`。
- `GET /api/export.csv`：目前資料 CSV。

服務只綁定 127.0.0.1；沒有遠端控制或雲端依賴。
數值範圍於 PC 與韌體各自檢查；串口命令與輪詢透過鎖依序處理。
每 250 ms 輪詢，頁面每 500 ms 更新；逾期禁用 RUN，保留 STOP。
批次設定先整批驗證；裝置中途回報失敗時嘗試 STOP，不宣稱設定已全部生效。

測試：`python -m unittest discover -s pc -p test_server.py`。
串口 API 參照 [pySerial 官方文件](https://pyserial.readthedocs.io/en/latest/pyserial_api.html)。
