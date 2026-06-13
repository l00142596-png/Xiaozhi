param([string]$Action = "build")

Remove-Item Env:MSYSTEM -ErrorAction SilentlyContinue
$env:CMAKE_MAKE_PROGRAM = "C:\Users\Administrator\.espressif\tools\ninja\1.12.1\ninja.exe"
$env:IDF_PATH = "C:\esp-idf-v5.5.2"
$env:IDF_PYTHON_ENV_PATH = "C:\Users\Administrator\.espressif\python_env\idf5.5_py3.14_env"
$env:ESP_ROM_ELF_DIR = "C:\Users\Administrator\.espressif\tools\esp-rom-elfs\20241011\"
$env:ESP_IDF_VERSION = "5.5"
$env:PATH = "C:\Users\Administrator\.espressif\tools\riscv32-esp-elf\esp-14.2.0_20251107\riscv32-esp-elf\bin;C:\Users\Administrator\.espressif\tools\cmake\3.30.2\bin;C:\Users\Administrator\.espressif\tools\ninja\1.12.1;C:\Users\Administrator\.espressif\tools\idf-exe\1.0.3;C:\Users\Administrator\.espressif\tools\ccache\4.10.2;C:\Users\Administrator\.espressif\python_env\idf5.5_py3.14_env\Scripts;" + $env:PATH

Set-Location "C:\Users\Administrator\VS511\xiaozhi-esp32"

$python = "C:\Users\Administrator\.espressif\python_env\idf5.5_py3.14_env\Scripts\python.exe"
$idf_py = "C:\esp-idf-v5.5.2\tools\idf.py"

switch ($Action) {
    "set-target" {
        & $python $idf_py -DCMAKE_MAKE_PROGRAM="C:\Users\Administrator\.espressif\tools\ninja\1.12.1\ninja.exe" set-target esp32p4
    }
    "build"   {
        & $python $idf_py -DCMAKE_MAKE_PROGRAM="C:\Users\Administrator\.espressif\tools\ninja\1.12.1\ninja.exe" build
    }
    "flash"   { & $python $idf_py -p COM7 flash }
    "monitor" { & $python $idf_py -p COM7 monitor }
    "clean"   { & $python $idf_py fullclean }
    "menuconfig" { & $python $idf_py menuconfig }
    default   { Write-Host "Usage: build_xiaozhi.ps1 [-Action] build|flash|monitor|clean|set-target|menuconfig" }
}
