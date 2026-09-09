# TSDZ2 ESP32-S3 Hardware Simulator (TSDZ2 模擬控制器發射台)

這是一個專為 TSDZ2 開源儀表板專案開發的「專屬硬體模擬器」。

本專案運行於 **ESP32-S3** 開發板上，採用 **ESP-IDF v5.1** 官方框架開發。它的核心功能是**完美偽裝成真實的 TSDZ2 (STM8) 電機控制器**。透過實體 UART 吐出標準的 29-Byte 遙測封包，讓開發者在沒有實車、電機與 Windows 編譯環境的情況下，依然能順利開發、除錯 Android 車載儀表板 App 與 OTA 功能。

## 🏗 系統測試架構

本模擬器徹底將「測試控制鏈」與「正式車載鏈」分離：

```text
【測試控制鏈】                                    【正式車載鏈 (受測目標)】
[ 遙控 App 或 nRF Connect ]                       [ 儀表板 App (重構中) ]
         │ (BLE 藍牙連線)                                 ▲
         ▼ (寫入指令 C:90,T:180...)                       │ (BLE 藍牙連線)
[ ESP32-S3 (本模擬器 / 扮演 STM8) ] ──(實體 UART)──▶ [ ESP32_B (車載通訊橋接端) ]
硬體接線定義
​模擬器與 ESP32_B (車載端) 之間只需連接兩根線：
ESP32-S3 (本模擬器端)連接至ESP32_B (車載橋接端)說明
GND↔GND必須共地
GPIO 17 (TX)➔GPIO 17 (RX / CT_RX_PIN)傳送 29-Byte 控制器封包
​⚙️ 核心功能特色
​自動物理動態模型
​系統內建一套動態演算法，開機即會自動產生踏頻正弦波 (65~85 RPM) 與 扭力雙正弦波 (ADC 120~200)。
​車速與輪圈累積轉數會模擬真實慣性，平滑加速至 25 km/h。
​全功能 BLE 藍牙即時覆寫 (Override)
​可透過手機藍牙直接蓋過內建的物理模型，強制輸出指定數值，包含踏頻、扭力、車速、電壓、溫度與錯誤碼，方便進行儀表板 App 的極限值或特定條件測試。
​超時防護機制：若超過 10 秒未收到新的 BLE 指令，系統會自動切回物理動態模型。
​精準通訊協議
​封包長度 29 Bytes，標頭為 0x43。
​結尾採用標準 Modbus CRC16 (多項式 0xA001) 演算法，保證 ESP32_B 接收校驗 100% 通過。
​🎭 深度偽裝機制 (Spoofing)
​在 ESP32_B 與手機 App 的眼中，這塊 ESP32-S3 模擬器就是一顆**「運作極度穩定、韌體版本為 v2.0 的真實 TSDZ2 電機」**，主要透過以下機制實現：
​連線狀態 (Heartbeat) 偽裝：ESP32_B 判斷「馬達是否連線」的唯一標準是 UART 封包。模擬器透過嚴格的時序控制（10 Hz）持續發送完美格式的 29-Byte 封包，確保 ESP32_B 100% 相信它正連接著實體 STM8 馬達，不會觸發斷線錯誤。
​STM8 電機韌體版本欺騙：封包內的第 16 個 Byte (packet[15]) 被寫死為 20。當 Android App 透過藍牙查詢電機版本時，系統會穩定回報其為 v2.0（若需測試舊版相容性，可於程式碼中改為 10）。
​ESP32 版本查詢獨立性：當 App 查詢「ESP32 版本」時，是由車載的真實 ESP32_B 直接回覆其內部版本號碼。這部分完全由 ESP32_B 原有韌體處理，維持了雙層架構的真實性。
​📱 BLE 藍牙遙控指南 (全功能作弊模式)
​可以使用手機端的 nRF Connect 或自製的遙控 App 進行控制：
​藍牙廣播名稱：TSDZ2_SIM
​Service UUID：0xFFF0
​Characteristic UUID：0xFFF1 (具備 Write 權限)
​指令格式 (Text/UTF-8)
​系統支援 6 大參數的彈性解析，參數間以逗號 , 隔開，順序不拘，未設定的參數將維持當前狀態。
​C：踏頻 (RPM)
​T：扭力 (ADC)
​S：車速 (km/h)
​V：電池電壓 (V)
​E：錯誤代碼/煞車狀態
​H：馬達溫度 (°C)
​指令範例：
​測試極速：S:50 (僅修改車速為 50 km/h)
​測試低電壓與過熱：V:32,H:90
​全參數覆寫：C:90,T:180,S:35,V:48,E:0,H:38
​☁️ 雲端編譯與燒錄 (GitHub Actions)
​本專案無需在本地電腦安裝任何編譯工具鏈，完全依賴 GitHub 雲端編譯：
​修改任何程式碼並 Push 至 main 分支。
​切換至 GitHub 倉庫的 Actions 頁籤。
​等待 Build ESP32-S3 Simulator 任務完成（亮綠燈）。
​在頁面底部的 Artifacts 下載 esp32s3-simulator-binaries。
​解壓縮後，可使用 Android 手機瀏覽器 (Chrome) 開啟 ESP Web Flasher，透過 Type-C 線直接將 .bin 燒錄至 ESP32-S3。
​📁 專案目錄結構
TSDZ2-ESP32S3-Simulator/
├── .github/workflows/build.yml # GitHub Actions 自動編譯腳本 (使用官方 esp-idf v5.1 容器)
├── main/
│   ├── CMakeLists.txt          # 宣告編譯模組 (包含 driver, freertos, nvs_flash, bt)
│   ├── main.c                  # 核心邏輯 (UART 封包組裝、動態模型、全功能 BLE 解析)
│   ├── tsdz_utils.c            # Modbus CRC16 演算法實作
│   └── tsdz_utils.h
├── CMakeLists.txt              # 頂層專案宣告
└── sdkconfig.defaults          # 指定晶片為 esp32s3、開啟 USB CDC 與 NimBLE 藍牙