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
2. 按「套用並開始 RUN」會先套用畫面設定再啟動；運轉中可另按「套用設定」。連接與載入情境均不會自動啟動。
3. 觀察轉速、電壓、電流曲線與邏輯訊號、八通道 DAC code。
4. 煞車切斷驅動電流；STOP 清除裝置 PWM、轉速、電流及 DAC code，保留畫面草稿供下次啟動。
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

## 自動驗證流程

「自動驗證」區塊的「執行完整測試」會覆寫裝置設定為 48 V、80 RPM、60 Nm、
PWM 40%、煞車解除，約 13 秒完成以下流程。這些是本專案模型的預期門檻，
不代表真實 TSDZ 電機規格或硬體安全驗證。

| 階段 | 等待 | 判斷 |
|---|---|---|
| 起步 | 5 秒 | 轉速 > 500 RPM、電流 > 0.1 A、電壓 < 47.9 V |
| 15% 爬坡 | 5 秒 | 轉速低於平路 90%、電流高於平路 0.3 A |
| 煞車 | 1.5 秒 | 電流 ≤ 0.01 A、轉速低於爬坡 20% |
| STOP | 命令回報後 | running=false、轉速/電流/PWM=0、八通道 DAC=0 |

前三個階段取最後最多三筆新資料的中位數，每階段至少兩筆採樣。
資料超過 2.5 秒未更新就失敗；開始時也會檢查連線與資料時間。
只允許 fake PWM、logical-only GPIO、mock/disabled DAC；SPI 模式不可執行此流程。

自動測試期間，手動 RUN、調參與斷線會被服務端拒絕；STOP 或「中止測試」可中止。
中止後不會執行後續階段，並再次送 STOP。只有收到停止回報且確認歸零，
報告才會標示 `stop_confirmed=true`。USB 斷線導致無法確認停止時，結果為 FAIL。
結束或中止均清除裝置 PWM 並嘗試解除煞車；不會恢復測試前的參數。

畫面顯示步驟、PASS/FAIL、條件及實測值。完成後可下載完整 JSON，包含參數、
所有採樣、各階段結果與停止確認。報告也會保存於本機 `pc/reports/`（不加入 Git）。
畫面的最新報告只保留在目前服務記憶體，服務重啟後可到該資料夾讀取歷史 JSON。
若磁碟寫入失敗，畫面會提示下載保留；模型測試結果與報告儲存狀態分開記錄。

新增 API：

- `POST /api/test/start`，JSON `{}`：啟動固定流程。
- `POST /api/test/cancel`，JSON `{}`：中止並送出 STOP。
- `GET /api/test/report`：最新完整報告（無報告時為 404）。
- `GET /api/state` 的 `test` 欄位：進度、結果與採樣數，不含完整採樣陣列。

完整 PC 測試：`python -m unittest discover -s pc -p 'test_*.py'`。

## 電壓 / PWM / 坡度掃描

掃描可使用目前板上的 protocol 1 韌體，不需重新燒錄。
預設 36/48/52 V × PWM 20/40/60% × 坡度 0/15%，共 18 點，每點 5 秒。
踏頻固定 80 RPM、扭力 60 Nm、煞車解除。每點先 STOP，套用條件後 RUN，
使用最後最多三筆新資料的中位數，避免前一點的殘留轉速影響下一點。
這是固定秒數的響應比較，**不宣稱穩態**。UI 上顯示的是 ESP32 計算模型，
不是電機實測或 TSDZ 規格。

可修改逗號分隔清單：電壓 12–60 V、PWM 0–100%、坡度 -30–30%；每軸 1–6 值、
不得重複，每次總點數上限 36。每點時間 2–15 秒。服務端先驗證完整計畫，
拒絕無效輸入後才允許任何裝置操作。規劃按坡度、電壓、PWM 由小到大執行。

每點檢查裝置回報的設定、running/煞車狀態與有效數值，PWM>0 必須有可觀測轉速，
PWM=0 必須零轉速。結束再分組檢查轉速對 PWM、電壓和坡度的方向反應：

- 相鄰點容許反向偏差 max(5 RPM, 前一點轉速的 5%)，吸收採樣時間差。
- PWM 跨度 ≥5%、電壓跨度 ≥2 V、坡度跨度 ≥5% 時，端點必須呈預期方向，
  且差值大於 max(0.1 RPM, 起點轉速的 1%)。
- PWM=0 時，不要求電壓/坡度造成轉速變化。
- 預設掃描共 21 組趨勢判斷；只給單點時無法比較趨勢，畫面會明示。

比較圖以 PWM 為橫軸、電壓為不同顏色，可切換坡度，分別顯示轉速、電流與電池端電壓。
表格列出已完成測點，尚未量測的點不補值。CSV 只匯出測點摘要；完整 JSON
包含所有採樣、設定計畫、趨勢判斷與停止確認。中止或失敗的報告保留部分結果。
最新標準測試或掃描共用報告欄位；啟動另一種測試會取代記憶體中的最新報告，
已完成報告仍保存在 `pc/reports/`。

API：`POST /api/test/start`，JSON 範例：

```json
{"kind":"sweep","sweep":{"voltages":[36,48,52],"pwms":[20,40,60],"grades":[0,15],"hold_s":5}}
```

原有 `{}` 或 `{"kind":"sequence"}` 仍執行約 13 秒的標準測試。
`GET /api/test/points.csv` 匯出最新掃描摘要；不是掃描報告時回傳 404。
`POST /api/test/cancel` 與 STOP 沿用原本中止、歸零確認與排他控制。
