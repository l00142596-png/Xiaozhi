@echo off
cd /d C:\Users\Administrator\VS511\xiaozhi-esp32
set IDF_PATH=C:\esp-idf-v5.5.2
set IDF_PYTHON_ENV_PATH=C:\Users\Administrator\.espressif\python_env\idf5.5_py3.14_env
set PATH=C:\Users\Administrator\.espressif\python_env\idf5.5_py3.14_env\Scripts;C:\Users\Administrator\.espressif\tools\riscv32-esp-elf\esp-14.2.0_20241119\riscv32-esp-elf\bin;C:\Users\Administrator\.espressif\tools\cmake\3.30.2\bin;C:\Users\Administrator\.espressif\tools\ninja\1.12.1;C:\Users\Administrator\.espressif\tools\idf-exe\1.0.3;C:\Users\Administrator\.espressif\tools\ccache\4.10.2;%PATH%
C:\Users\Administrator\.espressif\python_env\idf5.5_py3.14_env\Scripts\python.exe C:\esp-idf-v5.5.2\tools\idf.py build
