@echo off
chcp 65001 >nul
echo 垃圾/缓存候选清理脚本
echo.
echo 安全提醒：此脚本不会由工具自动执行。
echo 建议先检查 file-organization-plan.md 和 file-organization-report.md。
echo.
echo 低风险候选：4 个
echo 中风险候选：0 个（只提示，不自动删除）
echo.
echo 将删除以下低风险候选：
echo   __pycache__/organize.cpython-314.pyc
echo   __pycache__/app_native.cpython-314.pyc
echo   __pycache__/web_app.cpython-314.pyc
echo   __pycache__/app_gui.cpython-314.pyc
echo.
echo 预计释放空间：152.2 KB
pause
echo.
del /f /q "C:\Users\xiaobai\Desktop\不会动文件的 AI 扫描器\__pycache__\organize.cpython-314.pyc"
if exist "C:\Users\xiaobai\Desktop\不会动文件的 AI 扫描器\__pycache__\organize.cpython-314.pyc" (echo 失败: __pycache__/organize.cpython-314.pyc) else (echo 已删除: __pycache__/organize.cpython-314.pyc)
del /f /q "C:\Users\xiaobai\Desktop\不会动文件的 AI 扫描器\__pycache__\app_native.cpython-314.pyc"
if exist "C:\Users\xiaobai\Desktop\不会动文件的 AI 扫描器\__pycache__\app_native.cpython-314.pyc" (echo 失败: __pycache__/app_native.cpython-314.pyc) else (echo 已删除: __pycache__/app_native.cpython-314.pyc)
del /f /q "C:\Users\xiaobai\Desktop\不会动文件的 AI 扫描器\__pycache__\web_app.cpython-314.pyc"
if exist "C:\Users\xiaobai\Desktop\不会动文件的 AI 扫描器\__pycache__\web_app.cpython-314.pyc" (echo 失败: __pycache__/web_app.cpython-314.pyc) else (echo 已删除: __pycache__/web_app.cpython-314.pyc)
del /f /q "C:\Users\xiaobai\Desktop\不会动文件的 AI 扫描器\__pycache__\app_gui.cpython-314.pyc"
if exist "C:\Users\xiaobai\Desktop\不会动文件的 AI 扫描器\__pycache__\app_gui.cpython-314.pyc" (echo 失败: __pycache__/app_gui.cpython-314.pyc) else (echo 已删除: __pycache__/app_gui.cpython-314.pyc)
echo.
echo 脚本结束。
pause
