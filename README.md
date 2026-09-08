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