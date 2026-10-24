# JK BMS 藍牙接入

## 已完成：掃描與本機登記

使用者指定藍牙介面。購買截圖顯示 8–17 串、0.6A 均衡、60A 持續的選項，表格可能對應 JK-BD6A17S6P；照片不是板身標籤，型號與硬/軟體版本仍待確認。訂單、姓名、地址及電話不納入程式或測試資料。

PC 使用 Bleak 3.0.2，主動掃描 BLE 廣播 5 秒（可能包含 scan request/response），不建立 GATT 連線、不配對、不讀寫 characteristic、不發送 JK 設定或充放電指令。Windows 實測掃描成功。名稱含 JK / JIKONG 僅為排序提示，不代表確定是極空保護板。

控制台「電池 BMS」快速導覽可開啟電池工作台。選擇明確位址後按「登記這塊保護板」；只接受 60 秒內掃描到的唯一位址，不自動選第一台。登記存於忽略的 `pc/local/jk_bms.json`，服務重啟後不自動連線。鄰近裝置清單只放記憶體，不進 Git 或整合資料包。掃描失敗會明確顯示，不當作成功的空清單。

API：`GET /api/bms/state`、`POST /api/bms/scan`、`POST /api/bms/select`（JSON `address`）。掃描與登記在模型自動測試期間拒絕，耗時掃描不持有模型通訊鎖。

目前 `connected=false`、`protocol_verified=false`、`telemetry=null`，沒有電壓、電流或 SOC 的虛構數值。BMS 尚未列入既有 HIL 8 項計分，也不把廣播出現當成實機整合成功。

## 後續階段

1. 使用者確認藍牙裝置與板身標籤，提供極空 App 的硬體/軟體版本；必要時先讓手機 App 斷開，避免佔用連線。
2. 對明確指定的保護板做服務探索，核對 UUID 與協定版本。
3. 只實作經核對的查詢和通知接收、分包重組與校驗；保留原始測試資料於本機。
4. 解析總壓、電流、SOC、電芯、溫度與告警；每項附單位、時間與資料有效性。
5. 加入斷線恢復、紀錄與整合報告，保持與模擬電池分開顯示。

充放電開關、均衡開關、保護參數修改不屬於目前實作範圍。

## 核對來源

- Bleak Scanner API：<https://bleak.readthedocs.io/en/latest/api/scanner.html>
- 原作者開源實作及支援紀錄：<https://github.com/syssi/esphome-jk-bms>

該專案列出 JK-BD6A17S6P hw 7.2 / sw 7.1.0H 的支援紀錄，並說明 `JK02_24S` 與 `JK02_32S` 是幀格式選項，不是電池串數。這是開源專案的相容紀錄，不是使用者這塊板的實測結果。未複製其控制程式到本專案。
