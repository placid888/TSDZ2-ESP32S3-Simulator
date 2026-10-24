# STM8 離線編譯

已於 2026-10-24 在 Windows 實際編譯成功，僅為離線產物，沒有開啟 ST-Link、寫入韌體或 Option Bytes。

## 固定來源與工具

- 原始碼：<https://github.com/TSDZ2-ESP32/TSDZ2-Smart-EBike>
- Commit：`3df3083ad220856eb416692aa6d5ad73f5fdd1fc`
- `main.h` 的 `FW_VERSION` 為 17。Wiki 的成品目錄查詢時最高列到 v16，未驗證兩者等價。
- 工具：PlatformIO registry 的 `platformio/toolchain-sdcc@1.40400.0`，實測版本 SDCC 4.4.0 #14620。
- 原始碼授權：上游 GPL-3.0；保持 LICENSE 及各檔案原有授權文字。
- 上游標頭選擇 STM8S105 系列，但不據此推定使用者實體板的完整晶片型號、容量、接線。

官方 SDCC Windows 安裝程式下載在本次環境回傳 HTML，未執行該檔；改用已安裝的 PlatformIO 從其套件庫取得固定版本。不改全機 PATH，編譯器子程序的 PATH 才加入工具目錄。

## 重現

以下從 repository 根目錄執行；`python`、`pio`、`git` 需可使用。原始碼 checkout 放在忽略的 `pc/local/`，輸出使用新的 `build-*` 目錄。既有目錄不會覆寫。

```powershell
pio pkg install --global --tool platformio/toolchain-sdcc@1.40400.0
git clone https://github.com/TSDZ2-ESP32/TSDZ2-Smart-EBike.git pc/local/stm8-source
git -C pc/local/stm8-source checkout --detach 3df3083ad220856eb416692aa6d5ad73f5fdd1fc
python pc/stm8_build.py --source pc/local/stm8-source --sdcc "$env:USERPROFILE/.platformio/packages/toolchain-sdcc/bin/sdcc.exe" --output build-stm8-run1
```

已存在 checkout 時略過 clone，先檢查自己的變更再切換版本。工具會拒絕不同 commit 或 Git 偵測到的未提交變更。SDCC 路徑可以明確指定，不依賴網頁輸入。

本機 helper 直接逐檔呼叫 SDCC，使用已核對 Windows Makefile 的來源清單及旗標，不執行上游 `compile_and_flash.bat`、Makefile 的 flash/clean target 或任何下載腳本。上游來源複製到獨立輸出目錄編譯，原 checkout 不變。

## 產物與實測

- `firmware.hex`：`main.ihx` 的原樣複本，未變更位址或插入 bootloader。
- `build.log`：完整命令及輸出。
- `build-report.json`：commit、來源檔雜湊、編譯器版本/雜湊、旗標、警告、HEX 校驗及資料範圍。
- `src/` 與 `LICENSE.upstream`：編譯副本及授權。

兩次獨立輸出目錄的編譯得到相同 HEX SHA-256：
`8615b0db90e5232e906a731832d3612f4b12e8939d8f0c2e3b36708cc9af0464`。
資料共 23,648 bytes，絕對位址 `0x8000–0xDC5F`。檢查了 Intel HEX 記錄長度、校驗碼、EOF、重疊資料與延伸位址。這不是實體晶片容量或執行行為驗證。

共 19 行上游 warning 283（函式宣告沒有 prototype），保留於報告。未改動原作者的馬達控制演算法，也未宣稱可直接上車使用。下一階段需先確認實體晶片與備份方式、再做讀取和 HIL 驗證。

指南：<https://github.com/TSDZ2-ESP32/TSDZ2-ESP32-Wiki/wiki/TSDZ-Controller-Flash>
