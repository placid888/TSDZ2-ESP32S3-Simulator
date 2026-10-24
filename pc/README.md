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

## 模型故障注入（fault-v1）

需燒入回報 `fault_api:1` 的新韌體。protocol 1 保持不變，新增欄位為向後相容擴充；
PC 連舊版韌體時會停用故障操作，標準操作與掃描仍可使用。

| 故障 | 模型作用 | 保留的設定 |
|---|---|---|
| PAS_LOSS | 有效踏頻與 PAS 頻率歸零 | 原踏頻 |
| TORQUE_ZERO | 有效扭力與 mock CH2 歸零 | 原扭力 |
| BRAKE_STUCK | 有效煞車強制啟用，驅動電流歸零並減速 | 原煞車設定 |
| NONE | 解除模型故障，恢復有效輸入 | 全部設定 |

一次一種故障。手動注入不會自動 RUN；解除故障時若模型仍運轉且 PWM>0，
會依保留設定恢復反應。STOP 會清除故障、PWM、轉速、電流與 DAC code。
踏頻/扭力中斷不會自行切斷 fake PWM，因為此模型還沒有接入真實 STM8 的助力邏輯。
這是測試感測器刺激，**不代表已驗證實車故障保護**，沒有新增 STM8 故障碼。

「故障與恢復測試」固定 48 V、80 RPM、60 Nm、坡度 0、PWM 40%、煞車解除，
會自動啟動並驗證八項：正常基準、PAS 中斷/恢復、扭力歸零/恢復、
煞車卡住/恢復、停止與清除故障。約 11 秒完成；結束後保持停止與 NONE。
支援既有中止、資料逾期檢查、報告 JSON、完整採樣與排他控制。
手動故障注入在任何自動測試期間會被拒絕，請使用 STOP 或中止。

API：`POST /api/fault`，JSON `{"fault":"PAS_LOSS"}`（其他值見表格）；
`POST /api/test/start`，JSON `{"kind":"faults"}` 啟動八項測試。
CSV 新增 fault、effective_cadence_rpm、effective_torque_nm、effective_brake 欄位。
既有 cadence_rpm、torque_nm、brake 仍表示原設定，UI 同時顯示有效輸入。

## DAC 到貨前的通道檢視

每通道顯示 ESP32 回傳的 16-bit code、比例條與理想電壓。換算使用 `2.5 × gain × code / 65536`；gain 1 對應 A/B，gain 2 對應 C/D。預設 gain 2 是預覽假設，必須核對到貨完整型號。選項只影響 PC 顯示，不送出控制命令、不代表實測電壓，也不是 TSDZ 感測器校正。

資料過期時標示舊資料。STOP 後八通道歸零。比例模型仍是 CH1 40 A、CH2 200 Nm、CH3 60 V；CH4–8 保持零。SPI 目前仍為 zero-only。

依據：[TI DAC8568 datasheet](https://www.ti.com/lit/ds/symlink/dac8568.pdf)。硬體到貨後先記錄完整型號、供電與參考電壓，再量測零點、中點、滿量程附近；尚不填入 STM8 pin mapping。

## 歷史報告

控制台下方可重新讀取 `pc/reports/` 已保存報告，按時間由新到舊列出，選擇後顯示 PASS/FAIL/CANCELLED、停止確認、各檢查與掃描測點，並可下載原始 JSON。檢視不會執行測試或改變 ESP32 設定，服務重啟後仍可查閱。新測試完成後按「重新讀取報告」。

`GET /api/reports` 列出報告摘要；`GET /api/reports/<id>` 讀取完整報告。只接受程式產生的時間戳記檔名、schema 1 與已結束的狀態，拒絕路徑跳脫、符號連結、超過 5 MB 或無效 JSON；清單顯示略過的檔案數。報告仍留在本機並由 Git 忽略。
## 連續循環測試

控制台可指定 1–20 次（預設 5 次），每次沿用標準起步、爬坡、煞車、停止流程，約 12 秒。每次先 STOP，套用 48 V / 80 RPM / 60 Nm / PWM 40% / GRADE 0 / BRAKE 0，再 RUN；每次有四項檢查。任一失敗立即終止後續循環並執行 STOP 清理，中止同樣不會重新啟動下一次。

POST `/api/test/start` 範例：`{"kind":"endurance","cycles":3}`。cycles 必須是整數，拒絕布林、小數、字串與超限值。報告含 total_cycles、current_cycle、completed_cycles、total_checks，逐項結果與採樣步驟附循環編號。只有四項檢查都通過才計入已完成次數；最終是否成功仍以 status 與 stop_confirmed 為準。

完成後按「重新讀取報告」可找回整次測試。此功能只驗證 ESP32 模型反覆運轉，並非實體電機、DAC 或 STM8 的長時間耐久測試。
## 通訊保護

新韌體在運轉中超過 5 秒沒有有效指令會自動停止，並清除 PWM、故障與 DAC 碼。控制台顯示本次開機的觸發次數與停止原因。PC 服務的定期查詢維持通訊；關閉網頁仍須按 STOP。逾時後重新連線不會自動 RUN，請確認狀態再套用設定並手動開始。
## 測試版本紀錄

控制台顯示 ESP32 韌體版本、IDF 版本、ELF 指紋前 12 碼與 PC 程式指紋。PC 啟動時以本機 Python 原始碼及 web 檔案內容計算 SHA-256（不含測試檔案）；代表服務啟動時來源，修改檔案後應重啟服務。它不等同 Git commit。

每份新報告的 provenance 保存測試開始時的 firmware 與 pc 完整資訊（含完整指紋及 Python 版本）。歷史報告顯示來源；舊報告缺少時標示未記錄，不推測版本。韌體 INFO 的 elf_sha256 是 ELF 的指紋，不是 .bin 檔案雜湊。
## 兩份報告比較

先在歷史報告選擇比較對象，再於「兩份報告比較」選基準。只允許兩份不同、已通過且確認停止的完整報告；測試種類、參數、掃描計畫、循環次數、範圍、步驟名稱與判斷條件必須相同。

每步列出 rpm、current_a、battery_v 的基準值、對象值及差值（對象減基準），可下載比較 JSON。顯示兩邊已記錄的版本，舊報告未知版本仍標示未記錄。數值是固定等待時間後採樣，差異含採樣時序影響；未配置容許值，因此不新增 PASS/FAIL 判定。比較不會操作串口或修改原始報告。

API：`GET /api/compare?baseline=<報告檔名>&candidate=<報告檔名>`；條件不符回傳 400，找不到檔案回傳 404。

窄畫面（640 px 以下）會將比較表改為卡片，每筆直接顯示「基準、比較對象、差值」，不需左右捲動；較寬畫面維持表格。
## 完整測試包 ZIP

歷史報告選取後可按「下載完整測試包 ZIP」，或呼叫 `GET /api/bundle/<報告檔名>`。封裝 report.json、samples.csv、steps.csv、points.csv、provenance.json、README.txt 與 SHA256SUMS.txt；只含選取報告的已保存資料，不操作串口、不重新採樣。

CSV 為 UTF-8 BOM，巢狀欄位以 JSON 文字保存；以 =、+、-、@ 開始的文字加單引號，數字保持原值。完整原值仍在 report.json。舊報告未記錄的版本為 null，無採樣時 CSV 為空表。SHA256SUMS.txt 列出其餘六個檔案的 SHA-256，供解壓後檢查完整性。
## 裝置管理中心（統一控制台第一階段）

`GET /api/devices` 僅列舉 PC 串口與工具是否在 PATH，不會開啟串口、送指令、啟動 ADB 或燒錄。支援 motor、gateway、author_board 三個串口角色；原作者 ESP32 板的用途仍待確認。STM8/ST-Link 與 Android 保留獨立接入位置，不把沒有串口當作未插入除錯器或手機的證據。

`POST /api/devices/assign` 使用 `{"role":"motor","port":"COM5"}` 保存目前選定裝置；同一個裝置不能登記為兩個角色。`POST /api/devices/clear` 使用 `{"role":"motor"}` 解除角色，保持現有連線不變。自動測試中不允許改角色。連接模擬器時，若該裝置已登記為 Gateway 或原作者板，會拒絕從模擬器入口連接。

本機設定為 `pc/local/devices.json`，不加入 Git。識別以 VID/PID/USB 序號為主，可追蹤 COM 編號變動；沒有序號時只能以目前串口與硬體描述登記，介面明示換接孔後須核對。識別重複顯示歧義並拒絕新登記。損壞的設定不自動覆寫。

這一階段不包含 STM8/Gateway 燒錄、未知協定、ADB 操作或跨裝置流程；後續將以獨立模組接入。角色登記只是人工指定用途，不等於已驗證設備韌體。
## 自訂騎乘流程

控制台可編排 1–12 個連續路段、調整順序及刪除。共用電壓 12–60 V、踏頻/扭力 0–200；各步可指定名稱、持續 2–30 秒、PWM 0–100%、坡度 -30–30%、煞車狀態；總持續時間上限 180 秒，另加指令與停止時間。

`POST /api/test/start` 使用 `{"kind":"ride","ride":{...}}`。計畫須含 battery_v、cadence_rpm、torque_nm、steps，步驟須含 name、seconds、pwm_percent、grade_percent、brake（布林）。整份計畫驗證後才接觸裝置；拒絕未知欄位、非有限值、布林冒充數值與超限設定。請求大小上限 16 KiB。

流程先 STOP 並重設初始條件，第一步 RUN，後續步驟連續套用設定。各步使用新鮮採樣、檢查設定回報與數據範圍，煞車時檢查電流歸零；不將此結果當作實車性能驗證。結尾與失敗/中止均沿用 STOP 清理，報告保存完整 plan 與各步實測值、版本資料。相同計畫的兩份成功報告可比較。

`GET /api/ride-plan` 讀取 PC 保存的計畫（尚未保存時提供預設）；`POST /api/ride-plan` 使用 `{"plan":{...}}` 保存至 `pc/local/ride_plan.json`。保存/載入不送裝置指令；自動測試執行中禁止保存。第一版保存一份 PC 共用計畫，另可由歷史報告與 ZIP 保留完整舊計畫。流程內故障刺激與多裝置步驟尚未加入，既有故障測試仍可獨立執行。
## Android 偵測與測試目標

控制台可手動偵測 ADB 裝置，區分 device（已授權）、unauthorized、offline 及其他模式。ADB 會從 ANDROID_SDK_ROOT / ANDROID_HOME、Windows 使用者 Android SDK 標準位置與 PATH 尋找，不修改 PATH 或另裝軟體。

`GET /api/android/state` 只讀取快照與工具是否存在，不執行 ADB；`GET /api/android/scan` 只執行固定的 `adb version`、`adb devices -l`，必要時由 ADB 啟動本機服務。執行不持有模擬器串口鎖，最長版本查詢 2 秒、裝置查詢 6 秒。沒有通用 shell 或任意命令 API。

`POST /api/android/select` 使用 `{"serial":"裝置序號"}` 登記測試目標。需要 30 秒內的正常掃描、唯一序號、state=device；未授權/離線/歧義/過期快照均拒絕。不自動挑第一支手機；已登記手機拔除時保留其身分，不改選其他裝置。設定為 `pc/local/android_target.json`，不加入 Git，測試執行中禁止改目標。

目前不提供 App 啟動、安裝、一般檔案讀取、重開機或無線配對。需有實體測試手機並在手機自行啟用 USB 偵錯、確認 PC 授權後，才能驗證真正的已授權連線。

官方說明：https://developer.android.com/tools/adb

## 測試手機截圖

`POST /api/android/capture` 僅擷取已登記的測試目標。執行前重新掃描，必須保持同一序號、唯一且已授權；不接受請求指定其他序號。固定執行 `adb -s <已選序號> exec-out screencap -p`，10 秒逾時，以 binary bytes 接收，不經 shell 或文字換行轉換。Android 官方參考：https://developer.android.com/tools/adb#screencap

PNG 上限 16 MiB、8192×8192 且不超過 4000 萬畫素，檢查簽章、區塊結構、CRC 與完整結尾。成功後保存於 `pc/local/android_captures/`，含時間、尺寸、指定手機、ADB/PC 版本與 SHA-256。這個目錄不加入 Git；不寫檔到手機，也不把截圖自動加入其他測試報告。

`GET /api/android/captures` 列出已保存紀錄；`GET /api/android/captures/<32位id>.png` 讀取校驗後圖片，`.json` 讀取紀錄。固定 ID 與路徑檢查拒絕任意檔案讀取。控制台可查看、下載 PNG/JSON。自動測試執行中不接受新的手動截圖；ADB 等待不持有 ESP32 串口鎖。

本階段尚未接上測試手機，截圖成功路徑以測試替身驗證；實機畫面擷取仍待手機接入與授權後確認。生產紀錄不包含測試替身圖片。
## STM8 工作台準備檢查

`GET /api/stm8/state` 讀取快照與工具位置；`GET /api/stm8/scan` 使用 Windows 固定的 Get-CimInstance Win32_PnPEntity 查詢，只列 USB 中名稱符合 ST-Link/STM8/SWIM 或 VID_0483 的候選項，排除明確不在場的裝置。最多等待 8 秒，不開啟 USB probe、不讀寫晶片，不持有模擬器串口鎖。

ST-Link 名稱與驅動狀態僅供辨識，swim_verified 永遠為 false，programming_enabled 永遠為 false。ST 廠商 USB 裝置不一律視為 ST-Link。查詢失敗/逾時明確回報錯誤，不混同成功的零裝置結果。

查找 PATH 與常見 Program Files 位置的 SDCC、STVP_CmdLine、stm8flash，不執行工具，不推定版本或專案相容性。ST-LINK_CLI / STM32 工具不作為已具備 STM8 燒錄能力的證據。實際所需編譯器與版本仍以韌體專案為準。

`POST /api/stm8/source` 使用 `{"repository_url":"https://github.com/owner/repo"}` 登記至 `pc/local/stm8_project.json`。只接受不含帳密、query、fragment 的 GitHub 根 repo URL；不 clone、不編譯、不下載或燒錄，自動測試期間不允許改來源。source_verified=false；設定損壞不覆寫。尚未選定專案時維持空白，不填測試專案。

官方參考：STVP https://www.st.com/en/development-tools/stvp-stm8.html 、SDCC https://sdcc.sourceforge.net/ 。
## STM8 離線結果檢視

STM8 工作台可讀取 `pc/local/stm8-build/build-report.json` 及 `firmware.hex`，重新核對 HEX 記錄和報告中的 SHA-256、資料範圍。缺檔、報告不符或校驗失敗時不顯示通過；目前登記來源不同時會顯示來源不符。只讀取固定本機路徑，不接受網頁指定的檔案路徑，也不啟動編譯器或燒錄工具。

`GET /api/stm8/build` 回傳檢視狀態；`GET /api/stm8/build/report` 下載已通過檔案核對的原始編譯報告，無有效產物時為 404。沒有上傳、執行或燒錄端點。來源與編譯操作見 [離線編譯說明](../docs/stm8-offline-build.md)。

## 啟動 Android TSDZ App

先偵測並指定已授權手機，再按「啟動原作者 TSDZ App」。`POST /api/android/launch` 重新確認同一序號仍唯一且已授權，查詢固定套件是否安裝，再啟動其 MainActivity；不接受客戶端提供套件名或任意指令。自動 ESP32 測試期間拒絕啟動操作。

入口依據[原作者 AndroidManifest.xml](https://github.com/TSDZ2-ESP32/TSDZ2-Android/blob/master/app/src/main/AndroidManifest.xml)：`spider65.ebike.tsdz2_esp32/.MainActivity`。使用明確 `adb -s`、固定 `pm path` / `am start -W -n`，不安裝 APK、授權權限或操作 App 內設定。App 自身啟動後的行為由該 App 決定。Android 回報啟動成功不等於 BLE、Gateway 或 STM8 已驗證。

成功路徑以測試替身驗證；目前未接入測試手機，實機啟動與真 BLE 回歸仍待驗證。
