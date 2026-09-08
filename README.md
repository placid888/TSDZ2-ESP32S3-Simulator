# TSDZ2-ESP32S3-Simulator
# TSDZ2 ESP32-S3 Hardware Simulator (TSDZ2 模擬控制器發射台)

這是一個專為 TSDZ2 開源儀表板專案開發的「專屬硬體模擬器」。

本專案運行於 **ESP32-S3** 開發板上，採用 **ESP-IDF v5.1** 官方框架開發。它的核心功能是**完美偽裝成真實的 TSDZ2 (STM8) 電機控制器**。透過實體 UART 吐出標準的 29-Byte 遙測封包，讓開發者在沒有實車、電機與 Windows 編譯環境的情況下，依然能順利開發、除錯 Android 車載儀表板 App 與 OTA 功能。

## 🏗 系統測試架構

本模擬器徹底將「測試控制鏈」與「正式車載鏈」分離：

```text
【測試控制鏈】                                    【正式車載鏈 (受測目標)】
[ 遙控 App 或 nRF Connect ]                       [ 儀表板 App (重構中) ]
         │ (BLE 藍牙連線)                                 ▲
         ▼ (寫入指令 C:90,T:180)                          │ (BLE 藍牙連線)
[ ESP32-S3 (本模擬器 / 扮演 STM8) ] ──(實體 UART)──▶ [ ESP32_B (車載通訊橋接端) ]
模擬器與 ESP32_B (車載端) 之間只需連接兩根線：
ESP32-S3 (本模擬器端)連接至ESP32_B (車載橋接端)說明
GND↔GND必須共地
GPIO 17 (TX)➔GPIO 17 (RX / CT_RX_PIN)傳送 29-Byte 控制器封包
通訊規格：9600 bps (8N1)，發送頻率 10 Hz (每 100ms)。
​電平相容：雙方皆為 3.3V 邏輯電平，無需電平轉換晶片。
​⚙️ 核心功能特色
​自動物理動態模型
​系統內建一套動態演算法，開機即會自動產生踏頻正弦波 (65~85 RPM) 與 扭力雙正弦波 (ADC 120~200)。
​車速與輪圈累積轉數會模擬真實慣性，平滑加速至 25 km/h。
​BLE 藍牙即時覆寫 (Override)
​可透過手機藍牙直接蓋過內建的物理模型，強制輸出指定踏頻與扭力，方便進行儀表板 App 的極限值或特定條件測試。
​超時防護機制：若超過 5 秒未收到新的 BLE 指令，系統會自動切回物理動態模型。
​精準通訊協議
​封包長度 29 Bytes，標頭為 0x43。
​結尾採用標準 Modbus CRC16 (多項式 0xA001) 演算法，保證 ESP32_B 接收校驗 100% 通過。
​📱 BLE 藍牙遙控指南
​可以使用手機端的 nRF Connect 或自製的遙控 App 進行控制：
​藍牙廣播名稱：TSDZ2_SIM
​Service UUID：0xFFF0
​Characteristic UUID：0xFFF1 (具備 Write 權限)
​指令格式 (Text/UTF-8)：
發送格式為 C:踏頻,T:扭力 的字串。
​範例：C:90,T:180 (代表設定踏頻為 90 RPM，扭力 ADC 為 180)
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
│   ├── main.c                  # 核心邏輯 (UART 封包組裝、物理模型、BLE GATT 伺服器)
│   ├── tsdz_utils.c            # Modbus CRC16 演算法實作
│   └── tsdz_utils.h
├── CMakeLists.txt              # 頂層專案宣告
└── sdkconfig.defaults          # 指定晶片為 esp32s3、開啟 USB CDC 與 NimBLE 藍牙

欺騙連線狀態 (Heartbeat 偽裝)：
ESP32_B 判斷「馬達是否連線」的唯一標準，就是 UART 有沒有持續收到開頭為 0x43、長度 29 Bytes 且 CRC16 校驗正確的封包。我們在 main.c 中嚴格設定 vTaskDelayUntil 以 100ms (10 Hz) 的頻率發送完美格式的封包，因此 ESP32_B 會 100% 相信它正連接著實體 STM8 馬達，不會觸發斷線錯誤。
​欺騙 STM8 (電機) 韌體版本：
在我們寫的 main.c 第 107 行左右，有這段封包賦值：
packet[15] = 20;  // STM8 韌體版本 (v2.0)
原作者的通訊協議中，第 16 個 Byte (packet[15]) 就是保留給 STM8 版本的。我們填入 20，當你的 Android App 透過藍牙向 ESP32_B 查詢電機版本時，ESP32_B 就會把這個 20 轉傳給 App，App 就會判定電機韌體為 v2.0。如果你未來需要測試 App 對舊版韌體的相容性，只要把這裡改成 10 (v1.0) 即可。
​關於 ESP32 自身的版本查詢：
你的架構是：手機 App \rightarrow ESP32_B \rightarrow ESP32-S3 (模擬器)。
當 App 查詢「ESP32 版本」時，是由你車載那塊真實的 ESP32_B 直接回覆它自己內部的版本號碼，這部分完全由 ESP32_B 原有韌體處理，不需要我們這塊模擬器介入偽裝。
​簡單來說，在 ESP32_B 與手機 App 的眼中，這塊 ESP32-S3 模擬器就是一顆**「運作極度穩定、韌體版本為 v2.0 的真實 TSDZ2 電機」**。