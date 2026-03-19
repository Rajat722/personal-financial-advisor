@echo off
cd /d D:\Dev\personal-financial-advisor

for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set datetime=%%I
set YEAR=%datetime:~0,4%
set MONTH=%datetime:~4,2%
set DAY=%datetime:~6,2%
set HOUR=%datetime:~8,2%
set MIN=%datetime:~10,2%

if not exist "logs\scheduler_runs" mkdir logs\scheduler_runs

set LOGFILE=logs\scheduler_runs\ingest_%YEAR%-%MONTH%-%DAY%_%HOUR%-%MIN%.txt

echo [%YEAR%-%MONTH%-%DAY% %HOUR%:%MIN%] Starting news_ingest_pipeline >> "%LOGFILE%"
C:\Users\rajat\anaconda3\envs\finAdvisor\python.exe news\news_ingest_pipeline.py >> "%LOGFILE%" 2>&1
echo [%YEAR%-%MONTH%-%DAY% %HOUR%:%MIN%] Finished >> "%LOGFILE%"
exit